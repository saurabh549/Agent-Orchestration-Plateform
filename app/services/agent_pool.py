from typing import Dict, List, Any, Optional, Type
from semantic_kernel import Kernel
from semantic_kernel.functions import kernel_function
from typing_extensions import Annotated
import inspect
import types

from app.models.agent import Agent
from app.models.crew import CrewMember
from app.services.copilot_client import CopilotStudioClient
from app.observability.telemetry import AgentCallTracker


def create_agent_pool_class(crew_members: List[CrewMember], agents: List[Agent], task_id: Optional[int] = None) -> Type:
    """
    Dynamically create an AgentPool class with methods for each agent in the crew.
    
    Args:
        crew_members: List of CrewMember objects
        agents: List of Agent objects
        task_id: Optional task ID for tracking purposes
        
    Returns:
        A dynamically created AgentPool class with methods for each agent
    """
    # Create a map of agent_id -> agent for quick lookup
    agent_map = {agent.id: agent for agent in agents}
    
    # Create a dictionary to store agent clients
    agent_clients = {}
    
    # Create the AgentPool class
    class AgentPool:
        """
        A dynamically created class that provides methods for each agent in the crew.
        Each method corresponds to a specific agent and calls the agent via Direct Line API.
        """
        
        def __init__(self):
            """Initialize the agent pool."""
            pass
    
    # Create methods for each agent
    for member in crew_members:
        if member.agent_id not in agent_map:
            continue
            
        agent = agent_map[member.agent_id]
        agent_name = agent.name.lower().replace(' ', '_')
        agent_description = agent.description
        
        # Create a client for this agent
        client = CopilotStudioClient(agent.direct_line_secret)
        agent_clients[agent_name] = {
            "client": client,
            "id": agent.copilot_id,
            "name": agent.name,
            "task_id": task_id
        }
        
        # Create a function that will be used as a method for this agent
        def create_agent_function(agent_name):
            async def agent_function(self, 
                                message: Annotated[str, "The message to send to the agent"],
                                conversation_id: Annotated[Optional[str], "Optional conversation ID for maintaining context"] = None) -> Annotated[str, "The agent's response"]:
                """Send a message to this agent and get a response."""
                agent_info = agent_clients[agent_name]
                client = agent_info["client"]
                
                # Use agent call tracker for telemetry if task_id is provided
                if agent_info["task_id"]:
                    with AgentCallTracker(
                        agent_id=agent_info["id"],
                        agent_name=agent_info["name"],
                        input_message=message
                    ) as agent_tracker:
                        response = await client.send_message(
                            agent_id=agent_info["id"],
                            message=message,
                            conversation_id=conversation_id or f"task_{agent_info['task_id']}"
                        )
                        agent_tracker.response = response
                        return response
                else:
                    # Without telemetry if no task_id
                    return await client.send_message(
                        agent_id=agent_info["id"],
                        message=message,
                        conversation_id=conversation_id
                    )
            return agent_function
        
        # Create the function for this agent
        method_name = f"ask_{agent_name}"
        
        # Create the function
        agent_function = create_agent_function(agent_name)
        
        # Add the kernel_function decorator
        decorated_function = kernel_function(
            name=method_name,
            description=agent_description
        )(agent_function)
        
        # Add the method to the AgentPool class
        setattr(AgentPool, method_name, decorated_function)
    
    return AgentPool


class AgentPoolManager:
    """
    A manager class that creates and manages AgentPool instances.
    """
    
    @staticmethod
    def create_agent_pool(crew_members: List[CrewMember], agents: List[Agent], task_id: Optional[int] = None) -> Any:
        """
        Create an AgentPool instance for a crew.
        
        Args:
            crew_members: List of CrewMember objects
            agents: List of Agent objects
            task_id: Optional task ID for tracking purposes
            
        Returns:
            An instance of the dynamically created AgentPool class
        """
        # Create the AgentPool class
        agent_pool_class = create_agent_pool_class(crew_members, agents, task_id)
        
        # Create an instance of the AgentPool class
        agent_pool = agent_pool_class()
        
        return agent_pool
    
    @staticmethod
    def register_with_kernel(agent_pool: Any, kernel: Kernel, plugin_name: str = "AgentPool"):
        """
        Register an AgentPool instance with a kernel.
        
        Args:
            agent_pool: An AgentPool instance
            kernel: A Semantic Kernel instance
            plugin_name: The name to use for the plugin
        """
        # Register the agent pool with the kernel
        kernel.add_plugin(agent_pool, plugin_name=plugin_name)
    
    @staticmethod
    def get_agent_info(agent_pool: Any) -> List[Dict[str, Any]]:
        """
        Get information about all agents in the pool.
        
        Args:
            agent_pool: An AgentPool instance
            
        Returns:
            A list of dictionaries with agent information
        """
        agent_info = []
        
        # Get all methods that have the kernel_function decorator
        for name, method in inspect.getmembers(agent_pool, predicate=inspect.ismethod):
            if hasattr(method, "__kernel_function__"):
                agent_info.append({
                    "name": name,
                    "description": method.__kernel_function_metadata__.description
                })
        
        return agent_info 