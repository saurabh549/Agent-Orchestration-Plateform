import time
from typing import Callable

from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from prometheus_client import Counter, Histogram, generate_latest

from app.core.config import settings
from app.db.base import engine

# Prometheus metrics
REQUEST_COUNT = Counter(
    "api_requests_total",
    "Total count of API requests",
    ["method", "endpoint", "status_code"]
)

REQUEST_LATENCY = Histogram(
    "api_request_latency_seconds",
    "Request latency in seconds",
    ["method", "endpoint"]
)

TASK_COUNT = Counter(
    "task_creation_total",
    "Total count of tasks created",
    ["status"]
)

AGENT_USAGE = Counter(
    "agent_usage_total",
    "Total count of agent usage in tasks",
    ["agent_id", "agent_name"]
)

def setup_observability(app: FastAPI) -> None:
    """Set up observability for the FastAPI application."""
    
    # Only set up OpenTelemetry if endpoint is configured
    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        # Set up OpenTelemetry
        resource = Resource(attributes={
            SERVICE_NAME: settings.PROJECT_NAME
        })
        
        tracer_provider = TracerProvider(resource=resource)
        
        # Configure exporter
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT
        )
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)
        
        trace.set_tracer_provider(tracer_provider)
        
        # Instrument FastAPI
        FastAPIInstrumentor.instrument_app(app)
        
        # Instrument SQLAlchemy
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            service=settings.PROJECT_NAME,
        )
        
        # Create a span for recording task executions
        tracer = trace.get_tracer(__name__)
        
        # This function will be used in task_executor.py to record task execution spans
        def record_task_execution(task_id: int, crew_id: int, description: str):
            with tracer.start_as_current_span(
                name=f"task_execution_{task_id}",
                attributes={
                    "task.id": task_id,
                    "crew.id": crew_id,
                    "task.description": description
                }
            ) as span:
                # The span will be automatically ended when the context is exited
                pass
        
        # Attach the function to app.state so it can be accessed from other parts of the app
        app.state.record_task_execution = record_task_execution
    else:
        # Add a no-op implementation when OpenTelemetry is disabled
        def noop_record_task_execution(task_id: int, crew_id: int, description: str):
            pass
        
        app.state.record_task_execution = noop_record_task_execution
    
    # Add middleware for metrics
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # Get request path without query params for metrics
        request_path = request.url.path
        
        # Process the request
        response = await call_next(request)
        
        # Record metrics
        status_code = response.status_code
        elapsed_time = time.time() - start_time
        REQUEST_COUNT.labels(
            method=request.method, 
            endpoint=request_path, 
            status_code=status_code
        ).inc()
        
        REQUEST_LATENCY.labels(
            method=request.method, 
            endpoint=request_path
        ).observe(elapsed_time)
        
        return response
    
    # Add Prometheus metrics endpoint
    @app.get(settings.PROMETHEUS_ENDPOINT)
    async def metrics():
        return Response(content=generate_latest(), media_type="text/plain") 