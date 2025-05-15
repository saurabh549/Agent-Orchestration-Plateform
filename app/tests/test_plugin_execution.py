#!/usr/bin/env python3

import asyncio
import os
import sys
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.models.task import Task, TaskMessage, TaskStatus
from app.models.crew import AgentCrew, CrewMember
from app.models.agent import Agent
from app.services.crew_kernel_manager import crew_kernel_manager
from app.services.plugin_task_service import execute_task_with_crew_kernel
from app.db.base import Base


async def test_plugin_execution():
    """Test the plugin-based task execution approach"""
    # Create a test in-memory database
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Create a database session
    db = SessionLocal()
    
    try:
        # Create test data
        print("Creating test data...")
        test_crew, test_agents = create_test_data(db)
        
        # Create a test task
        task = Task(
            title="Test Plugin Execution",
            description="This is a test task for Copilot agent plugins. Find information about Python's asyncio library.",
            creator_id=1,  # Assuming user ID 1
            crew_id=test_crew.id,
            status=TaskStatus.PENDING
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # Initialize the kernel for this crew
        print(f"Initializing kernel for crew {test_crew.id}...")
        kernel = await crew_kernel_manager.get_crew_kernel(db, test_crew.id)
        
        # Get plugin info
        plugin_info = crew_kernel_manager.get_crew_plugin_info(test_crew.id)
        print(f"Available plugins: {json.dumps(plugin_info, indent=2)}")
        
        # Execute the task
        print(f"Executing task {task.id}...")
        result = await execute_task_with_crew_kernel(task.id, db)
        
        # Print the result
        print(f"Task execution result: {result}")
        
        # Get task messages
        messages = db.query(TaskMessage).filter(TaskMessage.task_id == task.id).all()
        for msg in messages:
            print(f"Message {'(System)' if msg.is_system else ''}: {msg.content[:100]}...")
        
        print("Test completed successfully.")
    
    except Exception as e:
        print(f"Error during test: {str(e)}")
        raise
    
    finally:
        db.close()


def create_test_data(db: Session):
    """Create test data for the test"""
    # Create test agents
    agents = [
        Agent(
            name="Research Agent",
            description="An agent specialized in research and information gathering",
            copilot_id="research-agent-id",
            capabilities={
                "research": "Can search for information online and provide detailed research on any topic",
                "summarization": "Can summarize lengthy content into concise points"
            },
            is_active=True
        ),
        Agent(
            name="Coding Agent",
            description="An agent specialized in programming and code generation",
            copilot_id="coding-agent-id",
            capabilities={
                "code_generation": "Can generate code snippets in various programming languages",
                "code_explanation": "Can explain how code works"
            },
            is_active=True
        )
    ]
    
    for agent in agents:
        db.add(agent)
    
    db.commit()
    
    # Create a test crew
    crew = AgentCrew(
        name="Test Crew",
        description="A test crew with research and coding agents",
        owner_id=1,  # Assuming user ID 1
        is_active=True
    )
    db.add(crew)
    db.commit()
    
    # Add agents to the crew
    crew_members = [
        CrewMember(
            crew_id=crew.id,
            agent_id=agents[0].id,
            role="Researcher"
        ),
        CrewMember(
            crew_id=crew.id,
            agent_id=agents[1].id,
            role="Developer"
        )
    ]
    
    for member in crew_members:
        db.add(member)
    
    db.commit()
    
    return crew, agents


if __name__ == "__main__":
    asyncio.run(test_plugin_execution()) 