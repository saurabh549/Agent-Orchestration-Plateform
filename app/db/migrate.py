import logging
from sqlalchemy import Column, String, MetaData, Table, inspect
from sqlalchemy.sql import text

from app.db.base import engine, SessionLocal
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_direct_line_secret_to_agents():
    """
    Add direct_line_secret column to agents table
    """
    db = SessionLocal()
    try:
        # Check if column exists
        inspector = inspect(engine)
        columns = [col["name"] for col in inspector.get_columns("agents")]
        
        if "direct_line_secret" not in columns:
            logger.info("Adding direct_line_secret column to agents table")
            with engine.begin() as conn:
                # For SQLite
                if "sqlite" in settings.DATABASE_URL:
                    conn.execute(text("ALTER TABLE agents ADD COLUMN direct_line_secret VARCHAR"))
                # For PostgreSQL
                else:
                    conn.execute(text("ALTER TABLE agents ADD COLUMN direct_line_secret VARCHAR"))
            
            # Update existing rows to use the global secret
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE agents SET direct_line_secret = :secret"),
                    {"secret": settings.DIRECT_LINE_SECRET}
                )
            
            logger.info("Migration completed: Added direct_line_secret column to agents table")
        else:
            logger.info("Column direct_line_secret already exists in agents table")
    finally:
        db.close()

def main():
    logger.info("Running database migrations")
    add_direct_line_secret_to_agents()
    logger.info("Database migrations completed")

if __name__ == "__main__":
    main() 