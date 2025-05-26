from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.db.session import get_db
from app.observability.crud import ObservabilityCRUD
from app.observability.models import LLMCall, AgentExecution

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# LLM Analytics Endpoints
@router.get("/llm/usage")
def get_llm_usage_stats(
    start_time: datetime = Query(default_factory=lambda: datetime.utcnow() - timedelta(days=7)),
    end_time: datetime = Query(default_factory=lambda: datetime.utcnow()),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get LLM usage statistics including costs, tokens, and model distribution."""
    return ObservabilityCRUD.get_llm_usage_stats(db, start_time, end_time)

@router.get("/llm/recent-calls")
def get_recent_llm_calls(
    limit: int = Query(default=10, le=100),
    model: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Get recent LLM calls with optional filtering by model and status."""
    query = db.query(LLMCall).order_by(desc(LLMCall.timestamp))
    
    if model:
        query = query.filter(LLMCall.model == model)
    if status:
        query = query.filter(LLMCall.status == status)
    
    calls = query.limit(limit).all()
    return [
        {
            "id": call.id,
            "model": call.model,
            "function_name": call.function_name,
            "prompt_tokens": call.prompt_tokens,
            "completion_tokens": call.completion_tokens,
            "latency": call.latency,
            "cost": call.cost,
            "status": call.status,
            "timestamp": call.timestamp,
        }
        for call in calls
    ]

@router.get("/llm/cost-analysis")
def get_llm_cost_analysis(
    start_time: datetime = Query(default_factory=lambda: datetime.utcnow() - timedelta(days=30)),
    end_time: datetime = Query(default_factory=lambda: datetime.utcnow()),
    group_by: str = Query(default="model", enum=["model", "function_name"]),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get detailed cost analysis of LLM usage grouped by model or function."""
    costs = db.query(
        getattr(LLMCall, group_by),
        func.sum(LLMCall.cost).label("total_cost"),
        func.count(LLMCall.id).label("call_count"),
        func.avg(LLMCall.latency).label("avg_latency")
    ).filter(
        LLMCall.timestamp.between(start_time, end_time)
    ).group_by(
        getattr(LLMCall, group_by)
    ).all()

    return {
        "time_period": {
            "start": start_time,
            "end": end_time
        },
        "grouped_by": group_by,
        "data": [
            {
                group_by: getattr(item, group_by),
                "total_cost": float(item.total_cost),
                "call_count": item.call_count,
                "avg_latency": float(item.avg_latency)
            }
            for item in costs
        ]
    }

# Agent Analytics Endpoints
@router.get("/agents/performance")
def get_agent_performance_stats(
    start_time: datetime = Query(default_factory=lambda: datetime.utcnow() - timedelta(days=7)),
    end_time: datetime = Query(default_factory=lambda: datetime.utcnow()),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get agent performance statistics including success rates and latencies."""
    return ObservabilityCRUD.get_agent_performance_stats(db, start_time, end_time)

@router.get("/agents/recent-executions")
def get_recent_agent_executions(
    limit: int = Query(default=10, le=100),
    agent_name: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Get recent agent executions with optional filtering."""
    query = db.query(AgentExecution).order_by(desc(AgentExecution.timestamp))
    
    if agent_name:
        query = query.filter(AgentExecution.agent_name == agent_name)
    if status:
        query = query.filter(AgentExecution.status == status)
    
    executions = query.limit(limit).all()
    return [
        {
            "id": exec.id,
            "agent_id": exec.agent_id,
            "agent_name": exec.agent_name,
            "status": exec.status,
            "latency": exec.latency,
            "timestamp": exec.timestamp,
            "metadata": exec.metadata
        }
        for exec in executions
    ] 