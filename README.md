# AI Agent Orchestration Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A platform for orchestrating teams of AI agents created in Copilot Studio using Semantic Kernel.

> **Note**: This project is for demonstration purposes to showcase AI agent orchestration using Semantic Kernel and Copilot Studio.

**Quick Links:**
- [Features](#features)
- [Setup Instructions](#setup)
- [API Documentation](#api-documentation)
- [Contributing](CONTRIBUTING.md)
- [License](LICENSE)

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Setup](#setup)
- [API Documentation](#api-documentation)
  - [Authentication](#authentication)
  - [Users](#users)
  - [Agents](#agents)
  - [Crews](#crews)
  - [Tasks](#tasks)
  - [Metrics](#metrics)
- [Architecture](#architecture)
- [Observability](#observability)
  - [OpenTelemetry Setup](#opentelemetry-setup)
  - [Starting and Stopping the Collector](#starting-and-stopping-the-collector)
- [Development](#development)

## Overview

The AI Agent Orchestration Platform allows you to create, manage, and orchestrate AI agents in collaborative teams (crews) to perform complex tasks. The platform integrates with Microsoft Copilot Studio for agent capabilities and uses Semantic Kernel for powerful orchestration.

## Features

- **Agent Management**: Create and manage AI agents from Microsoft Copilot Studio
- **Crew Creation**: Form teams of AI agents with specific roles
- **Task Assignment**: Assign tasks to agent crews
- **AI-powered Orchestration**: Automatically determine which agent should handle different parts of a task
- **Real-time Monitoring**: Track task progress and agent performance
- **Analytics Dashboard**: View metrics on agent and crew performance
- **OpenTelemetry Integration**: Full observability with distributed tracing

## Tech Stack

- **Backend**: FastAPI (Python)
- **Database**: SQLite (configurable to any SQLAlchemy compatible database)
- **AI Orchestration**: Microsoft Semantic Kernel
- **Agent Integration**: Microsoft Copilot Studio via Direct Line API
- **Observability**: OpenTelemetry, Prometheus

## Setup

### Prerequisites

- Python 3.9 or higher
- Microsoft Copilot Studio account
- OpenAI API key or Azure OpenAI API key

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd ai-agent-orchestration-platform
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file with your configuration:
   ```
   SECRET_KEY=your-secret-key
   DIRECT_LINE_SECRET=your-copilot-studio-direct-line-secret
   OPENAI_API_KEY=your-openai-api-key
   # Or for Azure OpenAI:
   # AZURE_OPENAI_API_KEY=your-azure-openai-api-key
   # AZURE_OPENAI_ENDPOINT=your-azure-openai-endpoint
   ```

### Initialize the Database

```bash
python -m app.db.init
```

### Running the Application

```bash
uvicorn app.main:app --reload
```

Visit http://localhost:8000/docs to see the API documentation.

## API Documentation

The platform provides a RESTful API with the following endpoints:

### Authentication

#### Login

- **Endpoint**: `POST /api/v1/auth/login`
- **Description**: Authenticate user and get access token
- **Request Body**:
  ```json
  {
    "username": "user@example.com",
    "password": "password"
  }
  ```
- **Response**:
  ```json
  {
    "access_token": "eyJ0eXAi...",
    "token_type": "bearer"
  }
  ```
- **Usage**: Use the returned token in the Authorization header for all authenticated requests:
  ```
  Authorization: Bearer eyJ0eXAi...
  ```

### Users

#### Get Current User

- **Endpoint**: `GET /api/v1/users/me`
- **Description**: Get information about currently authenticated user
- **Authorization**: Required
- **Response**:
  ```json
  {
    "id": 1,
    "email": "user@example.com",
    "full_name": "User Name",
    "is_active": true,
    "is_superuser": false
  }
  ```

#### Update Current User

- **Endpoint**: `PUT /api/v1/users/me`
- **Description**: Update current user's information
- **Authorization**: Required
- **Request Body**:
  ```json
  {
    "full_name": "New Name",
    "email": "new@example.com",
    "password": "newpassword"
  }
  ```

#### Create User

- **Endpoint**: `POST /api/v1/users`
- **Description**: Create a new user
- **Authorization**: Required
- **Request Body**:
  ```json
  {
    "email": "newuser@example.com",
    "password": "password",
    "full_name": "New User"
  }
  ```

### Agents

#### List Agents

- **Endpoint**: `GET /api/v1/agents`
- **Description**: List all available agents
- **Authorization**: Required
- **Query Parameters**:
  - `skip`: Number of agents to skip (default: 0)
  - `limit`: Maximum number of agents to return (default: 100)

#### Create Agent

- **Endpoint**: `POST /api/v1/agents`
- **Description**: Create a new agent
- **Authorization**: Required
- **Request Body**:
  ```json
  {
    "name": "Research Assistant",
    "description": "Helps with research tasks",
    "copilot_id": "12345-abcde",
    "capabilities": {
      "research": true,
      "summarization": true
    }
  }
  ```

#### Get Agent

- **Endpoint**: `GET /api/v1/agents/{agent_id}`
- **Description**: Get information about a specific agent
- **Authorization**: Required
- **Path Parameters**:
  - `agent_id`: ID of the agent

#### Update Agent

- **Endpoint**: `PUT /api/v1/agents/{agent_id}`
- **Description**: Update an existing agent
- **Authorization**: Required
- **Path Parameters**:
  - `agent_id`: ID of the agent
- **Request Body**:
  ```json
  {
    "name": "Updated Name",
    "description": "Updated description",
    "is_active": true
  }
  ```

#### Delete Agent

- **Endpoint**: `DELETE /api/v1/agents/{agent_id}`
- **Description**: Delete an agent
- **Authorization**: Required
- **Path Parameters**:
  - `agent_id`: ID of the agent

### Crews

#### List Crews

- **Endpoint**: `GET /api/v1/crews`
- **Description**: List all agent crews
- **Authorization**: Required
- **Query Parameters**:
  - `skip`: Number of crews to skip (default: 0)
  - `limit`: Maximum number of crews to return (default: 100)

#### Create Crew

- **Endpoint**: `POST /api/v1/crews`
- **Description**: Create a new agent crew
- **Authorization**: Required
- **Request Body**:
  ```json
  {
    "name": "Research Team",
    "description": "Team specialized in research tasks",
    "members": [
      {
        "agent_id": 1,
        "role": "Leader"
      },
      {
        "agent_id": 2,
        "role": "Researcher"
      }
    ]
  }
  ```

#### Get Crew

- **Endpoint**: `GET /api/v1/crews/{crew_id}`
- **Description**: Get information about a specific crew with its members
- **Authorization**: Required
- **Path Parameters**:
  - `crew_id`: ID of the crew

#### Update Crew

- **Endpoint**: `PUT /api/v1/crews/{crew_id}`
- **Description**: Update an existing crew
- **Authorization**: Required
- **Path Parameters**:
  - `crew_id`: ID of the crew
- **Request Body**:
  ```json
  {
    "name": "Updated Team Name",
    "description": "Updated description",
    "members": [
      {
        "agent_id": 3,
        "role": "New Member"
      }
    ]
  }
  ```

#### Delete Crew

- **Endpoint**: `DELETE /api/v1/crews/{crew_id}`
- **Description**: Delete a crew
- **Authorization**: Required
- **Path Parameters**:
  - `crew_id`: ID of the crew

#### Add Crew Member

- **Endpoint**: `POST /api/v1/crews/{crew_id}/members`
- **Description**: Add a new member to a crew
- **Authorization**: Required
- **Path Parameters**:
  - `crew_id`: ID of the crew
- **Request Body**:
  ```json
  {
    "agent_id": 4,
    "role": "Specialist"
  }
  ```

#### Remove Crew Member

- **Endpoint**: `DELETE /api/v1/crews/{crew_id}/members/{member_id}`
- **Description**: Remove a member from a crew
- **Authorization**: Required
- **Path Parameters**:
  - `crew_id`: ID of the crew
  - `member_id`: ID of the crew member

### Tasks

#### List Tasks

- **Endpoint**: `GET /api/v1/tasks`
- **Description**: List all tasks
- **Authorization**: Required
- **Query Parameters**:
  - `skip`: Number of tasks to skip (default: 0)
  - `limit`: Maximum number of tasks to return (default: 100)

#### Create Task

- **Endpoint**: `POST /api/v1/tasks`
- **Description**: Create a new task and assign it to a crew
- **Authorization**: Required
- **Request Body**:
  ```json
  {
    "title": "Research Task",
    "description": "Research quantum computing advancements in 2023",
    "crew_id": 1
  }
  ```

#### Get Task

- **Endpoint**: `GET /api/v1/tasks/{task_id}`
- **Description**: Get information about a specific task including messages
- **Authorization**: Required
- **Path Parameters**:
  - `task_id`: ID of the task

#### Update Task

- **Endpoint**: `PUT /api/v1/tasks/{task_id}`
- **Description**: Update an existing task
- **Authorization**: Required
- **Path Parameters**:
  - `task_id`: ID of the task
- **Request Body**:
  ```json
  {
    "title": "Updated Task Title",
    "description": "Updated task description",
    "status": "in_progress"
  }
  ```

#### Add Task Message

- **Endpoint**: `POST /api/v1/tasks/{task_id}/messages`
- **Description**: Add a message to a task
- **Authorization**: Required
- **Path Parameters**:
  - `task_id`: ID of the task
- **Request Body**:
  ```json
  {
    "content": "Additional information for the task",
    "agent_id": 1,
    "is_system": false
  }
  ```

#### Delete Task

- **Endpoint**: `DELETE /api/v1/tasks/{task_id}`
- **Description**: Delete a task
- **Authorization**: Required
- **Path Parameters**:
  - `task_id`: ID of the task

### Metrics

#### Dashboard Metrics

- **Endpoint**: `GET /api/v1/metrics/dashboard`
- **Description**: Get dashboard metrics for the current user
- **Authorization**: Required
- **Query Parameters**:
  - `days`: Number of days to include in metrics (default: 30)
- **Response**: Comprehensive metrics including task stats, crew performance, and agent usage

#### Task Statistics

- **Endpoint**: `GET /api/v1/metrics/tasks/stats`
- **Description**: Get detailed task statistics
- **Authorization**: Required
- **Query Parameters**:
  - `days`: Number of days to include in statistics (default: 30)

#### LLM and Agent Telemetry

- **Endpoint**: `GET /api/v1/metrics/telemetry`
- **Description**: Get detailed telemetry for LLM calls, agent interactions, and task execution
- **Authorization**: Required
- **Response**: JSON with metrics for LLM usage (calls, tokens, latency, cost), agent usage (calls, latency, success rate), and task execution stats
- **Use Case**: For building dashboards to monitor AI performance and usage trends

#### Raw Telemetry Data

- **Endpoint**: `GET /api/v1/metrics/telemetry/raw`
- **Description**: Get raw Prometheus-format metrics for all telemetry data
- **Authorization**: Required
- **Response**: Plain text in Prometheus exposition format
- **Use Case**: For scraping by Prometheus or other monitoring tools

## Architecture

The platform follows a modern API architecture with the following components:

1. **API Layer**: FastAPI routes handle HTTP requests
2. **Service Layer**: Business logic for task execution and agent coordination
3. **Data Layer**: SQLAlchemy ORM for database operations
4. **Integration Layer**: Connects with Copilot Studio and Semantic Kernel

Key architectural patterns:
- Dependency Injection for database and security
- Repository pattern for data access
- Asynchronous task execution
- Event-driven communication between agents

## Observability

The platform includes comprehensive observability features:

- **Distributed Tracing**: OpenTelemetry integration tracks requests across services
- **Metrics**: Prometheus-compatible metrics endpoint at `/metrics`
- **Logging**: Structured logging with context

### OpenTelemetry Setup

To enable OpenTelemetry:

1. Configure the collector endpoint in `.env`:
   ```
   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
   ```

2. Ensure you have the collector configuration file (`otel-collector-config.yaml`) in your project root:
   ```yaml
   receivers:
     otlp:
       protocols:
         grpc:
           endpoint: 0.0.0.0:4317
         http:
           endpoint: 0.0.0.0:4318

   processors:
     batch:
       timeout: 1s
       send_batch_size: 1024

   exporters:
     logging:
       loglevel: debug
     file:
       path: ./otel-traces.json

   service:
     pipelines:
       traces:
         receivers: [otlp]
         processors: [batch]
         exporters: [logging, file]
       metrics:
         receivers: [otlp]
         processors: [batch]
         exporters: [logging, file]
   ```

### Starting and Stopping the Collector

#### Starting the OpenTelemetry Collector

Before starting your FastAPI server, start the OpenTelemetry collector:

1. Download the collector binary if you haven't already:
   ```bash
   # For macOS (ARM64):
   mkdir -p bin
   curl -L https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.96.0/otelcol-contrib_0.96.0_darwin_arm64.tar.gz -o otelcol.tar.gz
   tar -xzf otelcol.tar.gz -C bin
   rm otelcol.tar.gz
   
   # For macOS (Intel):
   mkdir -p bin
   curl -L https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.96.0/otelcol-contrib_0.96.0_darwin_amd64.tar.gz -o otelcol.tar.gz
   tar -xzf otelcol.tar.gz -C bin
   rm otelcol.tar.gz
   
   # For Linux:
   mkdir -p bin
   curl -L https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.96.0/otelcol-contrib_0.96.0_linux_amd64.tar.gz -o otelcol.tar.gz
   tar -xzf otelcol.tar.gz -C bin
   rm otelcol.tar.gz
   ```

2. Start the collector in a terminal:
   ```bash
   bin/otelcol-contrib --config=otel-collector-config.yaml
   ```
   
   You should see log output indicating the collector has started successfully.

3. In a new terminal session, start your FastAPI server:
   ```bash
   uvicorn app.main:app --reload
   ```

#### Stopping the OpenTelemetry Collector

To properly shut down the services:

1. Stop the FastAPI server first (Ctrl+C in its terminal)

2. Stop the OpenTelemetry collector (Ctrl+C in its terminal)

3. If the collector is running in the background, find and stop it:
   ```bash
   # Find the process ID
   ps aux | grep otelcol
   
   # Stop the process
   kill <process_id>
   ```

4. Verify the telemetry data was captured in `otel-traces.json`

#### Troubleshooting

If you see warnings about connection failures:

```
UNAVAILABLE encountered while exporting traces to localhost:4317
```

Make sure:
1. The collector is running and listening on port 4317
2. There are no firewall restrictions blocking the connection
3. The configuration in both the application and collector match

If you want to disable telemetry temporarily, set the environment variable before starting the server:
```bash
OTEL_EXPORTER_OTLP_ENDPOINT="" uvicorn app.main:app --reload
```

## Development

### Running Tests

```bash
pytest
```

### Code Structure

- `app/api`: API routes and endpoints
- `app/core`: Core configuration and security
- `app/db`: Database setup and initialization
- `app/models`: SQLAlchemy models
- `app/schemas`: Pydantic schemas for validation
- `app/services`: Business logic services
- `app/observability`: Telemetry and monitoring

### Best Practices

- Create new agents in Copilot Studio before adding them to the platform
- Form crews with complementary agent capabilities
- Monitor task execution through the metrics dashboard
- Use background tasks for long-running operations

## License

MIT 