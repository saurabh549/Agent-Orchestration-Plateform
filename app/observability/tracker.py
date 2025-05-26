import time
from typing import Optional, Dict, Any
from contextlib import contextmanager

from app.db.session import get_db
from app.observability.crud import ObservabilityCRUD

class LLMCallTracker:
    def __init__(self, model: str, function_name: str, prompt: str):
        self.model = model
        self.function_name = function_name
        self.prompt = prompt
        self.start_time = None
        self.completion = None
        self.error_message = None
        self.completion_tokens = 0
        self.prompt_tokens = len(prompt.split())  # Simple approximation

    def record_completion(self, response: str, tokens: Optional[int] = None):
        self.completion = (response, tokens)

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                self.error_message = str(exc_val)
                
            # Process completion if available
            response = None
            if self.completion:
                response, completion_tokens = self.completion
                self.completion_tokens = completion_tokens if completion_tokens is not None else len(response.split()) if response else 0
            
            elapsed_time = time.time() - self.start_time
            
            # Estimate cost based on model and tokens
            cost = estimate_llm_cost(self.model, self.prompt_tokens, self.completion_tokens)
            
            # Store in database
            db = next(get_db())
            ObservabilityCRUD.create_llm_call(
                db=db,
                model=self.model,
                function_name=self.function_name,
                prompt_tokens=self.prompt_tokens,
                completion_tokens=self.completion_tokens,
                latency=elapsed_time,
                cost=cost,
                status="error" if self.error_message else "success",
                prompt=self.prompt,
                response=response,
                error_message=self.error_message,
            )
        except Exception as e:
            # Log the error but don't raise it to ensure cleanup
            print(f"Error in LLMCallTracker cleanup: {str(e)}")

class AgentExecutionTracker:
    def __init__(self, agent_id: str, agent_name: str, input_message: str, metadata: Optional[Dict[str, Any]] = None):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.input_message = input_message
        self.metadata = metadata
        self.start_time = None
        self.response = None
        self.error_message = None

    def record_response(self, response: str):
        self.response = response

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                self.error_message = str(exc_val)
            
            elapsed_time = time.time() - self.start_time
            
            # Store in database
            db = next(get_db())
            ObservabilityCRUD.create_agent_execution(
                db=db,
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                status="error" if self.error_message else "success",
                latency=elapsed_time,
                input_message=self.input_message,
                output_message=self.response,
                error_message=self.error_message,
                metadata=self.metadata,
            )
        except Exception as e:
            # Log the error but don't raise it to ensure cleanup
            print(f"Error in AgentExecutionTracker cleanup: {str(e)}")

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