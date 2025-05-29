import logging
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db.base import SessionLocal, engine
from app.db.init_db import init_db
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_observability_tables(db: Session) -> None:
    """
    Create tables for LLM calls and agent executions tracking
    """
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        if "llm_calls" not in existing_tables:
            logger.info("Creating llm_calls table")
            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE llm_calls (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        model VARCHAR NOT NULL,
                        function_name VARCHAR NOT NULL,
                        prompt_tokens INTEGER NOT NULL,
                        completion_tokens INTEGER NOT NULL,
                        latency FLOAT NOT NULL,
                        cost FLOAT NOT NULL,
                        status VARCHAR NOT NULL,
                        error_message VARCHAR,
                        timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        prompt TEXT,
                        response TEXT
                    )
                """))
            logger.info("Created llm_calls table")

        if "agent_executions" not in existing_tables:
            logger.info("Creating agent_executions table")
            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE agent_executions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        agent_id VARCHAR NOT NULL,
                        agent_name VARCHAR NOT NULL,
                        input_message TEXT,
                        output_message TEXT,
                        status VARCHAR NOT NULL,
                        error_message VARCHAR,
                        latency FLOAT NOT NULL,
                        timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        metadata JSON
                    )
                """))
            logger.info("Created agent_executions table")

        if "task_executions" not in existing_tables:
            logger.info("Creating task_executions table")
            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE task_executions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id INTEGER NOT NULL,
                        crew_id INTEGER NOT NULL,
                        description TEXT NOT NULL,
                        status VARCHAR NOT NULL,
                        start_time DATETIME NOT NULL,
                        end_time DATETIME,
                        duration FLOAT,
                        result JSON,
                        error_message VARCHAR
                    )
                """))
            logger.info("Created task_executions table")

        if "task_llm_calls" not in existing_tables:
            logger.info("Creating task_llm_calls table")
            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE task_llm_calls (
                        task_id INTEGER NOT NULL,
                        llm_call_id INTEGER NOT NULL,
                        PRIMARY KEY (task_id, llm_call_id),
                        FOREIGN KEY (task_id) REFERENCES task_executions (id),
                        FOREIGN KEY (llm_call_id) REFERENCES llm_calls (id)
                    )
                """))
            logger.info("Created task_llm_calls table")

        if "task_agent_executions" not in existing_tables:
            logger.info("Creating task_agent_executions table")
            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE task_agent_executions (
                        task_id INTEGER NOT NULL,
                        agent_execution_id INTEGER NOT NULL,
                        PRIMARY KEY (task_id, agent_execution_id),
                        FOREIGN KEY (task_id) REFERENCES task_executions (id),
                        FOREIGN KEY (agent_execution_id) REFERENCES agent_executions (id)
                    )
                """))
            logger.info("Created task_agent_executions table")

    except Exception as e:
        logger.error(f"Error creating observability tables: {str(e)}")
        raise

def add_direct_line_secret_to_agents(db: Session) -> None:
    """
    Add direct_line_secret column to agents table
    """
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
            
            logger.info("Migration completed: Added direct_line_secret column to agents table")
        else:
            logger.info("Column direct_line_secret already exists in agents table")
    except Exception as e:
        logger.error(f"Error adding direct_line_secret column: {str(e)}")
        raise

def init() -> None:
    db = SessionLocal()
    try:
        logger.info("Initializing database")
        # Initialize base tables and create superuser
        init_db(db)
        
        # Create observability tables
        logger.info("Creating observability tables")
        create_observability_tables(db)
        
        # Add direct_line_secret to agents table
        logger.info("Adding direct_line_secret to agents table")
        add_direct_line_secret_to_agents(db)
        
        logger.info("Database initialized successfully")
    finally:
        db.close()

def main() -> None:
    logger.info("Creating database tables and running migrations")
    init()
    logger.info("Database setup completed")

if __name__ == "__main__":
    main() 