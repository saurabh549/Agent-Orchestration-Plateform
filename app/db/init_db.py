from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.base import Base, engine
from app.models import User  # Import from app.models to ensure all models are loaded
from app.core.config import settings

# Create all tables
def init_db(db: Session) -> None:
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Check if we should create initial superuser
    user = db.query(User).filter(User.email == "admin@example.com").first()
    if not user:
        user = User(
            email="admin@example.com",
            hashed_password=get_password_hash("admin"),
            full_name="Admin User",
            is_superuser=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user) 