import json
import time
from typing import Dict, Any, Optional
from datetime import datetime

from opentelemetry import trace
from opentelemetry.trace.span import Span
from prometheus_client import Counter, Histogram, Gauge

# Prometheus metrics for LLM and Agent calls
LLM_CALL_COUNT = Counter(
    "llm_calls_total",
    "Total count of LLM API calls",
    ["model", "function_name", "status"]
)

LLM_TOKEN_COUNT = Counter(
    "llm_tokens_total", 
    "Total token usage for LLM calls",
    ["model", "type"]  # type can be "prompt" or "completion"
)

LLM_LATENCY = Histogram(
    "llm_latency_seconds",
    "LLM call latency in seconds",
    ["model", "function_name"]
)

LLM_COST = Counter(
    "llm_cost_total",
    "Estimated cost of LLM API calls in USD",
    ["model"]
)

AGENT_CALL_COUNT = Counter(
    "agent_calls_total",
    "Total count of agent API calls",
    ["agent_id", "agent_name", "status"]
)

AGENT_LATENCY = Histogram(
    "agent_latency_seconds",
    "Agent call latency in seconds",
    ["agent_id", "agent_name"]
)

TASK_EXECUTION_GAUGE = Gauge(
    "tasks_in_progress",
    "Number of tasks currently in progress"
)

# Token cost estimates (per 1K tokens) - update as needed
TOKEN_COSTS = {
    "gpt-4": {"prompt": 0.03, "completion": 0.06},
    "gpt-3.5-turbo": {"prompt": 0.0015, "completion": 0.002}
}

class LLMTelemetry:
    """Helper class for tracking LLM call telemetry"""
    
    @staticmethod
    def start_span(model: str, function_name: str, prompt: str) -> Span:
        """Start a span for an LLM call and return the span"""
        tracer = trace.get_tracer(__name__)
        span = tracer.start_span(f"llm_call.{function_name}")
        
        # Set span attributes
        span.set_attribute("llm.model", model)
        span.set_attribute("llm.function", function_name)
        span.set_attribute("llm.prompt_length", len(prompt))
        span.set_attribute("llm.timestamp", datetime.utcnow().isoformat())
        
        return span
    
    @staticmethod
    def end_span(
        span: Span, 
        success: bool, 
        model: str,
        function_name: str,
        prompt_tokens: int, 
        completion_tokens: int, 
        duration: float,
        response: Optional[str] = None,
        error: Optional[str] = None
    ) -> None:
        """End an LLM call span with results"""
        # Update span with completion information
        status = "success" if success else "error"
        
        span.set_attribute("llm.status", status)
        span.set_attribute("llm.prompt_tokens", prompt_tokens)
        span.set_attribute("llm.completion_tokens", completion_tokens)
        span.set_attribute("llm.total_tokens", prompt_tokens + completion_tokens)
        span.set_attribute("llm.duration", duration)
        
        if response:
            # Limit response size to avoid huge spans
            span.set_attribute("llm.response", response[:1000] + "..." if len(response) > 1000 else response)
        
        if error:
            span.set_attribute("llm.error", error)
            span.record_exception(Exception(error))
        
        # Record Prometheus metrics
        LLM_CALL_COUNT.labels(model=model, function_name=function_name, status=status).inc()
        LLM_TOKEN_COUNT.labels(model=model, type="prompt").inc(prompt_tokens)
        LLM_TOKEN_COUNT.labels(model=model, type="completion").inc(completion_tokens)
        LLM_LATENCY.labels(model=model, function_name=function_name).observe(duration)
        
        # Calculate and record cost if model is known
        if model.lower() in TOKEN_COSTS:
            prompt_cost = (prompt_tokens / 1000) * TOKEN_COSTS[model.lower()]["prompt"]
            completion_cost = (completion_tokens / 1000) * TOKEN_COSTS[model.lower()]["completion"]
            total_cost = prompt_cost + completion_cost
            LLM_COST.labels(model=model).inc(total_cost)
            span.set_attribute("llm.estimated_cost_usd", total_cost)
        
        # End the span
        span.end()

class AgentTelemetry:
    """Helper class for tracking Agent call telemetry"""
    
    @staticmethod
    def start_span(agent_id: str, agent_name: str, input_message: str) -> Span:
        """Start a span for an Agent call and return the span"""
        tracer = trace.get_tracer(__name__)
        span = tracer.start_span(f"agent_call.{agent_name}")
        
        # Set span attributes
        span.set_attribute("agent.id", agent_id)
        span.set_attribute("agent.name", agent_name) 
        span.set_attribute("agent.input_length", len(input_message))
        span.set_attribute("agent.timestamp", datetime.utcnow().isoformat())
        span.set_attribute("agent.input", input_message[:500] + "..." if len(input_message) > 500 else input_message)
        
        return span
    
    @staticmethod
    def end_span(
        span: Span,
        success: bool,
        agent_id: str,
        agent_name: str,
        duration: float,
        response: Optional[str] = None,
        error: Optional[str] = None
    ) -> None:
        """End an Agent call span with results"""
        # Update span with response information
        status = "success" if success else "error"
        
        span.set_attribute("agent.status", status)
        span.set_attribute("agent.duration", duration)
        
        if response:
            # Limit response size to avoid huge spans
            span.set_attribute("agent.response", response[:1000] + "..." if len(response) > 1000 else response)
            span.set_attribute("agent.response_length", len(response))
        
        if error:
            span.set_attribute("agent.error", error)
            span.record_exception(Exception(error))
        
        # Record Prometheus metrics
        AGENT_CALL_COUNT.labels(agent_id=agent_id, agent_name=agent_name, status=status).inc()
        AGENT_LATENCY.labels(agent_id=agent_id, agent_name=agent_name).observe(duration)
        
        # End the span
        span.end()

class TaskTelemetry:
    """Helper class for tracking Task execution telemetry"""
    
    @staticmethod
    def task_started(task_id: int, crew_id: int, task_description: str) -> Span:
        """Start a span for task execution and increment the in-progress gauge"""
        tracer = trace.get_tracer(__name__)
        span = tracer.start_span(f"task_execution.{task_id}")
        
        # Set span attributes
        span.set_attribute("task.id", task_id)
        span.set_attribute("task.crew_id", crew_id)
        span.set_attribute("task.description", task_description[:500] + "..." if len(task_description) > 500 else task_description)
        span.set_attribute("task.start_time", datetime.utcnow().isoformat())
        
        # Increment gauge for tasks in progress
        TASK_EXECUTION_GAUGE.inc()
        
        return span
    
    @staticmethod
    def task_completed(
        span: Span,
        task_id: int,
        success: bool,
        duration: float,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> None:
        """End a task execution span and decrement the in-progress gauge"""
        # Update span with completion information
        status = "success" if success else "error"
        
        span.set_attribute("task.status", status)
        span.set_attribute("task.duration", duration)
        span.set_attribute("task.end_time", datetime.utcnow().isoformat())
        
        if result:
            # Limit result size to avoid huge spans
            result_str = json.dumps(result)
            span.set_attribute("task.result", result_str[:1000] + "..." if len(result_str) > 1000 else result_str)
        
        if error:
            span.set_attribute("task.error", error)
            span.record_exception(Exception(error))
        
        # Decrement gauge for tasks in progress
        TASK_EXECUTION_GAUGE.dec()
        
        # End the span
        span.end()

# Context manager for LLM calls
class LLMCallTracker:
    """Context manager for tracking LLM API calls"""
    
    def __init__(self, model: str, function_name: str, prompt: str):
        self.model = model
        self.function_name = function_name
        self.prompt = prompt
        self.start_time = None
        self.span = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.span = LLMTelemetry.start_span(self.model, self.function_name, self.prompt)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        success = exc_type is None
        
        # If we have token counts, use them, otherwise estimate
        prompt_tokens = getattr(self, 'prompt_tokens', len(self.prompt) // 4)  # Rough estimate
        completion_tokens = getattr(self, 'completion_tokens', 0)
        response = getattr(self, 'response', None)
        
        LLMTelemetry.end_span(
            span=self.span,
            success=success,
            model=self.model,
            function_name=self.function_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration=duration,
            response=response,
            error=str(exc_val) if exc_val else None
        )
        
        # Don't suppress exceptions
        return False

# Context manager for Agent calls
class AgentCallTracker:
    """Context manager for tracking Agent API calls"""
    
    def __init__(self, agent_id: str, agent_name: str, input_message: str):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.input_message = input_message
        self.start_time = None
        self.span = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.span = AgentTelemetry.start_span(self.agent_id, self.agent_name, self.input_message)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        success = exc_type is None
        response = getattr(self, 'response', None)
        
        AgentTelemetry.end_span(
            span=self.span,
            success=success,
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            duration=duration,
            response=response,
            error=str(exc_val) if exc_val else None
        )
        
        # Don't suppress exceptions
        return False

# Context manager for Task execution
class TaskExecutionTracker:
    """Context manager for tracking Task execution"""
    
    def __init__(self, task_id: int, crew_id: int, task_description: str):
        self.task_id = task_id
        self.crew_id = crew_id
        self.task_description = task_description
        self.start_time = None
        self.span = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.span = TaskTelemetry.task_started(self.task_id, self.crew_id, self.task_description)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        success = exc_type is None
        result = getattr(self, 'result', None)
        
        TaskTelemetry.task_completed(
            span=self.span,
            task_id=self.task_id,
            success=success,
            duration=duration,
            result=result,
            error=str(exc_val) if exc_val else None
        )
        
        # Don't suppress exceptions
        return False 