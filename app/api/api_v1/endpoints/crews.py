from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.deps import get_db, get_current_user
from app.models.crew import AgentCrew, CrewMember
from app.models.agent import Agent
from app.models.user import User
from app.schemas.crew import (
    AgentCrew as AgentCrewSchema, 
    AgentCrewCreate, 
    AgentCrewUpdate,
    AgentCrewWithMembers,
    CrewMember as CrewMemberSchema,
    CrewMemberCreate,
    CrewMemberUpdate
)

router = APIRouter()

@router.get("", response_model=List[AgentCrewSchema])
def read_crews(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve crews owned by current user.
    """
    crews = (
        db.query(AgentCrew)
        .filter(AgentCrew.owner_id == current_user.id, AgentCrew.is_active == True)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return crews

@router.post("", response_model=AgentCrewWithMembers)
def create_crew(
    *,
    db: Session = Depends(get_db),
    crew_in: AgentCrewCreate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Create new agent crew.
    """
    crew = AgentCrew(
        name=crew_in.name,
        description=crew_in.description,
        owner_id=current_user.id,
        is_active=crew_in.is_active
    )
    db.add(crew)
    db.commit()
    db.refresh(crew)
    
    # Add crew members if provided
    if crew_in.members:
        for member_data in crew_in.members:
            # Verify agent exists
            agent = db.query(Agent).filter(Agent.id == member_data.agent_id).first()
            if not agent:
                # Rollback and raise exception
                db.delete(crew)
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent with id {member_data.agent_id} not found",
                )
            
            crew_member = CrewMember(
                crew_id=crew.id,
                agent_id=member_data.agent_id,
                role=member_data.role
            )
            db.add(crew_member)
    
    db.commit()
    db.refresh(crew)
    
    # Get full crew with members
    crew_with_members = db.query(AgentCrew).filter(AgentCrew.id == crew.id).first()
    return crew_with_members

@router.get("/{crew_id}", response_model=AgentCrewWithMembers)
def read_crew(
    *,
    db: Session = Depends(get_db),
    crew_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get specific crew by ID.
    """
    crew = (
        db.query(AgentCrew)
        .filter(AgentCrew.id == crew_id, AgentCrew.owner_id == current_user.id)
        .first()
    )
    if not crew:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Crew not found or you don't have permission to access it",
        )
    return crew

@router.put("/{crew_id}", response_model=AgentCrewWithMembers)
def update_crew(
    *,
    db: Session = Depends(get_db),
    crew_id: int,
    crew_in: AgentCrewUpdate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Update a crew.
    """
    crew = (
        db.query(AgentCrew)
        .filter(AgentCrew.id == crew_id, AgentCrew.owner_id == current_user.id)
        .first()
    )
    if not crew:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Crew not found or you don't have permission to access it",
        )
    
    # Update basic crew info
    update_data = crew_in.dict(exclude={"members"}, exclude_unset=True)
    for field, value in update_data.items():
        setattr(crew, field, value)
    
    # Handle members update if provided
    if crew_in.members is not None:
        # Remove existing members
        db.query(CrewMember).filter(CrewMember.crew_id == crew.id).delete()
        
        # Add new members
        for member_data in crew_in.members:
            crew_member = CrewMember(
                crew_id=crew.id,
                agent_id=member_data.agent_id,
                role=member_data.role
            )
            db.add(crew_member)
    
    db.add(crew)
    db.commit()
    db.refresh(crew)
    return crew

@router.delete("/{crew_id}", response_model=AgentCrewSchema)
def delete_crew(
    *,
    db: Session = Depends(get_db),
    crew_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Delete a crew.
    """
    crew = (
        db.query(AgentCrew)
        .filter(AgentCrew.id == crew_id, AgentCrew.owner_id == current_user.id)
        .first()
    )
    if not crew:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Crew not found or you don't have permission to access it",
        )
    
    # Soft delete
    crew.is_active = False
    db.add(crew)
    db.commit()
    db.refresh(crew)
    return crew

@router.post("/{crew_id}/members", response_model=CrewMemberSchema)
def add_crew_member(
    *,
    db: Session = Depends(get_db),
    crew_id: int,
    member_in: CrewMemberCreate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Add member to a crew.
    """
    crew = (
        db.query(AgentCrew)
        .filter(AgentCrew.id == crew_id, AgentCrew.owner_id == current_user.id)
        .first()
    )
    if not crew:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Crew not found or you don't have permission to access it",
        )
    
    # Check if agent exists
    agent = db.query(Agent).filter(Agent.id == member_in.agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with id {member_in.agent_id} not found",
        )
    
    # Check if agent is already in the crew
    existing_member = (
        db.query(CrewMember)
        .filter(CrewMember.crew_id == crew_id, CrewMember.agent_id == member_in.agent_id)
        .first()
    )
    if existing_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent is already a member of this crew",
        )
    
    crew_member = CrewMember(
        crew_id=crew.id,
        agent_id=member_in.agent_id,
        role=member_in.role
    )
    db.add(crew_member)
    db.commit()
    db.refresh(crew_member)
    return crew_member

@router.delete("/{crew_id}/members/{member_id}", response_model=CrewMemberSchema)
def remove_crew_member(
    *,
    db: Session = Depends(get_db),
    crew_id: int,
    member_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Remove member from a crew.
    """
    crew = (
        db.query(AgentCrew)
        .filter(AgentCrew.id == crew_id, AgentCrew.owner_id == current_user.id)
        .first()
    )
    if not crew:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Crew not found or you don't have permission to access it",
        )
    
    crew_member = (
        db.query(CrewMember)
        .filter(CrewMember.id == member_id, CrewMember.crew_id == crew_id)
        .first()
    )
    if not crew_member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Crew member not found",
        )
    
    db.delete(crew_member)
    db.commit()
    return crew_member 