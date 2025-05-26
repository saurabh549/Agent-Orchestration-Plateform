import time
from typing import Optional, Dict, Any
from contextlib import contextmanager

from app.db.session import get_db
from app.observability.crud import ObservabilityCRUD

class AnalyticsTracker:
    """Utility class for tracking LLM and agent calls"""

    @staticmethod
    @contextmanager
    def track_llm_call(
        model: str,
        function_name: str,
        prompt: str,
    ):
        """
        Context manager to track LLM API calls.
        Usage:
            with AnalyticsTracker.track_llm_call("gpt-4", "generate_response", prompt) as tracker:
                response = llm.generate(prompt)
                tracker.record_completion(response)
        """
        start_time = time.time()
        completion_tokens = 0
        prompt_tokens = len(prompt.split())  # Simple approximation
        error_message = None
        response = None

        try:
            yield lambda response, tokens=None: setattr(tracker, 'completion', (response, tokens))
            
            # After the context, get the completion
            if hasattr(tracker, 'completion'):
                response, completion_tokens = tracker.completion
                if completion_tokens is None:
                    completion_tokens = len(response.split()) if response else 0
            
        except Exception as e:
            error_message = str(e)
            raise
        finally:
            elapsed_time = time.time() - start_time
            
            # Estimate cost based on model and tokens
            cost = estimate_llm_cost(model, prompt_tokens, completion_tokens)
            
            # Store in database
            db = next(get_db())
            ObservabilityCRUD.create_llm_call(
                db=db,
                model=model,
                function_name=function_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency=elapsed_time,
                cost=cost,
                status="error" if error_message else "success",
                prompt=prompt,
                response=response,
                error_message=error_message,
            )

    @staticmethod
    @contextmanager
    def track_agent_execution(
        agent_id: str,
        agent_name: str,
        input_message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Context manager to track agent executions.
        Usage:
            with AnalyticsTracker.track_agent_execution("agent123", "code_assistant", input_msg) as tracker:
                response = agent.execute(input_msg)
                tracker.record_response(response)
        """
        start_time = time.time()
        error_message = None
        output_message = None

        try:
            yield lambda response: setattr(tracker, 'response', response)
            
            # After the context, get the response
            if hasattr(tracker, 'response'):
                output_message = tracker.response
            
        except Exception as e:
            error_message = str(e)
            raise
        finally:
            elapsed_time = time.time() - start_time
            
            # Store in database
            db = next(get_db())
            ObservabilityCRUD.create_agent_execution(
                db=db,
                agent_id=agent_id,
                agent_name=agent_name,
                status="error" if error_message else "success",
                latency=elapsed_time,
                input_message=input_message,
                output_message=output_message,
                error_message=error_message,
                metadata=metadata,
            )

def estimate_llm_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate cost based on token usage and model"""
    # Cost per 1K tokens (you can update these based on your actual costs)
    costs = {
        "gpt-4": {"prompt": 0.03, "completion": 0.06},
        "gpt-3.5-turbo": {"prompt": 0.0015, "completion": 0.002},
        # Add more models as needed
    }
    
    if model.lower() not in costs:
        return 0.0
    
    model_costs = costs[model.lower()]
    prompt_cost = (prompt_tokens / 1000) * model_costs["prompt"]
    completion_cost = (completion_tokens / 1000) * model_costs["completion"]
    
    return prompt_cost + completion_cost 