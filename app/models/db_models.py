from sqlalchemy import Column, String, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, index=True)
    google_refresh_token = Column(String, nullable=True)
    sunat_ruc = Column(String, nullable=True)
    sunat_usuario = Column(String, nullable=True)
    sunat_clave = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    jobs = relationship("Job", back_populates="user")

class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"))
    status = Column(String, default="pending")
    excel_filename = Column(String, nullable=True)
    excel_path = Column(String, nullable=True)
    message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    details = Column(JSON, nullable=True)

    user = relationship("User", back_populates="jobs")