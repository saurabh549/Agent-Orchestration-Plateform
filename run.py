import uvicorn
import os
import sys
import logging
import socket
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def is_port_in_use(port):
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def find_available_port(start_port, max_attempts=10):
    """Find an available port starting from start_port."""
    port = start_port
    for _ in range(max_attempts):
        if not is_port_in_use(port):
            return port
        port += 1
    return None

def main():
    """Run the API server."""
    logger.info("Starting AI Agent Orchestration Platform")
    
    # Initialize database if needed
    if len(sys.argv) > 1 and sys.argv[1] == "--init-db":
        logger.info("Initializing database...")
        from app.db.init import init
        init()
        logger.info("Database initialized successfully!")
    
    # Run API server
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    
    # Check if the port is already in use
    if is_port_in_use(port):
        logger.warning(f"Port {port} is already in use. Looking for an available port...")
        available_port = find_available_port(port + 1)
        if available_port:
            logger.info(f"Using alternative port {available_port}")
            port = available_port
        else:
            logger.error("No available ports found. Please free up a port or specify a different port.")
            sys.exit(1)
    
    logger.info(f"Starting server at http://{host}:{port}")
    logger.info(f"API documentation available at http://{host}:{port}/docs")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main() 