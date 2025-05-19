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
1. Copilot agents are registered as methods in a dynamically created AgentPool class
2. The AgentPool class is registered as a plugin with the Semantic Kernel
3. When a task is executed, the LLM has direct access to all agents as methods of the plugin
4. The LLM dynamically decides which agent method to call for which part of the task
5. The orchestration happens naturally in the LLM's reasoning process

## Key Components

### 1. AgentPool Class Generation

We dynamically create an `AgentPool` class with methods for each agent in the crew. Each method is decorated with `@kernel_function` and corresponds to a specific agent.

```python
# Dynamically created AgentPool class example
class AgentPool:
    """A dynamically created class with methods for each agent in the crew."""

    @kernel_function(description="Gives you a research report on any topic.")
    async def ask_research_agent(self, message: str, conversation_id: Optional[str] = None) -> str:
        """Send a message to the research agent and get a response."""
        # Implementation that calls the Copilot Studio agent via Direct Line API
        
    @kernel_function(description="Provides a formatted report from a text.")
    async def ask_formatter_agent(self, message: str, conversation_id: Optional[str] = None) -> str:
        """Send a message to the formatter agent and get a response."""
        # Implementation that calls the Copilot Studio agent via Direct Line API
```

### 2. AgentPoolManager

This utility class handles the creation and management of dynamically created AgentPool instances:

```python
class AgentPoolManager:
    @staticmethod
    def create_agent_pool(crew_members, agents, task_id=None):
        # Create a dynamically generated AgentPool class and return an instance
        
    @staticmethod
    def register_with_kernel(agent_pool, kernel, plugin_name="AgentPool"):
        # Register the agent pool with the kernel as a plugin
        
    @staticmethod
    def get_agent_info(agent_pool):
        # Get information about all agents in the pool
```

### 3. CrewKernelManager

This service manages Semantic Kernel instances for each crew, automatically registering the AgentPool class as a plugin when crews are created or updated.

```python
class CrewKernelManager:
    def __init__(self):
        self._kernels = {}  # crew_id -> kernel
        
    async def get_crew_kernel(self, db, crew_id):
        # Get or create a kernel for a crew
        
    async def refresh_crew_kernel(self, db, crew_id):
        # Force refresh a crew's kernel when membership changes
```

### 4. Plugin-Based Task Execution

The task execution now uses the crew's kernel with the AgentPool plugin:

```python
async def execute_task_with_plugins(task_id, db):
    # Initialize task executor
    executor = PluginTaskExecutor(db, task_id)
    
    # Setup kernel with AgentPool plugin
    await executor.setup_kernel()
    
    # Create orchestration function with a prompt
    orchestrator = executor.create_orchestration_function()
    
    # Execute task with LLM orchestration
    result = await orchestrator.invoke(...)
```

## Benefits of the New Approach

1. **True Plugin Architecture**: Agents are now registered as methods of a class that is added as a plugin to the kernel, following Semantic Kernel's plugin design pattern.

2. **Dynamic Class Generation**: The AgentPool class is generated dynamically based on the crew's composition, creating a custom plugin for each crew.

3. **Simplified Method Calls**: The LLM can call agent methods directly using the plugin's namespace, making it more intuitive.

4. **Better Organization**: All agents for a crew are grouped together in a single plugin, making it easier to manage.

5. **Improved Discoverability**: The LLM can more easily discover available agents through the plugin's structure.

6. **Centralized Agent Management**: The AgentPoolManager provides a centralized way to create and manage AgentPool instances.

## Implementation Changes

1. **Dynamic Class Creation**: When crews are created or updated, a custom AgentPool class is dynamically generated with methods for each agent.

2. **Plugin Registration**: The AgentPool instance is registered with the kernel as a plugin, making all agent methods available to the LLM.

3. **Task Execution**: Tasks are executed using the crew's kernel with the AgentPool plugin, allowing the LLM to call agent methods directly.

## Using the New Approach

To create and execute a task using the new plugin-based approach:

1. Create agents with appropriate capabilities
2. Form a crew with these agents
3. Create a task assigned to the crew
4. The task will be automatically executed using the plugin-based approach

The LLM will directly call agent methods when it determines they're needed to solve the task.

## Testing

You can test the new approach using the provided test script:

```bash
python -m app.tests.test_plugin_execution
```

This will create test agents and a crew, then execute a test task using the plugin-based approach. 