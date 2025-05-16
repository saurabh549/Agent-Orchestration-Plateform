from typing import Any, List, Dict
from datetime import datetime
import asyncio

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from app.db.deps import get_db, get_current_user
from app.models.task import Task, TaskMessage, TaskStatus
from app.models.crew import AgentCrew
from app.models.user import User
from app.schemas.task import (
    Task as TaskSchema,
    TaskCreate,
    TaskUpdate,
    TaskWithMessages,
    TaskMessage as TaskMessageSchema,
    TaskMessageCreate,
)
# Import both task execution methods
from app.services.task_executor import execute_task_with_crew
from app.services.plugin_task_service import execute_task_with_crew_kernel

router = APIRouter()

@router.get("", response_model=List[TaskSchema])
def read_tasks(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve tasks created by current user.
    """
    tasks = (
        db.query(Task)
        .filter(Task.creator_id == current_user.id)
        .order_by(Task.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return tasks

@router.post("", response_model=TaskSchema)
def create_task(
    *,
    db: Session = Depends(get_db),
    task_in: TaskCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Create new task and assign it to a crew.
    """
    print(f"\n[API] Creating task with plugin-based execution: {task_in.title}")
    # Check if crew exists and belongs to the user
    crew = (
        db.query(AgentCrew)
        .filter(
            AgentCrew.id == task_in.crew_id,
            AgentCrew.owner_id == current_user.id,
            AgentCrew.is_active == True
        )
        .first()
    )
    if not crew:
        print(f"[API] Error: Crew not found or permissions issue")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Crew not found or you don't have permission to access it",
        )
    
    # Create task
    task = Task(
        title=task_in.title,
        description=task_in.description,
        creator_id=current_user.id,
        crew_id=task_in.crew_id,
        status=TaskStatus.PENDING
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    
    print(f"[API] Task created with ID {task.id}, scheduling execution with plugin-based approach")
    
    # Use the new plugin-based task execution
    background_tasks.add_task(
        execute_task_with_crew_kernel,
        task_id=task.id,
        db=db
    )
    
    return task

@router.post("/legacy", response_model=TaskSchema)
def create_legacy_task(
    *,
    db: Session = Depends(get_db),
    task_in: TaskCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Create new task using the legacy execution method.
    """
    print(f"\n[API] Creating task with legacy execution: {task_in.title}")
    # Check if crew exists and belongs to the user
    crew = (
        db.query(AgentCrew)
        .filter(
            AgentCrew.id == task_in.crew_id,
            AgentCrew.owner_id == current_user.id,
            AgentCrew.is_active == True
        )
        .first()
    )
    if not crew:
        print(f"[API] Error: Crew not found or permissions issue")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Crew not found or you don't have permission to access it",
        )
    
    # Create task
    task = Task(
        title=task_in.title,
        description=task_in.description,
        creator_id=current_user.id,
        crew_id=task_in.crew_id,
        status=TaskStatus.PENDING
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    
    print(f"[API] Task created with ID {task.id}, scheduling execution with legacy approach")
    
    # Use the original task execution method
    background_tasks.add_task(
        execute_task_with_crew,
        task_id=task.id,
        db=db
    )
    
    return task

@router.get("/{task_id}", response_model=TaskWithMessages)
def read_task(
    *,
    db: Session = Depends(get_db),
    task_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get specific task by ID.
    """
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.creator_id == current_user.id)
        .first()
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return task

@router.put("/{task_id}", response_model=TaskSchema)
def update_task(
    *,
    db: Session = Depends(get_db),
    task_id: int,
    task_in: TaskUpdate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Update a task.
    """
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.creator_id == current_user.id)
        .first()
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    
    # Only allow updates if task is not in progress
    if task.status == TaskStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update a task that is in progress",
        )
    
    update_data = task_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)
    
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

@router.post("/{task_id}/messages", response_model=TaskMessageSchema)
def add_task_message(
    *,
    db: Session = Depends(get_db),
    task_id: int,
    message_in: TaskMessageCreate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Add a message to a task.
    """
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.creator_id == current_user.id)
        .first()
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    
    message = TaskMessage(
        task_id=task.id,
        content=message_in.content,
        is_system=False
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message

@router.delete("/{task_id}", response_model=TaskSchema)
def delete_task(
    *,
    db: Session = Depends(get_db),
    task_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Delete a task.
    """
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.creator_id == current_user.id)
        .first()
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    
    # Only allow deletion if task is not in progress
    if task.status == TaskStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a task that is in progress",
        )
    
    db.delete(task)
    db.commit()
    return task 