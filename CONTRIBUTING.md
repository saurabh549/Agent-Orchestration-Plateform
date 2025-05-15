# Contributing to AI Agent Orchestration Platform

Thank you for considering contributing to the AI Agent Orchestration Platform! This document provides guidelines and instructions for contributing.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/ai-agent-orchestration-platform.git`
3. Create a new branch for your feature: `git checkout -b feature/your-feature-name`

## Setup Development Environment

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file based on `.env-example`:
   ```bash
   cp .env-example .env
   # Edit .env with your configuration
   ```

4. Initialize the database:
   ```bash
   python -m app.db.init
   ```

5. Run the application:
   ```bash
   uvicorn app.main:app --reload
   ```

## Development Guidelines

- Follow [PEP 8](https://pep8.org/) style guide for Python code
- Write tests for new features
- Keep the codebase organized according to the existing structure
- Document your code and update the README if necessary

## Pull Request Process

1. Update your fork with the latest changes from the main repository
2. Ensure your code passes all tests
3. Update documentation as needed
4. Submit a pull request with a clear description of the changes and their purpose

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

Thank you for your contributions! 