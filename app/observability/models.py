from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base_class import Base

class LLMCall(Base):
    __tablename__ = "llm_calls"

    id = Column(Integer, primary_key=True, index=True)
    model = Column(String, nullable=False)
    function_name = Column(String, nullable=False)
    prompt_tokens = Column(Integer, nullable=False)
    completion_tokens = Column(Integer, nullable=False)
    latency = Column(Float, nullable=False)  # in seconds
    cost = Column(Float, nullable=False)  # in USD
    status = Column(String, nullable=False)  # success or error
    error_message = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    prompt = Column(String)
    response = Column(String)

class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String, nullable=False)
    agent_name = Column(String, nullable=False)
    input_message = Column(String)
    output_message = Column(String)
    status = Column(String, nullable=False)  # success or error
    error_message = Column(String)
    latency = Column(Float, nullable=False)  # in seconds
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    metadata = Column(JSON)  # for any additional agent-specific data

class TaskExecution(Base):
    __tablename__ = "task_executions"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False)
    crew_id = Column(Integer, nullable=False)
    description = Column(String, nullable=False)
    status = Column(String, nullable=False)  # started, completed, failed
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    duration = Column(Float)  # in seconds
    result = Column(JSON)
    error_message = Column(String)
    
    # Relationships with other executions
    llm_calls = relationship("LLMCall", secondary="task_llm_calls")
    agent_executions = relationship("AgentExecution", secondary="task_agent_executions")

# Association tables for many-to-many relationships
class TaskLLMCall(Base):
    __tablename__ = "task_llm_calls"

    task_id = Column(Integer, ForeignKey("task_executions.id"), primary_key=True)
    llm_call_id = Column(Integer, ForeignKey("llm_calls.id"), primary_key=True)

class TaskAgentExecution(Base):
    __tablename__ = "task_agent_executions"

    task_id = Column(Integer, ForeignKey("task_executions.id"), primary_key=True)
    agent_execution_id = Column(Integer, ForeignKey("agent_executions.id"), primary_key=True) 