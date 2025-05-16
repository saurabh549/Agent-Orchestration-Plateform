from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel

from app.models.task import TaskStatus

# Task Message schemas
class TaskMessageBase(BaseModel):
    content: str
    agent_id: Optional[int] = None
    is_system: bool = False

class TaskMessageCreate(TaskMessageBase):
    pass

class TaskMessageInDBBase(TaskMessageBase):
    id: int
    task_id: int
    timestamp: datetime

    class Config:
        from_attributes = True

class TaskMessage(TaskMessageInDBBase):
    pass

# Task schemas
class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    crew_id: int

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None

class TaskInDBBase(TaskBase):
    id: int
    creator_id: int
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True

class Task(TaskInDBBase):
    pass

class TaskWithMessages(Task):
    messages: List[TaskMessage] = [] 