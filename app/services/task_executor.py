import asyncio
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion, OpenAITextCompletion
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.task import Task, TaskMessage, TaskStatus
from app.models.crew import AgentCrew, CrewMember
from app.models.agent import Agent
from app.services.copilot_client import CopilotStudioClient
from app.observability.telemetry import LLMCallTracker, AgentCallTracker, TaskExecutionTracker

class TaskExecutor:
    def __init__(self, db: Session, task_id: int):
        self.db = db
        self.task_id = task_id
        self.task = self.db.query(Task).filter(Task.id == task_id).first()
        self.crew = self.db.query(AgentCrew).filter(AgentCrew.id == self.task.crew_id).first()
        self.crew_members = (
            self.db.query(CrewMember)
            .filter(CrewMember.crew_id == self.crew.id)
            .all()
        )
        self.agents = {}
        for member in self.crew_members:
            agent = self.db.query(Agent).filter(Agent.id == member.agent_id).first()
            self.agents[agent.copilot_id] = {
                "agent": agent,
                "role": member.role
            }
        
        self.copilot_client = CopilotStudioClient(settings.DIRECT_LINE_SECRET)
        self.kernel = None
        self.semantic_functions = {}
        self.task_context = None
        self.llm_model = "gpt-4"  # Default model, will be updated during setup
    
    async def setup_kernel(self):
        """Initialize Semantic Kernel with OpenAI backend"""
        self.kernel = sk.Kernel()
        
        # Configure AI backend based on config
        if settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT:
            # Azure OpenAI
            self.llm_model = "azure-gpt-4"
            self.kernel.add_chat_service(
                "chat_completion",
                OpenAIChatCompletion(
                    deployment_name="gpt-4",
                    endpoint=settings.AZURE_OPENAI_ENDPOINT,
                    api_key=settings.AZURE_OPENAI_API_KEY,
                )
            )
        else:
            # OpenAI
            self.llm_model = "gpt-4"
            self.kernel.add_chat_service(
                "chat_completion",
                OpenAIChatCompletion(
                    ai_model_id="gpt-4",
                    api_key=settings.OPENAI_API_KEY,
                )
            )
        
        # Initialize task context with task details
        self.task_context = self.kernel.create_new_context()
        self.task_context["task_description"] = self.task.description
        self.task_context["crew_name"] = self.crew.name
        
        # Add agent details to context
        agents_info = []
        for agent_id, info in self.agents.items():
            agents_info.append({
                "name": info["agent"].name,
                "role": info["role"],
                "capabilities": info["agent"].capabilities,
                "copilot_id": agent_id
            })
        self.task_context["agents"] = json.dumps(agents_info)
    
    def create_orchestration_semantic_functions(self):
        """Create semantic functions for orchestration"""
        # Task planner function
        planner_prompt = """
        You are an AI task orchestrator. Your job is to break down a task into subtasks 
        that can be assigned to specialized AI agents.
        
        TASK DESCRIPTION:
        {{$task_description}}
        
        AVAILABLE AGENTS:
        {{$agents}}
        
        Create a plan to solve this task by breaking it down into 3-7 sequential subtasks.
        For each subtask, specify:
        1. The subtask description
        2. Which agent should handle it (use their copilot_id)
        3. Why this agent is best suited for this subtask
        
        Respond in the following JSON format:
        {
            "plan": [
                {
                    "subtask": "Detailed description of the subtask",
                    "agent_id": "copilot_id of the assigned agent",
                    "reasoning": "Why this agent is suitable for this subtask"
                },
                ...
            ]
        }
        """
        
        self.semantic_functions["planner"] = self.kernel.create_semantic_function(
            planner_prompt,
            max_tokens=1000,
            temperature=0.7,
        )
        
        # Result aggregator function
        aggregator_prompt = """
        You are a result aggregator for a multi-agent task execution system.
        Your job is to compile the results from various AI agents into a coherent final result.
        
        TASK DESCRIPTION:
        {{$task_description}}
        
        AGENT RESPONSES:
        {{$agent_responses}}
        
        Create a comprehensive summary of the results that addresses the original task.
        Focus on providing a clear, actionable answer that integrates all the information
        provided by the agents.
        
        Keep your response concise but thorough.
        """
        
        self.semantic_functions["aggregator"] = self.kernel.create_semantic_function(
            aggregator_prompt,
            max_tokens=1000,
            temperature=0.3,
        )
    
    async def execute_task(self):
        """Main function to execute a task with the agent crew"""
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
                
                # Setup semantic kernel
                await self.setup_kernel()
                self.create_orchestration_semantic_functions()
                
                # Create task plan using LLM
                plan_result = None
                with LLMCallTracker(self.llm_model, "planner", self.task_context["task_description"]) as llm_tracker:
                    plan_result = await self.semantic_functions["planner"].invoke_async(self.task_context)
                    # Update token counts from result if available
                    if hasattr(plan_result, 'prompt_tokens'):
                        llm_tracker.prompt_tokens = plan_result.prompt_tokens
                    if hasattr(plan_result, 'completion_tokens'):
                        llm_tracker.completion_tokens = plan_result.completion_tokens
                    llm_tracker.response = plan_result.result
                
                plan = json.loads(plan_result.result)
                
                # Add plan to task messages
                plan_message = TaskMessage(
                    task_id=self.task.id,
                    content=f"Task Plan Created:\n{json.dumps(plan, indent=2)}",
                    is_system=True
                )
                self.db.add(plan_message)
                self.db.commit()
                
                # Execute each subtask with the appropriate agent
                agent_responses = []
                for idx, subtask in enumerate(plan["plan"]):
                    subtask_message = TaskMessage(
                        task_id=self.task.id,
                        content=f"Executing subtask {idx+1}: {subtask['subtask']}",
                        is_system=True
                    )
                    self.db.add(subtask_message)
                    self.db.commit()
                    
                    # Get agent details
                    agent_id = subtask["agent_id"]
                    agent_info = self.agents.get(agent_id)
                    if not agent_info:
                        error_msg = f"Agent with ID {agent_id} not found in crew"
                        self._add_error_message(error_msg)
                        continue
                    
                    # Execute subtask with Copilot Studio agent
                    try:
                        # Use agent call tracker for telemetry
                        with AgentCallTracker(
                            agent_id=agent_id,
                            agent_name=agent_info["agent"].name,
                            input_message=subtask["subtask"]
                        ) as agent_tracker:
                            response = await self.copilot_client.send_message(
                                agent_id=agent_id,
                                message=subtask["subtask"],
                                conversation_id=f"task_{self.task.id}_subtask_{idx}"
                            )
                            agent_tracker.response = response
                        
                        # Add agent response to task messages
                        agent_message = TaskMessage(
                            task_id=self.task.id,
                            agent_id=agent_info["agent"].id,
                            content=response,
                            is_system=False
                        )
                        self.db.add(agent_message)
                        self.db.commit()
                        
                        # Store for aggregation
                        agent_responses.append({
                            "agent_name": agent_info["agent"].name,
                            "agent_role": agent_info["role"],
                            "subtask": subtask["subtask"],
                            "response": response
                        })
                    except Exception as e:
                        error_msg = f"Error executing subtask with agent {agent_info['agent'].name}: {str(e)}"
                        self._add_error_message(error_msg)
                
                # Aggregate results using LLM
                if agent_responses:
                    self.task_context["agent_responses"] = json.dumps(agent_responses)
                    
                    # Use LLM call tracker for the aggregation
                    aggregation_result = None
                    with LLMCallTracker(
                        self.llm_model, 
                        "aggregator", 
                        json.dumps(agent_responses)
                    ) as llm_tracker:
                        aggregation_result = await self.semantic_functions["aggregator"].invoke_async(self.task_context)
                        # Update token counts from result if available
                        if hasattr(aggregation_result, 'prompt_tokens'):
                            llm_tracker.prompt_tokens = aggregation_result.prompt_tokens
                        if hasattr(aggregation_result, 'completion_tokens'):
                            llm_tracker.completion_tokens = aggregation_result.completion_tokens
                        llm_tracker.response = aggregation_result.result
                    
                    # Add aggregated result to task
                    result_message = TaskMessage(
                        task_id=self.task.id,
                        content=f"Task Result:\n{aggregation_result.result}",
                        is_system=True
                    )
                    self.db.add(result_message)
                    
                    # Update task with result
                    self.task.result = {"summary": aggregation_result.result, "details": agent_responses}
                    self.task.status = TaskStatus.COMPLETED
                    self.task.completed_at = datetime.utcnow()
                else:
                    # No agent responses, mark task as failed
                    self.task.status = TaskStatus.FAILED
                    self.task.error = "No agent responses were collected"
                    self.task.completed_at = datetime.utcnow()
                
                self.db.add(self.task)
                self.db.commit()
                self.db.refresh(self.task)
                
                completion_message = TaskMessage(
                    task_id=self.task.id,
                    content=f"Task {self.task.status.value}: {self.task.title}",
                    is_system=True
                )
                self.db.add(completion_message)
                self.db.commit()
                
                # Set the result for the task tracker
                task_tracker.result = self.task.result
                
            except Exception as e:
                self._handle_task_error(str(e))
                raise  # Re-raise to ensure the task tracker captures the error
    
    def _add_error_message(self, error_msg: str):
        """Add error message to task messages"""
        error_message = TaskMessage(
            task_id=self.task.id,
            content=f"Error: {error_msg}",
            is_system=True
        )
        self.db.add(error_message)
        self.db.commit()
    
    def _handle_task_error(self, error_msg: str):
        """Handle task error and update task status"""
        self._add_error_message(error_msg)
        
        self.task.status = TaskStatus.FAILED
        self.task.error = error_msg
        self.task.completed_at = datetime.utcnow()
        self.db.add(self.task)
        self.db.commit()
        self.db.refresh(self.task)

async def execute_task_with_crew(task_id: int, db: Session):
    """Execute a task with an agent crew using Semantic Kernel orchestration"""
    executor = TaskExecutor(db, task_id)
    await executor.execute_task() 