import logging

from app.db.base import SessionLocal
from app.db.init_db import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init() -> None:
    db = SessionLocal()
    try:
        logger.info("Initializing database")
        init_db(db)
        logger.info("Database initialized successfully")
    finally:
        db.close()

def main() -> None:
    logger.info("Creating database tables")
    init()
    logger.info("Database tables created")

if __name__ == "__main__":
    main() 