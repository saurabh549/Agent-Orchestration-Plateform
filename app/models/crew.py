from sqlalchemy import Boolean, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base

class AgentCrew(Base):
    __tablename__ = "agent_crews"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    
    # Relationships
    owner = relationship("User", back_populates="agent_crews")
    members = relationship("CrewMember", back_populates="crew", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="crew")

class CrewMember(Base):
    __tablename__ = "crew_members"

    id = Column(Integer, primary_key=True, index=True)
    crew_id = Column(Integer, ForeignKey("agent_crews.id"))
    agent_id = Column(Integer, ForeignKey("agents.id"))
    role = Column(String)  # Role of this agent in the crew
    
    # Relationships
    crew = relationship("AgentCrew", back_populates="members")
    agent = relationship("Agent", back_populates="crew_memberships") 