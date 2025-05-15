# Import all models here to resolve circular dependencies

from app.db.base import Base
from app.models.user import User
from app.models.agent import Agent
from app.models.crew import AgentCrew, CrewMember
from app.models.task import Task, TaskMessage, TaskStatus

# This ensures all models are imported when this module is imported
