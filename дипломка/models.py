from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True)
    email = Column(String, unique=True)
    results = relationship("TaskResult", back_populates="user")

class TaskResult(Base):
    __tablename__ = "task_results"
    id = Column(Integer, primary_key=True, index=True)
    task_name = Column(String)
    score = Column(Integer)
    date = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="results")
