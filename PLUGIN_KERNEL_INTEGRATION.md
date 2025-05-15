# Copilot Agent Integration with Semantic Kernel Plugins

This document explains the implementation of Copilot Studio agents as Semantic Kernel plugins in the AI Agent Orchestration Platform.

## Overview

In the new approach, we've changed how agent orchestration works:

**Previous Approach:**
1. LLM would create a detailed plan with fixed subtasks
2. Each subtask would be assigned to a specific agent
3. Code would manually execute each subtask with the assigned agent
4. Results would be aggregated by another LLM call

**New Plugin-Based Approach:**
1. Copilot agents are registered as Semantic Kernel plugins when a crew is created
2. When a task is executed, the LLM has direct access to all agents as functions
3. The LLM dynamically decides which agent to call for which part of the task
4. The LLM can make follow-up calls to agents based on previous responses
5. The orchestration happens naturally in the LLM's reasoning process

## Key Components

### 1. CopilotAgentPlugin

This class wraps a Copilot Studio agent as a Semantic Kernel plugin. It registers a function that can be called by the LLM to interact with the agent.

```python
class CopilotAgentPlugin(KernelPlugin):
    def __init__(self, copilot_client, agent_id, agent_name, capabilities, role=None, task_id=None):
        # Initialize plugin
        
    def _register_functions(self):
        # Register a function for this agent that the LLM can call
        
    async def query_agent(self, message, conversation_id=None):
        # Send a query to the Copilot Studio agent with telemetry tracking
```

### 2. CrewKernelManager

This service manages Semantic Kernel instances for each crew, automatically registering agents as plugins when crews are created or updated.

```python
class CrewKernelManager:
    def __init__(self):
        self._kernels = {}  # crew_id -> kernel
        
    async def get_crew_kernel(self, db, crew_id):
        # Get or create a kernel for a crew
        
    async def refresh_crew_kernel(self, db, crew_id):
        # Force refresh a crew's kernel when membership changes
        
    def get_crew_plugin_info(self, crew_id):
        # Get info about plugins registered for a crew
```

### 3. Plugin-Based Task Execution

The task execution now uses the crew's kernel with agent plugins:

```python
async def execute_task_with_crew_kernel(task_id, db):
    # Get the crew's kernel with agent plugins
    kernel = await crew_kernel_manager.get_crew_kernel(db, task.crew_id)
    
    # Create orchestration function with a prompt
    orchestrator = kernel.create_function_from_prompt(...)
    
    # Execute task with LLM orchestration
    result = await orchestrator.invoke(context)
```

## API Endpoints

The following new API endpoints have been added:

- `GET /api/v1/crews/{crew_id}/kernel/info` - Get information about a crew's kernel plugins
- `POST /api/v1/crews/{crew_id}/kernel/refresh` - Force refresh a crew's kernel

## Benefits of the New Approach

1. **Dynamic Decision-Making**: The LLM can decide on the fly which agent to use based on the context and previous responses.

2. **Natural Conversation Flow**: The LLM can have a more natural back-and-forth with agents when needed.

3. **Simplified Architecture**: No need for a separate planning step - the LLM directly calls the appropriate agents.

4. **Better Context Retention**: The LLM maintains the full context of the conversation, leading to better results.

5. **Improved Flexibility**: The LLM can adapt its approach as it learns more about the task from agent responses.

## Implementation Changes

1. **Crew Creation/Updates**: When crews are created or updated, agent plugins are automatically registered with the Semantic Kernel.

2. **Task Execution**: Tasks are now executed using the crew's Semantic Kernel with agent plugins.

3. **Legacy Support**: The previous approach is still available via the `/api/v1/tasks/legacy` endpoint for backward compatibility.

## Using the New Approach

To create and execute a task using the new plugin-based approach:

1. Create agents with appropriate capabilities
2. Form a crew with these agents
3. Create a task assigned to the crew
4. The task will be automatically executed using the plugin-based approach

The LLM will directly call agent functions when it determines they're needed to solve the task.

## Testing

You can test the new approach using the provided test script:

```bash
python -m app.tests.test_plugin_execution
```

This will create test agents and a crew, then execute a test task using the plugin-based approach. 