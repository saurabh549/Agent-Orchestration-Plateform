from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.db.session import get_db
from app.observability.models import LLMCall, AgentExecution

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# Dashboard Overview
@router.get("/dashboard")
def get_dashboard_overview(
    start_time: datetime = Query(default_factory=lambda: datetime.utcnow() - timedelta(days=7)),
    end_time: datetime = Query(default_factory=lambda: datetime.utcnow()),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get an overview of system usage including LLM and Agent metrics.
    Default time range is the last 7 days.
    """
    # LLM Overview
    llm_stats = db.query(
        func.count(LLMCall.id).label("total_calls"),
        func.sum(LLMCall.cost).label("total_cost"),
        func.avg(LLMCall.latency).label("avg_latency"),
        func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens).label("total_tokens")
    ).filter(
        LLMCall.timestamp.between(start_time, end_time)
    ).first()

    # Agent Overview
    agent_stats = db.query(
        func.count(AgentExecution.id).label("total_executions"),
        func.avg(AgentExecution.latency).label("avg_latency"),
        func.count(case([
            (AgentExecution.status == "success", 1)
        ])).label("successful_executions")
    ).filter(
        AgentExecution.timestamp.between(start_time, end_time)
    ).first()

    return {
        "time_period": {
            "start": start_time,
            "end": end_time
        },
        "llm_overview": {
            "total_calls": llm_stats.total_calls or 0,
            "total_cost": float(llm_stats.total_cost or 0),
            "avg_latency": float(llm_stats.avg_latency or 0),
            "total_tokens": int(llm_stats.total_tokens or 0)
        },
        "agent_overview": {
            "total_executions": agent_stats.total_executions or 0,
            "success_rate": (agent_stats.successful_executions or 0) / (agent_stats.total_executions or 1),
            "avg_latency": float(agent_stats.avg_latency or 0)
        }
    }

# LLM Analytics
@router.get("/llm/usage")
def get_llm_usage(
    start_time: datetime = Query(default_factory=lambda: datetime.utcnow() - timedelta(days=7)),
    end_time: datetime = Query(default_factory=lambda: datetime.utcnow()),
    model: Optional[str] = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get detailed LLM usage statistics with optional model filtering.
    """
    query = db.query(LLMCall).filter(LLMCall.timestamp.between(start_time, end_time))
    if model:
        query = query.filter(LLMCall.model == model)

    # Model distribution
    model_usage = db.query(
        LLMCall.model,
        func.count(LLMCall.id).label("calls"),
        func.sum(LLMCall.cost).label("total_cost"),
        func.avg(LLMCall.latency).label("avg_latency")
    ).filter(
        LLMCall.timestamp.between(start_time, end_time)
    ).group_by(LLMCall.model).all()

    return {
        "time_period": {
            "start": start_time,
            "end": end_time
        },
        "total_calls": query.count(),
        "total_cost": float(query.with_entities(func.sum(LLMCall.cost)).scalar() or 0),
        "avg_latency": float(query.with_entities(func.avg(LLMCall.latency)).scalar() or 0),
        "model_distribution": [
            {
                "model": item.model,
                "calls": item.calls,
                "total_cost": float(item.total_cost or 0),
                "avg_latency": float(item.avg_latency or 0)
            }
            for item in model_usage
        ]
    }

@router.get("/llm/recent")
def get_recent_llm_calls(
    limit: int = Query(default=10, le=100),
    model: Optional[str] = None,
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Get recent LLM calls with optional model filtering.
    """
    query = db.query(LLMCall).order_by(desc(LLMCall.timestamp))
    if model:
        query = query.filter(LLMCall.model == model)
    
    calls = query.limit(limit).all()
    return [
        {
            "id": call.id,
            "timestamp": call.timestamp,
            "model": call.model,
            "function_name": call.function_name,
            "tokens": call.prompt_tokens + call.completion_tokens,
            "cost": call.cost,
            "latency": call.latency,
            "status": call.status
        }
        for call in calls
    ]

# Agent Analytics
@router.get("/agents/performance")
def get_agent_performance(
    start_time: datetime = Query(default_factory=lambda: datetime.utcnow() - timedelta(days=7)),
    end_time: datetime = Query(default_factory=lambda: datetime.utcnow()),
    agent_name: Optional[str] = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get detailed agent performance statistics with optional agent filtering.
    """
    query = db.query(AgentExecution).filter(
        AgentExecution.timestamp.between(start_time, end_time)
    )
    if agent_name:
        query = query.filter(AgentExecution.agent_name == agent_name)

    # Agent performance by name
    agent_stats = db.query(
        AgentExecution.agent_name,
        func.count(AgentExecution.id).label("total_executions"),
        func.count(case([
            (AgentExecution.status == "success", 1)
        ])).label("successful_executions"),
        func.avg(AgentExecution.latency).label("avg_latency")
    ).filter(
        AgentExecution.timestamp.between(start_time, end_time)
    ).group_by(AgentExecution.agent_name).all()

    return {
        "time_period": {
            "start": start_time,
            "end": end_time
        },
        "total_executions": query.count(),
        "success_rate": query.filter(AgentExecution.status == "success").count() / query.count() if query.count() > 0 else 0,
        "avg_latency": float(query.with_entities(func.avg(AgentExecution.latency)).scalar() or 0),
        "agent_performance": [
            {
                "agent_name": item.agent_name,
                "total_executions": item.total_executions,
                "success_rate": item.successful_executions / item.total_executions if item.total_executions > 0 else 0,
                "avg_latency": float(item.avg_latency or 0)
            }
            for item in agent_stats
        ]
    }

@router.get("/agents/recent")
def get_recent_agent_executions(
    limit: int = Query(default=10, le=100),
    agent_name: Optional[str] = None,
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Get recent agent executions with optional agent filtering.
    """
    query = db.query(AgentExecution).order_by(desc(AgentExecution.timestamp))
    if agent_name:
        query = query.filter(AgentExecution.agent_name == agent_name)
    
    executions = query.limit(limit).all()
    return [
        {
            "id": exec.id,
            "timestamp": exec.timestamp,
            "agent_name": exec.agent_name,
            "agent_id": exec.agent_id,
            "latency": exec.latency,
            "status": exec.status,
            "metadata": exec.metadata
        }
        for exec in executions
    ] 