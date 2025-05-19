import json
from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.connectors.ai.google.google_ai import GoogleAIPromptExecutionSettings
from semantic_kernel.planners.function_calling_stepwise_planner import FunctionCallingStepwisePlanner, FunctionCallingStepwisePlannerOptions
from semantic_kernel.prompt_template import InputVariable, PromptTemplateConfig

from app.models.task import Task, TaskMessage, TaskStatus
from app.observability.telemetry import LLMCallTracker, TaskExecutionTracker
from app.services.crew_kernel_manager import crew_kernel_manager


async def execute_task_with_crew_kernel(task_id: int, db: Session) -> Dict[str, Any]:
    """
    Execute a task using the crew's Semantic Kernel instance with agent plugins.
    
    Args:
        task_id: Task ID to execute
        db: Database session
        
    Returns:
        Task execution result
    """
    # Get task details
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise ValueError(f"Task with ID {task_id} not found")
    
    print(f"\n[PLUGIN TASK FLOW] Starting execution of task {task.id}: {task.title}")
    
    # Create a task execution tracker
    with TaskExecutionTracker(task.id, task.crew_id, task.description) as task_tracker:
        try:
            # Update task status to in progress
            task.status = TaskStatus.IN_PROGRESS
            task.started_at = datetime.utcnow()
            db.add(task)
            db.commit()
            db.refresh(task)
            
            print(f"[PLUGIN TASK FLOW] Task status updated to IN_PROGRESS")
            
            # Add system message
            system_message = TaskMessage(
                task_id=task.id,
                content=f"Task started: {task.title}",
                is_system=True
            )
            db.add(system_message)
            db.commit()
            
            # Get the crew's kernel
            print(f"[PLUGIN TASK FLOW] Getting crew kernel with registered agent plugins")
            try:
                kernel = await crew_kernel_manager.get_crew_kernel(db, task.crew_id)
                
                # Log available plugins
                plugin_info = crew_kernel_manager.get_crew_plugin_info(task.crew_id)
                print(f"[PLUGIN TASK FLOW] Available plugins: {json.dumps(plugin_info, indent=2)}")
                
                plugin_message = TaskMessage(
                    task_id=task.id,
                    content=f"Available agent plugins:\n{json.dumps(plugin_info, indent=2)}",
                    is_system=True
                )
                db.add(plugin_message)
                db.commit()
            except Exception as kernel_error:
                # Handle kernel initialization errors
                error_msg = f"Failed to initialize kernel: {str(kernel_error)}"
                print(f"[PLUGIN TASK FLOW] ERROR: {error_msg}")
                raise ValueError(error_msg)
            
            # Create orchestration prompt
            print(f"[PLUGIN TASK FLOW] Creating orchestration Plan")
            options = FunctionCallingStepwisePlannerOptions(
                max_iterations=10,
                max_tokens=1000,
            )
            
            # Create the planner with the correct service_id
            planner = FunctionCallingStepwisePlanner(
                service_id="chat_completion",
                options=options
            )
            
            # Execute task orchestration using LLM with plugin function calling
            print(f"[PLUGIN TASK FLOW] Executing orchestration plan - LLM will decide which agent functions to call")
            # Determine which LLM is being used
            llm_model = "gemini-2.0-flash"
                
            with LLMCallTracker(llm_model, "orchestrator", task.description) as llm_tracker:
                result = await planner.invoke(kernel,task.description)
                # Record the result
                llm_tracker.response = str(result)
    
            print(f"[PLUGIN TASK FLOW] Orchestration complete. Result: {str(result)[:200]}...")
            # Add result to task messages
            result_message_content = f"Task Result:\n{result}"
            result_message = TaskMessage(
                task_id=task.id,
                content=result_message_content,
                is_system=True
            )
            db.add(result_message)
            # Update task with the result
            task.result = {"summary": str(result)}
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            db.add(task)
            db.commit()
            
            # Set the result for the task tracker
            task_tracker.result = task.result
            
            print(f"[PLUGIN TASK FLOW] Task execution completed with status: {task.status.value}")
            
            return {"status": "success", "result": str(result)}
            
        except Exception as e:
            # Handle errors
            error_msg = f"Error executing task: {str(e)}"
            print(f"[PLUGIN TASK FLOW] ERROR during execution: {str(e)}")
            
            # Add error message
            error_message = TaskMessage(
                task_id=task.id,
                content=error_msg,
                is_system=True
            )
            db.add(error_message)
            
            # Update task status
            task.status = TaskStatus.FAILED
            task.error = error_msg
            task.completed_at = datetime.utcnow()
            
            db.add(task)
            db.commit()
            
            # Re-raise to ensure the task tracker captures the error
            raise 
