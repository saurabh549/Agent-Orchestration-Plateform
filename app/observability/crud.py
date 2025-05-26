from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.observability.models import LLMCall, AgentExecution

class ObservabilityCRUD:
    @staticmethod
    def create_llm_call(
        db: Session,
        model: str,
        function_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency: float,
        cost: float,
        status: str,
        prompt: Optional[str] = None,
        response: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> LLMCall:
        db_obj = LLMCall(
            model=model,
            function_name=function_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency=latency,
            cost=cost,
            status=status,
            prompt=prompt,
            response=response,
            error_message=error_message,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    @staticmethod
    def create_agent_execution(
        db: Session,
        agent_id: str,
        agent_name: str,
        status: str,
        latency: float,
        input_message: Optional[str] = None,
        output_message: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> AgentExecution:
        db_obj = AgentExecution(
            agent_id=agent_id,
            agent_name=agent_name,
            status=status,
            latency=latency,
            input_message=input_message,
            output_message=output_message,
            error_message=error_message,
            metadata=metadata,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    @staticmethod
    def get_llm_usage_stats(
        db: Session,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        """Get LLM usage statistics for a time period"""
        stats = {
            "total_calls": db.query(LLMCall).filter(
                and_(
                    LLMCall.timestamp >= start_time,
                    LLMCall.timestamp <= end_time
                )
            ).count(),
            "total_cost": db.query(func.sum(LLMCall.cost)).filter(
                and_(
                    LLMCall.timestamp >= start_time,
                    LLMCall.timestamp <= end_time
                )
            ).scalar(),
            "total_tokens": db.query(
                func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens)
            ).filter(
                and_(
                    LLMCall.timestamp >= start_time,
                    LLMCall.timestamp <= end_time
                )
            ).scalar(),
            "model_usage": db.query(
                LLMCall.model,
                func.count(LLMCall.id)
            ).filter(
                and_(
                    LLMCall.timestamp >= start_time,
                    LLMCall.timestamp <= end_time
                )
            ).group_by(LLMCall.model).all(),
        }
        return stats

    @staticmethod
    def get_agent_performance_stats(
        db: Session,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        """Get agent performance statistics for a time period"""
        stats = {
            "total_executions": db.query(AgentExecution).filter(
                and_(
                    AgentExecution.timestamp >= start_time,
                    AgentExecution.timestamp <= end_time
                )
            ).count(),
            "success_rate": db.query(
                func.count(AgentExecution.id)
            ).filter(
                and_(
                    AgentExecution.timestamp >= start_time,
                    AgentExecution.timestamp <= end_time,
                    AgentExecution.status == "success"
                )
            ).scalar(),
            "avg_latency": db.query(
                func.avg(AgentExecution.latency)
            ).filter(
                and_(
                    AgentExecution.timestamp >= start_time,
                    AgentExecution.timestamp <= end_time
                )
            ).scalar(),
            "agent_usage": db.query(
                AgentExecution.agent_name,
                func.count(AgentExecution.id)
            ).filter(
                and_(
                    AgentExecution.timestamp >= start_time,
                    AgentExecution.timestamp <= end_time
                )
            ).group_by(AgentExecution.agent_name).all(),
        }
        return stats 