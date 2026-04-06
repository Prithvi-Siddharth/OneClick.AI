# Has all the schemas for tables in the database
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

# users table
class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    profile_pic_url = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Folder(Base):
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    parent_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    user_id = Column(Integer, nullable=False)
    folder_type = Column(String(50), nullable=False) # "dataset" or "model"
    created_at = Column(DateTime, default=datetime.utcnow)

class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False) # Foreign Key relationship to be enforced by application logic or add ForeignKey
    filename = Column(String(255), nullable=False)
    s3_key = Column(String(1024), nullable=False)
    s3_bucket = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    row_count = Column(Integer, nullable=True)
    upload_date = Column(DateTime, default=datetime.utcnow)
    description = Column(String(255), nullable=True)
    feature_schema = Column(String(4096), nullable=True) # Storing JSON as string
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True)

class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=True) # Added name
    target_column = Column(String(255), nullable=True)
    algorithm = Column(String(100), nullable=True)
    hyperparameters = Column(String(4096), nullable=True) # JSON as string
    metrics = Column(String(4096), nullable=True) # JSON as string
    status = Column(String(50), default="PENDING")
    model_artifact_path = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True)

class TemporaryDataset(Base):
    __tablename__ = "temp"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    s3_key = Column(String(1024), nullable=False)
    s3_bucket = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    row_count = Column(Integer, nullable=True)
    upload_date = Column(DateTime, default=datetime.utcnow)
    feature_schema = Column(String(4096), nullable=True)
    filename = Column(String(255), nullable=False)

class PreprocessingLog(Base):
    __tablename__ = "preprocessing_logs"

    id = Column(Integer, primary_key=True, index=True)
    temp_dataset_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False)
    operation_type = Column(String(255), nullable=False)
    operation_name = Column(String(255), nullable=False)
    attributes = Column(String(4096), nullable=True) # JSON list of attributes
    timestamp = Column(DateTime, default=datetime.utcnow)

class Note(Base):
    __tablename__ = 'notes'
    
    note_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    note_text = Column(String(10000), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)