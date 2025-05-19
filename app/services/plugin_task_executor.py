import json
import re
from datetime import datetime
from typing import Dict, List, Any, Optional

from semantic_kernel import Kernel
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.task import Task, TaskMessage, TaskStatus
from app.models.crew import AgentCrew, CrewMember
from app.models.agent import Agent
from app.services.agent_pool import AgentPoolManager
from app.observability.telemetry import LLMCallTracker, TaskExecutionTracker


class PluginTaskExecutor:
    """Task executor that uses Semantic Kernel plugins for agent orchestration"""
    
    def __init__(self, db: Session, task_id: int):
        """
        Initialize the plugin-based task executor.
        
        Args:
            db: Database session
            task_id: Task ID to execute
        """
        self.db = db
        self.task_id = task_id
        self.task = self.db.query(Task).filter(Task.id == task_id).first()
        self.crew = self.db.query(AgentCrew).filter(AgentCrew.id == self.task.crew_id).first()
        self.crew_members = (
            self.db.query(CrewMember)
            .filter(CrewMember.crew_id == self.crew.id)
            .all()
        )
        
        # Initialize agent information
        self.agents = []
        for member in self.crew_members:
            agent = self.db.query(Agent).filter(Agent.id == member.agent_id).first()
            if agent:
                self.agents.append(agent)
        
        # Initialize Semantic Kernel components
        self.kernel = None
        self.llm_model = "gpt-4"  # Will be updated during setup
        self.agent_pool = None
    
    def _sanitize_plugin_name(self, name: str) -> str:
        """
        Sanitize a name to be used as a plugin name.
        Plugin names must match the pattern ^[0-9A-Za-z_]+$
        
        Args:
            name: The name to sanitize
            
        Returns:
            A sanitized name that can be used as a plugin name
        """
        # Replace spaces and non-alphanumeric characters with underscores
        sanitized = re.sub(r'[^0-9A-Za-z_]', '_', name)
        
        # Ensure the name starts with a letter or underscore (not a number)
        if sanitized and sanitized[0].isdigit():
            sanitized = f"_{sanitized}"
            
        return sanitized
    
    async def setup_kernel(self):
        """Initialize Semantic Kernel with OpenAI backend and agent plugins"""
        # Create the kernel
        self.kernel = Kernel()
        
        # Configure AI backend based on config
        if settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT:
            # Azure OpenAI
            self.llm_model = "azure-gpt-4"
            self.kernel.add_service(
                AzureChatCompletion(
                    service_id="chat_completion",
                    deployment_name="gpt-4",
                    endpoint=settings.AZURE_OPENAI_ENDPOINT,
                    api_key=settings.AZURE_OPENAI_API_KEY,
                )
            )
        else:
            # OpenAI
            self.llm_model = "gpt-4"
            self.kernel.add_service(
                OpenAIChatCompletion(
                    service_id="chat_completion",
                    ai_model_id="gpt-4",
                    api_key=settings.OPENAI_API_KEY,
                )
            )
        
        # Create an AgentPool instance using the AgentPoolManager
        self.agent_pool = AgentPoolManager.create_agent_pool(
            crew_members=self.crew_members,
            agents=self.agents,
            task_id=self.task_id
        )
        
        # Create a valid plugin name
        plugin_name = self._sanitize_plugin_name(f"{self.crew.name}Agents")
        
        # Register the agent pool with the kernel
        AgentPoolManager.register_with_kernel(self.agent_pool, self.kernel, plugin_name=plugin_name)
    
    def create_orchestration_function(self):
        """Create a semantic function for task orchestration"""
        # Task orchestrator prompt
        orchestrator_prompt = """
        You are an AI task orchestrator responsible for solving complex tasks by using specialized AI agents.
        
        TASK DESCRIPTION:
        {{$task_description}}
        
        CREW NAME:
        {{$crew_name}}
        
        IMPORTANT: You must DIRECTLY CALL the available agent functions to complete this task. 
        DO NOT write pseudocode or describe what you would do - actually execute the task by calling 
        the appropriate agent functions that are available to you.
        
        The agent functions are already registered and ready to use - you just need to call them.
        DO NOT try to define new functions or create mock implementations.
        
        Think step by step:
        1. Break down the task into logical steps
        2. For each step, decide which agent would be best suited to handle it
        3. DIRECTLY CALL the appropriate agent function with a clear, specific request
        4. Use the agent's response as your answer or to inform the next step
        5. If needed, ask follow-up questions to the same or different agents
        
        Your final response should be the ACTUAL RESULT of the task, not a plan or pseudocode.
        """
        
        # Create the orchestrator function
        orchestrator = self.kernel.add_function(
            plugin_name="task_orchestrator",
            function_name="task_orchestrator",
            description="Orchestrates complex tasks by delegating to specialized agents",
            prompt=orchestrator_prompt
        )
        
        return orchestrator
    
    async def execute_task(self):
        """Main function to execute a task with the agent crew using Semantic Kernel plugins"""
        # Create a task execution tracker for the entire task
        with TaskExecutionTracker(self.task.id, self.crew.id, self.task.description) as task_tracker:
            try:
                # Update task status to in progress
                self.task.status = TaskStatus.IN_PROGRESS
                self.task.started_at = datetime.utcnow()
                self.db.add(self.task)
                self.db.commit()
                self.db.refresh(self.task)
                
                # Add system message
                system_message = TaskMessage(
                    task_id=self.task.id,
                    content=f"Task started: {self.task.title}",
                    is_system=True
                )
                self.db.add(system_message)
                self.db.commit()
                
                # Setup semantic kernel with agents as plugins
                await self.setup_kernel()
                
                # Create the task orchestration function
                orchestrator = self.create_orchestration_function()
                
                # Prepare kernel context with task details
                context = KernelArguments()
                context["task_description"] = self.task.description
                context["crew_name"] = self.crew.name
                
                # Log the available plugins
                plugin_info = []
                for plugin_name, plugin in self.kernel.plugins.items():
                    functions = []
                    for fn_name, fn in plugin.functions.items():
                        functions.append({
                            "name": fn_name,
                            "description": fn.metadata.description
                        })
                    plugin_info.append({
                        "plugin_name": plugin_name,
                        "functions": functions
                    })
                
                plugin_message = TaskMessage(
                    task_id=self.task.id,
                    content=f"Available agent plugins:\n{json.dumps(plugin_info, indent=2)}",
                    is_system=True
                )
                self.db.add(plugin_message)
                self.db.commit()
                
                # Execute task orchestration using LLM with plugin function calling
                with LLMCallTracker(self.llm_model, "orchestrator", self.task.description) as llm_tracker:
                    result = await orchestrator.invoke(
                        task_description=self.task.description,
                        crew_name=self.crew.name
                    )
                    # Record the result
                    llm_tracker.response = str(result)
                
                # Add result to task messages
                result_message = TaskMessage(
                    task_id=self.task.id,
                    content=f"Task Result:\n{result}",
                    is_system=True
                )
                self.db.add(result_message)
                
                # Update task with the result
                self.task.result = {"summary": str(result)}
                self.task.status = TaskStatus.COMPLETED
                self.task.completed_at = datetime.utcnow()
                
                self.db.add(self.task)
                self.db.commit()
                
                # Set the result for the task tracker
                task_tracker.result = self.task.result
                
                return {"status": "success", "result": str(result)}
                
            except Exception as e:
                # Handle errors
                error_msg = f"Error executing task: {str(e)}"
                
                # Add error message
                error_message = TaskMessage(
                    task_id=self.task.id,
                    content=error_msg,
                    is_system=True
                )
                self.db.add(error_message)
                
                # Update task status
                self.task.status = TaskStatus.FAILED
                self.task.error = error_msg
                self.task.completed_at = datetime.utcnow()
                
                self.db.add(self.task)
                self.db.commit()
                
                # Re-raise to ensure the task tracker captures the error
                raise


async def execute_task_with_plugins(task_id: int, db: Session):
    """Execute a task with an agent crew using Semantic Kernel plugins"""
    executor = PluginTaskExecutor(db, task_id)
    return await executor.execute_task() 