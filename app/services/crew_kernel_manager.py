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
        has_valid_azure = (settings.AZURE_OPENAI_API_KEY and 
                          settings.AZURE_OPENAI_ENDPOINT and 
                          settings.AZURE_OPENAI_ENDPOINT != "your-azure-openai-endpoint-here" and
                          "azure.com" in settings.AZURE_OPENAI_ENDPOINT)
        
        if has_valid_azure:
            # Azure OpenAI
            print(f"[CrewKernel] Using Azure OpenAI with endpoint: {settings.AZURE_OPENAI_ENDPOINT}")
            kernel.add_service(
                AzureChatCompletion(
                    service_id="chat_completion",
                    deployment_name="gpt-4",
                    endpoint=settings.AZURE_OPENAI_ENDPOINT,
                    api_key=settings.AZURE_OPENAI_API_KEY,
                )
            )
        elif settings.GEMINI_API_KEY:
            # Google Gemini
            print(f"[CrewKernel] Using Google Gemini API")
            from semantic_kernel.connectors.ai.google.google_ai import GoogleAIChatCompletion
            kernel.add_service(
                GoogleAIChatCompletion(
                    service_id="chat_completion",
                    gemini_model_id="gemini-2.0-flash",
                    api_key=settings.GEMINI_API_KEY,
                )
            )
        else:
            # OpenAI
            print(f"[CrewKernel] Using OpenAI API")
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
                agent_id=agent.copilot_id,
                agent_name=agent.name,
                direct_line_secret=agent.direct_line_secret,
                capabilities=agent.capabilities,
                role=member.role
            )
            
            # Add the plugin to the kernel - plugin name is now set in the constructor
            kernel.add_plugin(plugin)
        
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