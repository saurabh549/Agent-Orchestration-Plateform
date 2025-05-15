from typing import Any, List, Dict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from prometheus_client import generate_latest, REGISTRY

from app.db.deps import get_db, get_current_user
from app.models.task import Task, TaskStatus
from app.models.crew import AgentCrew, CrewMember
from app.models.agent import Agent
from app.models.user import User
from app.observability.telemetry import (
    LLM_CALL_COUNT, LLM_TOKEN_COUNT, LLM_LATENCY, LLM_COST,
    AGENT_CALL_COUNT, AGENT_LATENCY, TASK_EXECUTION_GAUGE
)

router = APIRouter()

@router.get("/dashboard", response_model=Dict[str, Any])
def get_dashboard_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = 30,
) -> Any:
    """
    Get dashboard metrics for the current user.
    """
    # Get date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Get task counts by status
    task_status_counts = (
        db.query(Task.status, func.count(Task.id))
        .filter(Task.creator_id == current_user.id)
        .group_by(Task.status)
        .all()
    )
    
    status_counts = {
        status.value: 0 
        for status in TaskStatus
    }
    
    for status, count in task_status_counts:
        status_counts[status.value] = count
    
    # Get task completion rate
    total_completed = status_counts[TaskStatus.COMPLETED.value]
    total_failed = status_counts[TaskStatus.FAILED.value]
    total_finished = total_completed + total_failed
    completion_rate = (total_completed / total_finished) * 100 if total_finished > 0 else 0
    
    # Get average task completion time
    avg_completion_time = (
        db.query(func.avg(Task.completed_at - Task.started_at))
        .filter(
            Task.creator_id == current_user.id,
            Task.status == TaskStatus.COMPLETED,
            Task.completed_at.isnot(None),
            Task.started_at.isnot(None)
        )
        .scalar()
    )
    
    # Get task count by day
    daily_task_counts = (
        db.query(
            func.date(Task.created_at).label("date"),
            func.count(Task.id).label("count")
        )
        .filter(
            Task.creator_id == current_user.id,
            Task.created_at >= start_date
        )
        .group_by(func.date(Task.created_at))
        .all()
    )
    
    # Format as list of {date, count} objects
    daily_counts = [
        {"date": str(date), "count": count}
        for date, count in daily_task_counts
    ]
    
    # Get crew performance metrics
    crew_performance = (
        db.query(
            AgentCrew.name,
            func.count(Task.id).label("total_tasks"),
            func.sum(
                case(
                    (Task.status == TaskStatus.COMPLETED, 1),
                    else_=0
                )
            ).label("completed_tasks")
        )
        .join(Task, Task.crew_id == AgentCrew.id)
        .filter(
            AgentCrew.owner_id == current_user.id,
            Task.creator_id == current_user.id
        )
        .group_by(AgentCrew.id, AgentCrew.name)
        .all()
    )
    
    crew_metrics = [
        {
            "name": name,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks or 0,
            "success_rate": (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        }
        for name, total_tasks, completed_tasks in crew_performance
    ]
    
    # Get agent usage metrics
    agent_usage = (
        db.query(
            Agent.name,
            func.count(Task.id).label("usage_count")
        )
        .join(AgentCrew, AgentCrew.id == Task.crew_id)
        .join(CrewMember, CrewMember.crew_id == AgentCrew.id)
        .join(Agent, Agent.id == CrewMember.agent_id)
        .filter(
            Task.creator_id == current_user.id,
            Task.created_at >= start_date
        )
        .group_by(Agent.id, Agent.name)
        .all()
    )
    
    agent_metrics = [
        {"name": name, "usage_count": count}
        for name, count in agent_usage
    ]
    
    return {
        "task_stats": {
            "status_counts": status_counts,
            "total_tasks": sum(status_counts.values()),
            "completion_rate": completion_rate,
            "avg_completion_time_seconds": avg_completion_time.total_seconds() if avg_completion_time else None,
            "daily_counts": daily_counts
        },
        "crew_performance": crew_metrics,
        "agent_usage": agent_metrics
    }

@router.get("/tasks/stats", response_model=Dict[str, Any])
def get_task_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = 30,
) -> Any:
    """
    Get detailed task statistics for the current user.
    """
    # Get date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Get all tasks in time period
    tasks = (
        db.query(Task)
        .filter(
            Task.creator_id == current_user.id,
            Task.created_at >= start_date
        )
        .all()
    )
    
    # Calculate metrics
    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
    failed_tasks = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
    pending_tasks = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
    in_progress_tasks = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
    
    # Calculate completion times for completed tasks
    completion_times = [
        (t.completed_at - t.started_at).total_seconds()
        for t in tasks
        if t.status == TaskStatus.COMPLETED and t.completed_at and t.started_at
    ]
    
    avg_completion_time = sum(completion_times) / len(completion_times) if completion_times else None
    max_completion_time = max(completion_times) if completion_times else None
    min_completion_time = min(completion_times) if completion_times else None
    
    return {
        "time_period_days": days,
        "total_tasks": total_tasks,
        "task_counts": {
            "completed": completed_tasks,
            "failed": failed_tasks,
            "pending": pending_tasks,
            "in_progress": in_progress_tasks
        },
        "completion_rate": (completed_tasks / (completed_tasks + failed_tasks) * 100) 
                           if (completed_tasks + failed_tasks) > 0 else None,
        "completion_times": {
            "average_seconds": avg_completion_time,
            "max_seconds": max_completion_time,
            "min_seconds": min_completion_time
        }
    }

@router.get("/telemetry", response_model=Dict[str, Any])
def get_telemetry_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get telemetry metrics for LLM calls, agent calls, and task execution.
    This provides a specialized dashboard-friendly format of metrics.
    """
    # Prepare data structure for metrics
    llm_metrics = {
        "call_count": {},
        "token_count": {
            "prompt": {},
            "completion": {},
            "total": {}
        },
        "latency": {
            "avg": {},
            "max": {},
            "p95": {}
        },
        "cost": {}
    }
    
    agent_metrics = {
        "call_count": {},
        "latency": {
            "avg": {},
            "max": {}
        },
        "success_rate": {}
    }
    
    # Extract metrics from Prometheus registry for LLM calls
    for metric in REGISTRY.collect():
        if metric.name == "llm_calls_total":
            for sample in metric.samples:
                model = sample.labels.get("model", "unknown")
                function = sample.labels.get("function_name", "unknown")
                status = sample.labels.get("status", "unknown")
                key = f"{model}:{function}"
                
                if key not in llm_metrics["call_count"]:
                    llm_metrics["call_count"][key] = {"total": 0, "success": 0, "error": 0}
                
                llm_metrics["call_count"][key]["total"] += sample.value
                if status == "success":
                    llm_metrics["call_count"][key]["success"] += sample.value
                elif status == "error":
                    llm_metrics["call_count"][key]["error"] += sample.value
        
        elif metric.name == "llm_tokens_total":
            for sample in metric.samples:
                model = sample.labels.get("model", "unknown")
                token_type = sample.labels.get("type", "unknown")
                
                if model not in llm_metrics["token_count"][token_type]:
                    llm_metrics["token_count"][token_type][model] = 0
                
                llm_metrics["token_count"][token_type][model] += sample.value
                
                # Also add to total tokens
                if model not in llm_metrics["token_count"]["total"]:
                    llm_metrics["token_count"]["total"][model] = 0
                
                llm_metrics["token_count"]["total"][model] += sample.value
        
        elif metric.name == "llm_latency_seconds_sum":
            for sample in metric.samples:
                model = sample.labels.get("model", "unknown")
                function = sample.labels.get("function_name", "unknown")
                key = f"{model}:{function}"
                
                if key not in llm_metrics["latency"]["avg"]:
                    llm_metrics["latency"]["avg"][key] = 0
                
                # We'll divide this by count later to get the average
                llm_metrics["latency"]["avg"][key] += sample.value
        
        elif metric.name == "llm_cost_total":
            for sample in metric.samples:
                model = sample.labels.get("model", "unknown")
                
                if model not in llm_metrics["cost"]:
                    llm_metrics["cost"][model] = 0
                
                llm_metrics["cost"][model] += sample.value
    
    # Extract metrics for agent calls
    for metric in REGISTRY.collect():
        if metric.name == "agent_calls_total":
            for sample in metric.samples:
                agent_id = sample.labels.get("agent_id", "unknown")
                agent_name = sample.labels.get("agent_name", "unknown")
                status = sample.labels.get("status", "unknown")
                key = f"{agent_id}:{agent_name}"
                
                if key not in agent_metrics["call_count"]:
                    agent_metrics["call_count"][key] = {"total": 0, "success": 0, "error": 0}
                
                agent_metrics["call_count"][key]["total"] += sample.value
                if status == "success":
                    agent_metrics["call_count"][key]["success"] += sample.value
                elif status == "error":
                    agent_metrics["call_count"][key]["error"] += sample.value
        
        elif metric.name == "agent_latency_seconds_sum":
            for sample in metric.samples:
                agent_id = sample.labels.get("agent_id", "unknown")
                agent_name = sample.labels.get("agent_name", "unknown")
                key = f"{agent_id}:{agent_name}"
                
                if key not in agent_metrics["latency"]["avg"]:
                    agent_metrics["latency"]["avg"][key] = 0
                
                # We'll divide this by count later to get the average
                agent_metrics["latency"]["avg"][key] += sample.value
    
    # Calculate success rates for agents
    for key, counts in agent_metrics["call_count"].items():
        if counts["total"] > 0:
            agent_metrics["success_rate"][key] = (counts["success"] / counts["total"]) * 100
        else:
            agent_metrics["success_rate"][key] = 0
    
    # Get task execution metrics from DB for additional context
    task_metrics = {
        "total_count": db.query(Task).filter(Task.creator_id == current_user.id).count(),
        "completed_count": db.query(Task).filter(
            Task.creator_id == current_user.id,
            Task.status == TaskStatus.COMPLETED
        ).count(),
        "in_progress_count": db.query(Task).filter(
            Task.creator_id == current_user.id,
            Task.status == TaskStatus.IN_PROGRESS
        ).count(),
        "failed_count": db.query(Task).filter(
            Task.creator_id == current_user.id,
            Task.status == TaskStatus.FAILED
        ).count(),
        "avg_completion_time": None,  # Will be calculated below
    }
    
    # Get average completion time
    avg_completion_time = (
        db.query(func.avg(Task.completed_at - Task.started_at))
        .filter(
            Task.creator_id == current_user.id,
            Task.status == TaskStatus.COMPLETED,
            Task.completed_at.isnot(None),
            Task.started_at.isnot(None)
        )
        .scalar()
    )
    
    if avg_completion_time:
        task_metrics["avg_completion_time"] = avg_completion_time.total_seconds()
    
    return {
        "llm": llm_metrics,
        "agents": agent_metrics,
        "tasks": task_metrics,
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/telemetry/raw", response_model=str)
def get_raw_telemetry():
    """
    Get raw Prometheus metrics for all telemetry data.
    Can be consumed by Prometheus-compatible visualization tools.
    """
    return Response(content=generate_latest(), media_type="text/plain") 