from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core import config

DATABASE_URL = config.DATABASE_URL  # la cargaremos del .env

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependencia de FastAPI para obtener una sesión de BD."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()