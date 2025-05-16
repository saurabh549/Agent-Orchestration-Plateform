import json
from typing import Dict, Any, Optional, List, ClassVar

from semantic_kernel.functions import kernel_function
from semantic_kernel.functions import KernelFunctionMetadata, KernelParameterMetadata
from semantic_kernel.functions import KernelPlugin
from semantic_kernel.functions.kernel_function_from_method import KernelFunctionFromMethod
from pydantic import Field, PrivateAttr

from app.services.copilot_client import CopilotStudioClient
from app.observability.telemetry import AgentCallTracker


class CopilotAgentPlugin(KernelPlugin):
    """
    A Semantic Kernel plugin that wraps Copilot Studio agents as plugin functions.
    This allows LLMs to decide when to invoke which Copilot agent based on the task context.
    """
    # Private attributes not serialized to JSON
    _copilot_client: CopilotStudioClient = PrivateAttr(default=None)
    _agent_id: str = PrivateAttr(default="")
    _agent_name: str = PrivateAttr(default="")
    _capabilities: Dict[str, Any] = PrivateAttr(default_factory=dict)
    _role: Optional[str] = PrivateAttr(default=None)
    _task_id: Optional[int] = PrivateAttr(default=None)

    def __init__(self, 
                 agent_id: str, 
                 agent_name: str,
                 direct_line_secret: str,
                 capabilities: Dict[str, Any], 
                 role: str = None, 
                 task_id: Optional[int] = None):
        """
        Initialize a CopilotAgentPlugin.

        Args:
            agent_id: The Copilot Studio agent ID
            agent_name: A friendly name for the agent
            direct_line_secret: The Direct Line secret for this specific agent
            capabilities: Dictionary describing agent capabilities
            role: The role of this agent in a crew
            task_id: Optional task ID for tracking purposes
        """
        # Create the plugin name from agent name
        plugin_name = f"{agent_name.replace(' ', '')}Plugin"
        
        # Initialize base class with required name
        super().__init__(name=plugin_name, description=f"Copilot Studio agent: {agent_name}")
        
        # Set private attributes
        self._agent_id = agent_id
        self._agent_name = agent_name
        self._capabilities = capabilities
        self._role = role
        self._task_id = task_id
        self._copilot_client = CopilotStudioClient(direct_line_secret)
        
        # Register the agent function
        self._register_agent_function()
    
    def _register_agent_function(self):
        """Register this agent's function for querying"""
        # Create function name from agent name
        function_name = f"ask_{self._agent_name.lower().replace(' ', '_')}"
        
        # Create description using agent information
        description = (
            f"Ask the {self._agent_name} agent a question or give it a task. "
            f"This agent has the role: {self._role}. "
            f"It has the following capabilities: {json.dumps(self._capabilities)}"
        )
        
        # Create decorated function by using the function directly
        # instead of using kernel_function with metadata argument
        @kernel_function(name=function_name, description=description)
        async def query_agent_wrapper(message: str, conversation_id: Optional[str] = None) -> str:
            """
            Ask the agent a question or give it a task.
            
            Args:
                message: The message to send to the agent
                conversation_id: Optional conversation ID for maintaining context
                
            Returns:
                The agent's response
            """
            return await self.query_agent(message, conversation_id)
        
        # Register the function using the dictionary-like interface
        self[function_name] = query_agent_wrapper

    async def query_agent(self, message: str, conversation_id: Optional[str] = None) -> str:
        """
        Send a query to this Copilot Studio agent.
        
        Args:
            message: The message to send
            conversation_id: Optional conversation ID for maintaining context
            
        Returns:
            The agent's response
        """
        # Use agent call tracker for telemetry if task_id is provided
        if self._task_id:
            with AgentCallTracker(
                agent_id=self._agent_id,
                agent_name=self._agent_name,
                input_message=message
            ) as agent_tracker:
                response = await self._copilot_client.send_message(
                    agent_id=self._agent_id,
                    message=message,
                    conversation_id=conversation_id or f"task_{self._task_id}"
                )
                agent_tracker.response = response
                return response
        else:
            # Without telemetry if no task_id
            return await self._copilot_client.send_message(
                agent_id=self._agent_id,
                message=message,
                conversation_id=conversation_id
            ) 