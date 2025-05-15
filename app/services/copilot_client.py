import aiohttp
import json
from typing import Dict, List, Any, Optional
import uuid
import asyncio

class CopilotStudioClient:
    """Client for communicating with Copilot Studio agents via Direct Line API."""
    
    def __init__(self, direct_line_secret: str):
        self.direct_line_secret = direct_line_secret
        self.base_url = "https://directline.botframework.com/v3/directline"
        self.conversations = {}  # Store conversation IDs and watermarks
        
    async def _start_conversation(self) -> str:
        """Start a new conversation and return conversation ID."""
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self.direct_line_secret}",
                "Content-Type": "application/json"
            }
            
            async with session.post(
                f"{self.base_url}/conversations",
                headers=headers
            ) as response:
                if response.status != 201:
                    error_text = await response.text()
                    raise Exception(f"Failed to start conversation: {error_text}")
                
                data = await response.json()
                return data["conversationId"]
    
    async def _get_conversation_id(self, conversation_id: Optional[str] = None) -> str:
        """Get an existing conversation ID or create a new one."""
        if conversation_id and conversation_id in self.conversations:
            return conversation_id
        
        # Start a new conversation
        new_id = conversation_id or f"conv_{uuid.uuid4()}"
        self.conversations[new_id] = {
            "id": await self._start_conversation(),
            "watermark": None
        }
        return new_id
    
    async def send_message(
        self, 
        agent_id: str,
        message: str, 
        conversation_id: Optional[str] = None
    ) -> str:
        """Send a message to the Copilot Studio agent and return the response."""
        conv_key = await self._get_conversation_id(conversation_id)
        conv_data = self.conversations[conv_key]
        
        # Send message
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self.direct_line_secret}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "type": "message",
                "from": {
                    "id": "user"
                },
                "text": message,
                "channelData": {
                    "agentId": agent_id
                }
            }
            
            async with session.post(
                f"{self.base_url}/conversations/{conv_data['id']}/activities",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200 and response.status != 201:
                    error_text = await response.text()
                    raise Exception(f"Failed to send message: {error_text}")
            
            # Wait and retrieve bot response
            return await self._get_bot_response(conv_key, conv_data["id"])
    
    async def _get_bot_response(self, conv_key: str, direct_line_conv_id: str) -> str:
        """Retrieve the bot's response from the conversation."""
        watermark = self.conversations[conv_key].get("watermark")
        
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self.direct_line_secret}"
            }
            
            url = f"{self.base_url}/conversations/{direct_line_conv_id}/activities"
            if watermark:
                url += f"?watermark={watermark}"
            
            # Poll for response (with retry logic)
            max_retries = 5
            retry_count = 0
            
            while retry_count < max_retries:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Failed to get bot response: {error_text}")
                    
                    data = await response.json()
                    
                    # Update watermark
                    self.conversations[conv_key]["watermark"] = data.get("watermark")
                    
                    # Find bot responses
                    bot_messages = []
                    for activity in data.get("activities", []):
                        if activity.get("from", {}).get("id") != "user":
                            bot_messages.append(activity)
                    
                    if bot_messages:
                        # Return the latest bot message text
                        return bot_messages[-1].get("text", "")
                
                # Wait before polling again
                await asyncio.sleep(1)
                retry_count += 1
            
            raise Exception("No response received from bot after maximum retries") 