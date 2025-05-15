import json
from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

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
    
    # Create a task execution tracker
    with TaskExecutionTracker(task.id, task.crew_id, task.description) as task_tracker:
        try:
            # Update task status to in progress
            task.status = TaskStatus.IN_PROGRESS
            task.started_at = datetime.utcnow()
            db.add(task)
            db.commit()
            db.refresh(task)
            
            # Add system message
            system_message = TaskMessage(
                task_id=task.id,
                content=f"Task started: {task.title}",
                is_system=True
            )
            db.add(system_message)
            db.commit()
            
            # Get the crew's kernel
            kernel = await crew_kernel_manager.get_crew_kernel(db, task.crew_id)
            
            # Log available plugins
            plugin_info = crew_kernel_manager.get_crew_plugin_info(task.crew_id)
            plugin_message = TaskMessage(
                task_id=task.id,
                content=f"Available agent plugins:\n{json.dumps(plugin_info, indent=2)}",
                is_system=True
            )
            db.add(plugin_message)
            db.commit()
            
            # Create orchestration prompt
            orchestrator_prompt = """
            You are an AI task orchestrator responsible for solving complex tasks by using specialized AI agents.
            
            TASK DESCRIPTION:
            {{$task_description}}
            
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
            orchestrator = kernel.create_function_from_prompt(
                function_name="task_orchestrator",
                prompt=orchestrator_prompt,
                description="Orchestrates complex tasks by delegating to specialized agents"
            )
            
            # Prepare kernel context with task details
            context = kernel.create_new_context()
            context["task_description"] = task.description
            
            # Execute task orchestration using LLM with plugin function calling
            llm_model = "azure-gpt-4" if hasattr(kernel, "azure_chat_service") else "gpt-4"
            with LLMCallTracker(llm_model, "orchestrator", task.description) as llm_tracker:
                result = await orchestrator.invoke(context=context)
                # Record the result
                llm_tracker.response = str(result)
            
            # Add result to task messages
            result_message = TaskMessage(
                task_id=task.id,
                content=f"Task Result:\n{result}",
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
            
            return {"status": "success", "result": str(result)}
            
        except Exception as e:
            # Handle errors
            error_msg = f"Error executing task: {str(e)}"
            
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