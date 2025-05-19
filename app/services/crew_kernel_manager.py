import json
import re
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
from app.services.agent_pool import AgentPoolManager


class CrewKernelManager:
    """
    Manages Semantic Kernel instances for crews, 
    registering Copilot agents as plugins when crews are created or updated.
    """
    
    def __init__(self):
        """Initialize the manager"""
        self._kernels: Dict[int, Kernel] = {}  # crew_id -> kernel
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
    
    def _sanitize_plugin_name(self, name: str) -> str:
        """
        Sanitize a name to be used as a plugin name.
        Plugin names must match the pattern ^[0-9A-Za-z_]+$
        
        Args:
            name: The name to sanitize
            
        Returns:
            A sanitized name that can be used as a plugin name
        """
        # Replace spaces and non-alphanumeric characters with underscores
        sanitized = re.sub(r'[^0-9A-Za-z_]', '_', name)
        
        # Ensure the name starts with a letter or underscore (not a number)
        if sanitized and sanitized[0].isdigit():
            sanitized = f"_{sanitized}"
            
        return sanitized
    
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
        from semantic_kernel.connectors.ai.google.google_ai import GoogleAIChatCompletion
        kernel.add_service(
            GoogleAIChatCompletion(
                service_id="chat_completion",
                gemini_model_id="gemini-2.0-flash",
                api_key=settings.GEMINI_API_KEY,
            )
        )
        # Get crew and its members
        crew = db.query(AgentCrew).filter(AgentCrew.id == crew_id).first()
        if not crew:
            raise ValueError(f"Crew with ID {crew_id} not found")
        
        crew_members = db.query(CrewMember).filter(CrewMember.crew_id == crew_id).all()
        
        # Get all agents for this crew
        agent_ids = [member.agent_id for member in crew_members]
        agents = db.query(Agent).filter(Agent.id.in_(agent_ids)).all()
        
        # Create an AgentPool instance using the AgentPoolManager
        agent_pool = AgentPoolManager.create_agent_pool(crew_members, agents)
        
        # Create a valid plugin name
        plugin_name = self._sanitize_plugin_name(f"{crew.name}Agents")
        
        # Register the agent pool with the kernel
        AgentPoolManager.register_with_kernel(agent_pool, kernel, plugin_name=plugin_name)
        
        print(f"[CrewKernel] Kernel plugins: {kernel.plugins}")
        
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
                    # Access KernelParameterMetadata properties instead of treating it as a tuple
                    params.append({
                        "name": param.name,
                        "type": param.type_,
                        "description": param.description or ""
                    })
                
                functions.append({
                    "name": fn_name,
                    "description": fn.metadata.description or "",
                    "parameters": params
                })
            
            plugin_info.append({
                "plugin_name": plugin_name,
                "functions": functions
            })
        
        return plugin_info


# Global singleton instance
crew_kernel_manager = CrewKernelManager() 