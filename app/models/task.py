from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base import Base

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    creator_id = Column(Integer, ForeignKey("users.id"))
    crew_id = Column(Integer, ForeignKey("agent_crews.id"))
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    result = Column(JSON, nullable=True)  # Store the task result in JSON format
    error = Column(Text, nullable=True)  # Store error message if task failed
    
    # Relationships
    creator = relationship("User", back_populates="tasks")
    crew = relationship("AgentCrew", back_populates="tasks")
    messages = relationship("TaskMessage", back_populates="task", cascade="all, delete-orphan")

class TaskMessage(Base):
    __tablename__ = "task_messages"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    is_system = Column(Integer, default=False)  # Flag for system messages
    content = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    task = relationship("Task", back_populates="messages")
    agent = relationship("Agent") 