from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel

from app.schemas.agent import Agent

# Crew Member schemas
class CrewMemberBase(BaseModel):
    agent_id: int
    role: Optional[str] = None

class CrewMemberCreate(CrewMemberBase):
    pass

class CrewMemberUpdate(CrewMemberBase):
    agent_id: Optional[int] = None

class CrewMemberInDBBase(CrewMemberBase):
    id: int
    crew_id: int

    class Config:
        from_attributes = True

class CrewMember(CrewMemberInDBBase):
    pass

class CrewMemberWithDetails(CrewMember):
    agent: Optional[Agent] = None

# Agent Crew schemas
class AgentCrewBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: Optional[bool] = True

class AgentCrewCreate(AgentCrewBase):
    members: Optional[List[CrewMemberCreate]] = None

class AgentCrewUpdate(AgentCrewBase):
    name: Optional[str] = None
    members: Optional[List[CrewMemberCreate]] = None

class AgentCrewInDBBase(AgentCrewBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class AgentCrew(AgentCrewInDBBase):
    pass

class AgentCrewWithMembers(AgentCrew):
    members: List[CrewMemberWithDetails] = [] 