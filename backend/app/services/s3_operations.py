# This file handles all interactions with AWS S3 storage.
# It helps us:
# 1. Connect to S3 securely.
# 2. Upload different types of files (CSV, JSON, Excel).
# 3. Read file details (like row counts and column names) before saving.
# 4. Save the file info into our database so we can find it later.
# 5. Read files from S3 and return a preview of the data (as a list of dictionaries).

import os
import boto3
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from botocore.exceptions import NoCredentialsError
from app.models import Dataset, Experiment

# Ensure that you have AWS credentials in your environment variables:
# AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION

def get_user_datasets(db: Session, user_id: int, limit: int = None):
    """
    Retrieves the list of datasets uploaded by the user, ordered by most recent first.
    """
    query = db.query(Dataset).filter(Dataset.user_id == user_id).order_by(Dataset.id.desc())
    
    if limit:
        query = query.limit(limit)
        
    datasets = query.all()
    # Return a list of dictionaries or objects
    return datasets

def get_user_models(db: Session, user_id: int, limit: int = None):
    """
    Retrieves the list of models trained by the user, ordered by most recent first.
    """
    query = db.query(Experiment).filter(Experiment.dataset_id.in_(
        db.query(Dataset.id).filter(Dataset.user_id == user_id)
    )).order_by(Experiment.id.desc())
    
    if limit:
        query = query.limit(limit)
        
    models = query.all()
    return models

def get_s3_client():
    """
    Initialize and return a boto3 S3 client.
    """
    return boto3.client(
        's3',
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "us-east-1")
    )

def read_dataset_from_s3(bucket_name: str, s3_key: str, filename: str, preview_limit: int = 100):
    """
    Reads a file from S3 and returns a preview of the data (as a list of dictionaries).
    """
    s3 = get_s3_client()
    try:
        # Get object from S3
        response = s3.get_object(Bucket=bucket_name, Key=s3_key)
        file_stream = response['Body']
        
        ext = filename.lower().split('.')[-1]
        df = None

        if ext == 'csv':
            df = pd.read_csv(file_stream, nrows=preview_limit)
        elif ext == 'json':
            # Identify if it is newline-delimited JSON or standard list-of-dicts
            # Check first char or just try both
            # Since S3 stream is not seekable easily once read, we might need to read into buffer
            # BUT for preview, let's treat it simple:
            try:
                # Try lines=True first (common for large datasets)
                df = pd.read_json(file_stream, orient='records', lines=True, nrows=preview_limit)
            except ValueError:
                # Fallback necessitates seeking or re-reading, but stream is consumed.
                # Only way is to download to memory first if we are unsure.
                # For robustness, let's read content to BytesIO first
                from io import BytesIO
                file_content = response['Body'].read() # Re-read full body if needed or just handle valid JSON
                df = pd.read_json(BytesIO(file_content))
                if len(df) > preview_limit:
                    df = df.head(preview_limit)
        elif ext in ['xls', 'xlsx']:
            # Excel requires seekable stream or file
            from io import BytesIO
            content = file_stream.read()
            df = pd.read_excel(BytesIO(content), nrows=preview_limit)
        else:
            return {"error": f"Unsupported file extension: {ext}"}

        if df is not None:
            # Replace NaNs with None for valid JSON serialization
            df = df.where(pd.notnull(df), None)
            return df.to_dict(orient='records')
            
    except Exception as e:
        print(f"Error reading from S3: {e}")
        return {"error": str(e)}

def upload_file_to_s3(file_obj, bucket_name: str, s3_key: str) -> bool:
    """
    Uploads a file to S3.
    Buffered reader/file-like object is expected.
    """
    s3 = get_s3_client()
    try:
        # Use the underlying file object if this is a FastAPI UploadFile
        actual_file = getattr(file_obj, "file", file_obj)
        s3.upload_fileobj(actual_file, bucket_name, s3_key)
        return True
    except NoCredentialsError:
        print("Credentials not available")
        return False
    except Exception as e:
        print(f"Failed to upload to S3: {e}")
        return False

def inspect_dataset_metadata(file_obj, filename):
    """
    Reads the file to extract metadata (rows, schema).
    Supports CSV, JSON, and Excel.
    """
    ext = filename.lower().split('.')[-1]
    
    try:
        # Use the underlying file object if this is a FastAPI UploadFile
        actual_file = getattr(file_obj, "file", file_obj)
        
        # 1. Reset buffer
        actual_file.seek(0)
        
        row_count = 0
        schema = {}

        if ext == 'csv':
            # Schema
            df_preview = pd.read_csv(actual_file, nrows=5)
            schema = {col: str(dtype) for col, dtype in df_preview.dtypes.items()}
            
            # Row Count
            actual_file.seek(0)
            for chunk in pd.read_csv(actual_file, usecols=[0], chunksize=10000):
                row_count += len(chunk)

        elif ext == 'json':
            # Try line-delimited first, then standard JSON
            try:
                # Schema
                df_preview = pd.read_json(actual_file, orient='records', lines=True, nrows=5)
                schema = {col: str(dtype) for col, dtype in df_preview.dtypes.items()}
                
                # Row count
                actual_file.seek(0)
                # For JSON lines, we can chunk
                for chunk in pd.read_json(actual_file, orient='records', lines=True, chunksize=10000):
                    row_count += len(chunk)
            except ValueError:
                # Fallback to standard JSON (loads entire file, acceptable for JSON limits usually)
                actual_file.seek(0)
                df = pd.read_json(actual_file)
                row_count = len(df)
                schema = {col: str(dtype) for col, dtype in df.dtypes.items()}

        elif ext in ['xls', 'xlsx']:
            # Excel does not support chunking well, load into memory
            # Engine 'openpyxl' for xlsx, 'xlrd' for xls (if installed), default auto-detect
            df = pd.read_excel(actual_file)
            row_count = len(df)
            schema = {col: str(dtype) for col, dtype in df.dtypes.items()}

        else:
            # Fallback or unknown
            print(f"Unsupported file extension: {ext}")
            return 0, {}

        return row_count, schema

    except Exception as e:
        print(f"Error inspecting file {filename}: {e}")
        return 0, {}

def process_and_save_dataset(
    db: Session,
    user_id: int,
    file_obj,
    filename: str,
    bucket_name: str,
    description: str
) -> Dataset:
    """
    Orchestrator function to:
    1. Generate a unique S3 key.
    2. Extract metadata.
    3. Upload file to S3.
    4. Save record to TiDB.
    """
    
    # 1. Generate Unique Key
    # Organization: {user_id}/datasets/{timestamp}_{filename}
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    s3_key = f"{user_id}/datasets/{timestamp}_{filename}"
    
    # 2. Calculate Metadata & Size (BEFORE upload to avoid closed file issues)
    # Use the underlying file object if this is a FastAPI UploadFile
    actual_file = getattr(file_obj, "file", file_obj)

    # Get Size
    actual_file.seek(0, os.SEEK_END)
    file_size = actual_file.tell()
    actual_file.seek(0)
    
    # Get Schema and Rows
    row_count, schema_dict = inspect_dataset_metadata(file_obj, filename)

    # Reset stream for upload
    actual_file.seek(0)
    
    # 3. Upload to S3
    success = upload_file_to_s3(file_obj, bucket_name, s3_key)
    if not success:
        raise Exception("Failed to upload file to S3")
    
    # 4. Save to DB
    new_dataset = Dataset(
        user_id=user_id,
        filename=filename,
        s3_key=s3_key,
        s3_bucket=bucket_name,
        file_size=file_size,
        row_count=row_count,
        feature_schema=str(schema_dict) 
    )

    db.add(new_dataset)
    db.commit()
    db.refresh(new_dataset)
    
    return new_dataset

def upload_model_to_s3(
    db: Session,
    file_obj, 
    bucket_name: str, 
    user_id: int, 
    model_name: str,
    dataset_id: int,
    algorithm: str
) -> Experiment:
    """
    Uploads a trained model (joblib file) to S3 and saves metadata to TiDB.
    """
    # Generate Unique Key
    # Organization: {user_id}/models/{timestamp}_{model_name}
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    
    # Ensure extension
    if not model_name.endswith('.joblib') and not model_name.endswith('.pkl'):
        model_name += ".joblib"
        
    s3_key = f"{user_id}/models/{timestamp}_{model_name}"
    
    # Upload
    success = upload_file_to_s3(file_obj, bucket_name, s3_key)
    
    if not success:
        raise Exception("Failed to upload model to S3")

    # Save Metadata to TiDB
    new_experiment = Experiment(
        dataset_id=dataset_id, # Assuming we know which dataset this model is based on
        name=model_name,
        algorithm=algorithm,
        model_artifact_path=s3_key,
        status="COMPLETED"
    )
    db.add(new_experiment)
    db.commit()
    db.refresh(new_experiment)
    
    return new_experiment
