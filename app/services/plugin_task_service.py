import json
from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session
from semantic_kernel.functions.kernel_arguments import KernelArguments

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
                
                # Create a list to store agent responses
                agent_responses = []
                
                # Set up execution listeners to log when functions are called
                original_functions = {}
                for plugin_name, plugin in kernel.plugins.items():
                    for fn_name, fn in plugin.functions.items():
                        original_function = fn.method
                        
                        # Create a wrapper to log function calls
                        async def function_logger_wrapper(original_fn, plugin_name, fn_name, *args, **kwargs):
                            print(f"[PLUGIN TASK FLOW] Agent function called: {plugin_name}.{fn_name}")
                            print(f"[PLUGIN TASK FLOW] Arguments: {args}, {kwargs}")
                            
                            # Extract the message from kwargs or args
                            message = kwargs.get('message', '')
                            if not message and args:
                                message = args[0]
                            
                            # Add a message to the task
                            agent_call_message = TaskMessage(
                                task_id=task.id,
                                content=f"Called agent function: {plugin_name}.{fn_name}\nRequest: {message}",
                                is_system=True
                            )
                            db.add(agent_call_message)
                            db.commit()
                            
                            # Call the original function
                            result = await original_fn(*args, **kwargs)
                            
                            # Add the result to the task
                            agent_result_message = TaskMessage(
                                task_id=task.id,
                                content=f"Agent response from {plugin_name}.{fn_name}:\n{result}",
                                is_system=True
                            )
                            db.add(agent_result_message)
                            db.commit()
                            
                            # Store the response for the final result
                            agent_responses.append({
                                "plugin": plugin_name,
                                "function": fn_name,
                                "request": message,
                                "response": result
                            })
                            
                            print(f"[PLUGIN TASK FLOW] Agent function result: {str(result)[:100]}...")
                            return result
                        
                        # Store the original function
                        original_functions[(plugin_name, fn_name)] = original_function
                        
                        # Replace with our wrapper
                        import functools
                        fn.method = functools.partial(
                            function_logger_wrapper, 
                            original_function,
                            plugin_name,
                            fn_name
                        )
            except Exception as kernel_error:
                # Handle kernel initialization errors
                error_msg = f"Failed to initialize kernel: {str(kernel_error)}"
                print(f"[PLUGIN TASK FLOW] ERROR: {error_msg}")
                raise ValueError(error_msg)
            
            # Create orchestration prompt
            print(f"[PLUGIN TASK FLOW] Creating orchestration function")
            orchestrator_prompt = """
            You are an AI task orchestrator responsible for solving complex tasks by using specialized AI agents.
            
            TASK DESCRIPTION:
            {{$task_description}}
            
            Your job is to solve this task by using the available agent functions. Each agent has specific capabilities.
            You can ask agents questions, give them subtasks, and use their responses to build a comprehensive solution.
            
            IMPORTANT: You MUST directly call the agent functions that are available to you. DO NOT just plan to call functions
            or write hypothetical code blocks. Instead, actually invoke the functions to get responses from the agents.
            
            For example, if you have an agent function named "ask_researcher", you should directly call it like:
            ask_researcher("What is the history of OpenAI?")
            
            Think step by step:
            1. Break down the task into logical steps
            2. For each step, decide which agent would be best suited to handle it
            3. IMMEDIATELY call the appropriate agent function with a clear, specific request - don't just write what you would call
            4. Use the agent's response in your solution
            5. If needed, ask follow-up questions to the same or different agents
            
            Provide a comprehensive final answer that fully addresses the original task, incorporating the actual responses
            from the agents you called.
            """
            
            # Create the orchestrator function
            orchestrator = kernel.add_function(
                plugin_name="task_orchestrator",
                function_name="task_orchestrator",
                description="Orchestrates complex tasks by delegating to specialized agents",
                prompt=orchestrator_prompt
            )
            
            # Prepare kernel context with task details
            context = KernelArguments()
            context["task_description"] = task.description
            
            # Execute task orchestration using LLM with plugin function calling
            print(f"[PLUGIN TASK FLOW] Executing orchestration - LLM will decide which agent functions to call")
            
            # Determine which LLM is being used
            llm_model = "unknown"
            if hasattr(kernel, "azure_chat_service"):
                llm_model = "azure-gpt-4"
            elif hasattr(kernel, "gemini"):
                llm_model = "gemini-2.0-flash"
            else:
                llm_model = "gpt-4"
                
            with LLMCallTracker(llm_model, "orchestrator", task.description) as llm_tracker:
                # Pass kernel as first parameter and use context for task_description
                result = await orchestrator.invoke(kernel, context)
                # Record the result
                llm_tracker.response = str(result)
            
            print(f"[PLUGIN TASK FLOW] Orchestration complete. Result: {str(result)[:200]}...")
            
            # Add result to task messages
            result_message_content = f"Task Result:\n{result}"
            
            # Add agent interaction summary if any
            if agent_responses:
                result_message_content += "\n\n=== Agent Interactions ===\n"
                for idx, resp in enumerate(agent_responses, 1):
                    result_message_content += f"\n{idx}. Asked {resp['plugin']}.{resp['function']}: {resp['request'][:50]}...\n"
                    result_message_content += f"   Response: {resp['response'][:100]}...\n"
            
            result_message = TaskMessage(
                task_id=task.id,
                content=result_message_content,
                is_system=True
            )
            db.add(result_message)
            
            # Update task with the result
            task.result = {"summary": str(result), "agent_responses": agent_responses}
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