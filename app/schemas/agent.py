from typing import Optional, Dict, Any, List
from pydantic import BaseModel

# Shared properties
class AgentBase(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    copilot_id: Optional[str] = None
    direct_line_secret: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = True

# Properties to receive via API on creation
class AgentCreate(AgentBase):
    name: str
    copilot_id: str
    direct_line_secret: str

# Properties to receive via API on update
class AgentUpdate(AgentBase):
    pass

# Properties to return via API
class AgentInDBBase(AgentBase):
    id: int

    class Config:
        from_attributes = True

# Additional properties to return via API
class Agent(AgentInDBBase):
    pass 