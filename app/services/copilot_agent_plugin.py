import json
from typing import Dict, Any, Optional, List

from semantic_kernel.functions import kernel_function
from semantic_kernel.functions.kernel_function_metadata import KernelFunctionMetadata
from semantic_kernel.plugins import KernelPlugin

from app.services.copilot_client import CopilotStudioClient
from app.observability.telemetry import AgentCallTracker


class CopilotAgentPlugin(KernelPlugin):
    """
    A Semantic Kernel plugin that wraps Copilot Studio agents as plugin functions.
    This allows LLMs to decide when to invoke which Copilot agent based on the task context.
    """

    def __init__(self, 
                 copilot_client: CopilotStudioClient, 
                 agent_id: str, 
                 agent_name: str, 
                 capabilities: Dict[str, Any], 
                 role: str = None, 
                 task_id: Optional[int] = None):
        """
        Initialize a CopilotAgentPlugin.

        Args:
            copilot_client: The CopilotStudioClient instance for API communication
            agent_id: The Copilot Studio agent ID
            agent_name: A friendly name for the agent
            capabilities: Dictionary describing agent capabilities
            role: The role of this agent in a crew
            task_id: Optional task ID for tracking purposes
        """
        self.copilot_client = copilot_client
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.capabilities = capabilities
        self.role = role
        self.task_id = task_id
        self.functions = {}
        
        # Register the agent function
        self._register_functions()

    def _register_functions(self):
        """Register this agent's functions"""
        
        # Create metadata for the main query function
        function_name = f"ask_{self.agent_name.lower().replace(' ', '_')}"
        description = (
            f"Ask the {self.agent_name} agent a question or give it a task. "
            f"This agent has the role: {self.role}. "
            f"It has the following capabilities: {json.dumps(self.capabilities)}"
        )
        
        metadata = KernelFunctionMetadata(
            name=function_name,
            description=description,
            parameters=[
                ("message", "string", "The message to send to the agent"),
                ("conversation_id", "string", "Optional conversation ID for maintaining context", False)
            ],
            return_description="The agent's response"
        )
        
        # Create the function and add it to this plugin's functions
        self.functions[function_name] = kernel_function(metadata=metadata)(self.query_agent)

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
        if self.task_id:
            with AgentCallTracker(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                input_message=message
            ) as agent_tracker:
                response = await self.copilot_client.send_message(
                    agent_id=self.agent_id,
                    message=message,
                    conversation_id=conversation_id or f"task_{self.task_id}"
                )
                agent_tracker.response = response
                return response
        else:
            # Without telemetry if no task_id
            return await self.copilot_client.send_message(
                agent_id=self.agent_id,
                message=message,
                conversation_id=conversation_id
            ) 