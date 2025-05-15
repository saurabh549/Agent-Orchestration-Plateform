import uvicorn
import os
import sys
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

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