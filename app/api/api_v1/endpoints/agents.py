from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.deps import get_db, get_current_user
from app.models.agent import Agent
from app.models.user import User
from app.schemas.agent import Agent as AgentSchema
from app.schemas.agent import AgentCreate, AgentUpdate

router = APIRouter()

@router.get("", response_model=List[AgentSchema])
def read_agents(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve agents.
    """
    agents = db.query(Agent).filter(Agent.is_active == True).offset(skip).limit(limit).all()
    return agents

@router.post("", response_model=AgentSchema)
def create_agent(
    *,
    db: Session = Depends(get_db),
    agent_in: AgentCreate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Create new agent.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can create agents",
        )
    
    agent = Agent(
        name=agent_in.name,
        description=agent_in.description,
        copilot_id=agent_in.copilot_id,
        capabilities=agent_in.capabilities,
        is_active=agent_in.is_active,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent

@router.put("/{agent_id}", response_model=AgentSchema)
def update_agent(
    *,
    db: Session = Depends(get_db),
    agent_id: int,
    agent_in: AgentUpdate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Update an agent.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can update agents",
        )
    
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    
    update_data = agent_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(agent, field, value)
    
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent

@router.get("/{agent_id}", response_model=AgentSchema)
def read_agent(
    *,
    db: Session = Depends(get_db),
    agent_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get agent by ID.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    return agent

@router.delete("/{agent_id}", response_model=AgentSchema)
def delete_agent(
    *,
    db: Session = Depends(get_db),
    agent_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Delete an agent.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can delete agents",
        )
    
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    
    # Soft delete - just mark as inactive
    agent.is_active = False
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent 