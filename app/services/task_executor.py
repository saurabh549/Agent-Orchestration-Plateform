import asyncio
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

import semantic_kernel as sk
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.open_ai import OpenAIPromptExecutionSettings, AzureChatPromptExecutionSettings
from semantic_kernel.connectors.ai.google.google_ai import GoogleAIChatCompletion
from semantic_kernel.connectors.ai.google.google_ai import GoogleAIChatPromptExecutionSettings
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.prompt_template.input_variable import InputVariable
from semantic_kernel.prompt_template.prompt_template_config import PromptTemplateConfig
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
        
        self.kernel = None
        self.semantic_functions = {}
        self.task_context = None
        self.llm_model = "gpt-4"  # Default model, will be updated during setup
    
    async def setup_kernel(self):
        """Initialize Semantic Kernel with OpenAI backend"""
        self.kernel = Kernel()
        
        # # Configure AI backend based on config
        # if settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT:
        #     # Azure OpenAI
        #     self.llm_model = "azure-gpt-4"
        #     self.kernel.add_service(
        #         AzureChatCompletion(
        #             service_id="azure-openai",
        #             deployment_name="gpt-4",
        #             endpoint=settings.AZURE_OPENAI_ENDPOINT,
        #             api_key=settings.AZURE_OPENAI_API_KEY,
        #         )
        #     )
        # elif settings.GEMINI_API_KEY:
        #     # OpenAI
        #     self.llm_model = "gemini-2.0-flash"
        #     self.kernel.add_service(
        #         GoogleAIChatCompletion(
        #             gemini_model_id="gemini-2.0-flash",
        #             api_key=settings.GEMINI_API_KEY,
        #         )
        #     )
        # else:
        #     # OpenAI
        #     self.llm_model = "gpt-4"
        #     self.kernel.add_service(
        #         OpenAIChatCompletion(
        #             deployment_name="gpt-4",
        #             api_key=settings.OPENAI_API_KEY,
        #             endpoint=settings.OPENAI_ENDPOINT,
        #         )
        #     )

        # For now, just use Gemini for all tasks
        print(f"[LEGACY TASK FLOW] Using Google Gemini API for task execution")
        self.llm_model = "gemini-2.0-flash"
        self.kernel.add_service(
            GoogleAIChatCompletion(
                service_id="gemini",
                gemini_model_id="gemini-2.0-flash",
                api_key=settings.GEMINI_API_KEY,
            )
        )
        
        # Initialize task context with task details
        self.task_context = KernelArguments()
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
        1. The subtask description - be specific and detailed about what information you need
        2. Which agent should handle it (use their copilot_id)
        3. Why this agent is best suited for this subtask
        
        IMPORTANT: Your output must be valid JSON only. Do not include any code blocks, markdown formatting, or explanatory text.
        
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
        
        execution_settings = GoogleAIChatPromptExecutionSettings(
            model="gemini-2.0-flash",
            max_tokens=1000,
            temperature=0.7,
        )
        
        # Use the kernel to create semantic functions
        self.semantic_functions["planner"] = self.kernel.add_function(
            plugin_name="task_orchestrator",
            function_name="task_planner",
            description="Plans a task and breaks it into subtasks for agents",
            prompt=planner_prompt,
            prompt_execution_settings=execution_settings
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
        
        self.semantic_functions["aggregator"] = self.kernel.add_function(
            plugin_name="task_orchestrator",
            function_name="task_aggregator",
            description="Aggregates agent responses into a final result",
            prompt=aggregator_prompt,
            prompt_execution_settings=execution_settings
        )
    
    async def execute_task(self):
        """Main function to execute a task with the agent crew"""
        # Create a task execution tracker for the entire task
        print(f"\n[LEGACY TASK FLOW] Starting execution of task {self.task.id}: {self.task.title}")
        with TaskExecutionTracker(self.task.id, self.crew.id, self.task.description) as task_tracker:
            try:
                # Update task status to in progress
                self.task.status = TaskStatus.IN_PROGRESS
                self.task.started_at = datetime.utcnow()
                self.db.add(self.task)
                self.db.commit()
                self.db.refresh(self.task)
                
                print(f"[LEGACY TASK FLOW] Task status updated to IN_PROGRESS")
                
                # Add system message
                system_message = TaskMessage(
                    task_id=self.task.id,
                    content=f"Task started: {self.task.title}",
                    is_system=True
                )
                self.db.add(system_message)
                self.db.commit()
                
                # Setup semantic kernel
                print(f"[LEGACY TASK FLOW] Setting up semantic kernel")
                await self.setup_kernel()
                self.create_orchestration_semantic_functions()
                
                # Create task plan using LLM
                print(f"[LEGACY TASK FLOW] Creating task plan using LLM")
                plan_result = None
                with LLMCallTracker(self.llm_model, "planner", self.task_context["task_description"]) as llm_tracker:
                    plan_result = await self.kernel.invoke(
                        self.semantic_functions["planner"],
                        task_description=self.task_context["task_description"],
                        agents=self.task_context["agents"]
                    )
                    # Update token counts from result if available
                    if hasattr(plan_result, 'prompt_tokens'):
                        llm_tracker.prompt_tokens = plan_result.prompt_tokens
                    if hasattr(plan_result, 'completion_tokens'):
                        llm_tracker.completion_tokens = plan_result.completion_tokens
                    llm_tracker.response = str(plan_result)
                
                try:
                    plan = json.loads(str(plan_result))
                    print(f"[LEGACY TASK FLOW] Plan created: {json.dumps(plan, indent=2)}")
                except (ValueError, json.JSONDecodeError):
                    # If the result is not valid JSON, try to extract the result field
                    if hasattr(plan_result, 'result'):
                        try:
                            plan = json.loads(plan_result.result)
                            print(f"[LEGACY TASK FLOW] Plan created from result field: {json.dumps(plan, indent=2)}")
                        except (ValueError, json.JSONDecodeError):
                            # The result might be wrapped in Markdown code block
                            result_str = str(plan_result.result)
                            print(f"[LEGACY TASK FLOW] Attempting to extract JSON from: {result_str[:100]}...")
                            try:
                                # Try to extract JSON from markdown code block
                                if "```json" in result_str:
                                    json_text = result_str.split("```json")[1].split("```")[0].strip()
                                    plan = json.loads(json_text)
                                    print(f"[LEGACY TASK FLOW] Plan extracted from json code block: {json.dumps(plan, indent=2)}")
                                elif "```" in result_str:
                                    json_text = result_str.split("```")[1].split("```")[0].strip()
                                    plan = json.loads(json_text)
                                    print(f"[LEGACY TASK FLOW] Plan extracted from code block: {json.dumps(plan, indent=2)}")
                                else:
                                    # Fallback to creating a simple plan
                                    raise ValueError("No code block found")
                            except (ValueError, json.JSONDecodeError, IndexError):
                                # Fallback to creating a simple plan
                                print(f"[LEGACY TASK FLOW] Failed to parse JSON from result: {result_str}")
                                plan = {
                                    "plan": [
                                        {
                                            "subtask": self.task.description,
                                            "agent_id": list(self.agents.keys())[0],
                                            "reasoning": "Fallback plan due to JSON parsing error"
                                        }
                                    ]
                                }
                                print(f"[LEGACY TASK FLOW] Created fallback plan: {json.dumps(plan, indent=2)}")
                    else:
                        # The result might be wrapped in Markdown code block
                        result_str = str(plan_result)
                        print(f"[LEGACY TASK FLOW] Attempting to extract JSON from: {result_str[:100]}...")
                        try:
                            # Try to extract JSON from markdown code block
                            if "```json" in result_str:
                                json_text = result_str.split("```json")[1].split("```")[0].strip()
                                plan = json.loads(json_text)
                                print(f"[LEGACY TASK FLOW] Plan extracted from json code block: {json.dumps(plan, indent=2)}")
                            elif "```" in result_str:
                                json_text = result_str.split("```")[1].split("```")[0].strip()
                                plan = json.loads(json_text)
                                print(f"[LEGACY TASK FLOW] Plan extracted from code block: {json.dumps(plan, indent=2)}")
                            else:
                                # Fallback to creating a simple plan
                                raise ValueError("No code block found")
                        except (ValueError, json.JSONDecodeError, IndexError):
                            # Fallback to creating a simple plan
                            print(f"[LEGACY TASK FLOW] Failed to parse plan result: {str(plan_result)}")
                            plan = {
                                "plan": [
                                    {
                                        "subtask": self.task.description,
                                        "agent_id": list(self.agents.keys())[0],
                                        "reasoning": "Fallback plan due to JSON parsing error"
                                    }
                                ]
                            }
                            print(f"[LEGACY TASK FLOW] Created fallback plan: {json.dumps(plan, indent=2)}")
                
                # Add plan to task messages
                plan_message = TaskMessage(
                    task_id=self.task.id,
                    content=f"Task Plan Created:\n{json.dumps(plan, indent=2)}",
                    is_system=True
                )
                self.db.add(plan_message)
                self.db.commit()
                
                # Execute each subtask with the appropriate agent
                print(f"[LEGACY TASK FLOW] Starting execution of {len(plan['plan'])} subtasks")
                agent_responses = []
                for idx, subtask in enumerate(plan["plan"]):
                    print(f"[LEGACY TASK FLOW] Executing subtask {idx+1}: {subtask['subtask']}")
                    subtask_message = TaskMessage(
                        task_id=self.task.id,
                        content=f"Executing subtask {idx+1}: {subtask['subtask']}",
                        is_system=True
                    )
                    self.db.add(subtask_message)
                    self.db.commit()
                    
                    # Get agent details
                    agent_id = subtask["agent_id"]
                    print(f"[LEGACY TASK FLOW] Using agent: {agent_id}")
                    agent_info = self.agents.get(agent_id)
                    if not agent_info:
                        error_msg = f"Agent with ID {agent_id} not found in crew"
                        print(f"[LEGACY TASK FLOW] ERROR: {error_msg}")
                        self._add_error_message(error_msg)
                        continue
                    
                    # Execute subtask with Copilot Studio agent
                    try:
                        # Use agent call tracker for telemetry
                        print(f"[LEGACY TASK FLOW] Sending request to agent {agent_info['agent'].name}")
                        with AgentCallTracker(
                            agent_id=agent_id,
                            agent_name=agent_info["agent"].name,
                            input_message=subtask["subtask"]
                        ) as agent_tracker:
                            # Create client with agent-specific secret
                            client = CopilotStudioClient(agent_info["agent"].direct_line_secret)
                            response = await client.send_message(
                                agent_id=agent_id,
                                message=subtask["subtask"],
                                conversation_id=f"task_{self.task.id}_subtask_{idx}"
                            )
                            agent_tracker.response = response
                        
                        print(f"[LEGACY TASK FLOW] Received response from agent: {response[:100]}...")
                        
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
                        print(f"[LEGACY TASK FLOW] ERROR: {error_msg}")
                        self._add_error_message(error_msg)
                
                # Aggregate results using LLM
                if agent_responses:
                    print(f"[LEGACY TASK FLOW] Aggregating results from {len(agent_responses)} agent responses")
                    self.task_context["agent_responses"] = json.dumps(agent_responses)
                    
                    # Use LLM call tracker for the aggregation
                    aggregation_result = None
                    with LLMCallTracker(
                        self.llm_model, 
                        "aggregator", 
                        json.dumps(agent_responses)
                    ) as llm_tracker:
                        aggregation_result = await self.kernel.invoke(
                            self.semantic_functions["aggregator"],
                            task_description=self.task_context["task_description"],
                            agent_responses=self.task_context["agent_responses"]
                        )
                        # Update token counts from result if available
                        if hasattr(aggregation_result, 'prompt_tokens'):
                            llm_tracker.prompt_tokens = aggregation_result.prompt_tokens
                        if hasattr(aggregation_result, 'completion_tokens'):
                            llm_tracker.completion_tokens = aggregation_result.completion_tokens
                        llm_tracker.response = str(aggregation_result)
                    
                    print(f"[LEGACY TASK FLOW] Final result: {str(aggregation_result)[:200]}...")
                    
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
                    print(f"[LEGACY TASK FLOW] ERROR: No agent responses were collected")
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
                
                print(f"[LEGACY TASK FLOW] Task execution completed with status: {self.task.status.value}")
                
            except Exception as e:
                print(f"[LEGACY TASK FLOW] ERROR during execution: {str(e)}")
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