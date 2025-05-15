import json
from typing import Dict, Optional, Any, List
import asyncio

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.crew import AgentCrew, CrewMember
from app.models.agent import Agent
from app.services.copilot_client import CopilotStudioClient
from app.services.copilot_agent_plugin import CopilotAgentPlugin


class CrewKernelManager:
    """
    Manages Semantic Kernel instances for crews, 
    registering Copilot agents as plugins when crews are created or updated.
    """
    
    def __init__(self):
        """Initialize the manager"""
        self._kernels: Dict[int, Kernel] = {}  # crew_id -> kernel
        self._copilot_client = CopilotStudioClient(settings.DIRECT_LINE_SECRET)
        self._kernel_locks = {}  # Locks to prevent race conditions on kernel creation
    
    async def get_crew_kernel(self, db: Session, crew_id: int) -> Kernel:
        """
        Get or create a Semantic Kernel instance for a crew.
        
        Args:
            db: Database session
            crew_id: Crew ID
            
        Returns:
            A Semantic Kernel instance with crew's agents registered as plugins
        """
        # If we already have a kernel for this crew, return it
        if crew_id in self._kernels:
            return self._kernels[crew_id]
        
        # Create a lock for this crew if it doesn't exist
        if crew_id not in self._kernel_locks:
            self._kernel_locks[crew_id] = asyncio.Lock()
        
        # Use the lock to prevent race conditions
        async with self._kernel_locks[crew_id]:
            # Check again if kernel was created while waiting for lock
            if crew_id in self._kernels:
                return self._kernels[crew_id]
            
            # Create a new kernel for this crew
            kernel = await self._create_kernel_for_crew(db, crew_id)
            self._kernels[crew_id] = kernel
            return kernel
    
    async def _create_kernel_for_crew(self, db: Session, crew_id: int) -> Kernel:
        """
        Create a Semantic Kernel instance for a crew with its agents registered as plugins.
        
        Args:
            db: Database session
            crew_id: Crew ID
            
        Returns:
            A configured Semantic Kernel instance
        """
        # Initialize kernel
        kernel = Kernel()
        
        # Configure AI backend based on config
        if settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT:
            # Azure OpenAI
            kernel.add_service(
                AzureChatCompletion(
                    service_id="chat_completion",
                    deployment_name="gpt-4",
                    endpoint=settings.AZURE_OPENAI_ENDPOINT,
                    api_key=settings.AZURE_OPENAI_API_KEY,
                )
            )
        else:
            # OpenAI
            kernel.add_service(
                OpenAIChatCompletion(
                    service_id="chat_completion",
                    ai_model_id="gpt-4",
                    api_key=settings.OPENAI_API_KEY,
                )
            )
        
        # Get crew and its members
        crew = db.query(AgentCrew).filter(AgentCrew.id == crew_id).first()
        if not crew:
            raise ValueError(f"Crew with ID {crew_id} not found")
        
        crew_members = db.query(CrewMember).filter(CrewMember.crew_id == crew_id).all()
        
        # Register each agent as a plugin
        for member in crew_members:
            agent = db.query(Agent).filter(Agent.id == member.agent_id).first()
            if not agent:
                continue
            
            # Create a plugin for this agent
            plugin = CopilotAgentPlugin(
                copilot_client=self._copilot_client,
                agent_id=agent.copilot_id,
                agent_name=agent.name,
                capabilities=agent.capabilities,
                role=member.role
            )
            
            # Add the plugin to the kernel
            plugin_name = f"{agent.name.replace(' ', '')}Plugin"
            kernel.add_plugin(plugin, plugin_name=plugin_name)
        
        return kernel
    
    async def refresh_crew_kernel(self, db: Session, crew_id: int) -> Kernel:
        """
        Force refresh of a crew's kernel (e.g., after crew membership changes).
        
        Args:
            db: Database session
            crew_id: Crew ID
            
        Returns:
            The updated Semantic Kernel instance
        """
        # Use the lock to prevent race conditions
        if crew_id not in self._kernel_locks:
            self._kernel_locks[crew_id] = asyncio.Lock()
            
        async with self._kernel_locks[crew_id]:
            # Remove existing kernel if any
            if crew_id in self._kernels:
                del self._kernels[crew_id]
            
            # Create a new kernel
            kernel = await self._create_kernel_for_crew(db, crew_id)
            self._kernels[crew_id] = kernel
            return kernel
    
    def get_crew_plugin_info(self, crew_id: int) -> List[Dict[str, Any]]:
        """
        Get information about plugins registered for a crew.
        
        Args:
            crew_id: Crew ID
            
        Returns:
            List of plugin information dictionaries
        """
        if crew_id not in self._kernels:
            return []
        
        kernel = self._kernels[crew_id]
        plugin_info = []
        
        for plugin_name, plugin in kernel.plugins.items():
            functions = []
            for fn_name, fn in plugin.functions.items():
                params = []
                for param in fn.metadata.parameters:
                    params.append({
                        "name": param[0],
                        "type": param[1],
                        "description": param[2]
                    })
                
                functions.append({
                    "name": fn_name,
                    "description": fn.metadata.description,
                    "parameters": params
                })
            
            plugin_info.append({
                "plugin_name": plugin_name,
                "functions": functions
            })
        
        return plugin_info


# Global singleton instance
crew_kernel_manager = CrewKernelManager() 