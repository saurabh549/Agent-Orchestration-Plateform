import json
from datetime import datetime
from typing import Dict, List, Any, Optional

import semantic_kernel as sk
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion, AzureChatCompletion
from semantic_kernel.functions import kernel_function
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.task import Task, TaskMessage, TaskStatus
from app.models.crew import AgentCrew, CrewMember
from app.models.agent import Agent
from app.services.copilot_client import CopilotStudioClient
from app.services.copilot_agent_plugin import CopilotAgentPlugin
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
        self.agents = {}
        for member in self.crew_members:
            agent = self.db.query(Agent).filter(Agent.id == member.agent_id).first()
            self.agents[agent.copilot_id] = {
                "agent": agent,
                "role": member.role
            }
        
        # Initialize Copilot client
        self.copilot_client = CopilotStudioClient(settings.DIRECT_LINE_SECRET)
        
        # Initialize Semantic Kernel components
        self.kernel = None
        self.llm_model = "gpt-4"  # Will be updated during setup
    
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
        
        # Register all agents as plugins
        for agent_id, info in self.agents.items():
            agent = info["agent"]
            plugin = CopilotAgentPlugin(
                copilot_client=self.copilot_client,
                agent_id=agent_id,
                agent_name=agent.name,
                capabilities=agent.capabilities,
                role=info["role"],
                task_id=self.task_id
            )
            
            # Add the plugin to the kernel
            self.kernel.add_plugin(plugin, plugin_name=f"{agent.name.replace(' ', '')}Plugin")
    
    def create_orchestration_function(self):
        """Create a semantic function for task orchestration"""
        # Task orchestrator prompt
        orchestrator_prompt = """
        You are an AI task orchestrator responsible for solving complex tasks by using specialized AI agents.
        
        TASK DESCRIPTION:
        {{$task_description}}
        
        CREW NAME:
        {{$crew_name}}
        
        Your job is to solve this task by using the available agent functions. Each agent has specific capabilities.
        You can ask agents questions, give them subtasks, and use their responses to build a comprehensive solution.
        
        Think step by step:
        1. Break down the task into logical steps
        2. For each step, decide which agent would be best suited to handle it
        3. Call the appropriate agent function with a clear, specific request
        4. Use the agent's response to move forward with your solution
        5. If needed, ask follow-up questions to the same or different agents
        
        Provide a comprehensive final answer that fully addresses the original task.
        """
        
        # Create the orchestrator function
        orchestrator = self.kernel.create_function_from_prompt(
            function_name="task_orchestrator",
            prompt=orchestrator_prompt,
            description="Orchestrates complex tasks by delegating to specialized agents"
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
                context = self.kernel.create_new_context()
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
                    result = await orchestrator.invoke(context=context)
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