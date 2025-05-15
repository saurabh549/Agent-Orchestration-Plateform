from sqlalchemy import Boolean, Column, Integer, String, Text, JSON
from sqlalchemy.orm import relationship

from app.db.base import Base

class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    copilot_id = Column(String, unique=True, index=True)  # ID from Copilot Studio
    capabilities = Column(JSON)  # JSON field to store agent capabilities
    is_active = Column(Boolean, default=True)
    
    # Relationships
    crew_memberships = relationship("CrewMember", back_populates="agent") 