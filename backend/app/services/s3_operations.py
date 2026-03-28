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
from app.models import Dataset, Experiment, TemporaryDataset
from app.services.data_preprocessing import get_dataset_preview_and_stats
from io import BytesIO
import json


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
    query = db.query(Experiment).filter(Experiment.user_id == user_id).order_by(Experiment.id.desc())
    
    if limit:
        query = query.limit(limit)
        
    models = query.all()
    return models

def get_s3_client():
    """
    Initialize and return a boto3 S3 client.
    """
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("AWS_REGION", "us-east-1")

    if not access_key or not secret_key:
        print("Error: AWS credentials not found in environment variables.")
        print(f"AWS_ACCESS_KEY_ID set: {bool(access_key)}")
        print(f"AWS_SECRET_ACCESS_KEY set: {bool(secret_key)}")
        # Check if we should fall back to default profile or IAM roles
        # If so, we call boto3.client('s3', region_name=region) without keys
        # But for this app, explicit keys via .env seem expected.
    
    # Pass None if not set to let boto3 attempt other methods (like ~/.aws/credentials)
    # But explicitly warn if both methods fail (handled by NoCredentialsError later)
    return boto3.client(
        's3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region
    )

def read_dataset_from_s3(bucket_name: str, s3_key: str, filename: str, preview_limit: int = 5):
    s3 = get_s3_client()
    try:
        # 1. Fetch from S3
        response = s3.get_object(Bucket=bucket_name, Key=s3_key)
        file_stream = response['Body']
        
        from io import BytesIO
        content = file_stream.read()
        file_buffer = BytesIO(content)
        
        ext = filename.lower().split('.')[-1]
        
        # 2. Delegate to the Preprocessing Service
        return get_dataset_preview_and_stats(file_buffer, ext, preview_limit)
            
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
        description=description,
        feature_schema=json.dumps(schema_dict) 
    )

    db.add(new_dataset)
    db.commit()
    db.refresh(new_dataset)
    
    return new_dataset

def process_and_save_dataset_temporary(
    db: Session,
    user_id: int,
    file_obj,
    bucket_name: str
) -> TemporaryDataset:
    """
    Orchestrator function to:
    1. Generate a unique S3 key.
    2. Extract metadata.
    3. Upload file to S3.
    4. Save record to TiDB.
    """
    
    # 1. Generate Unique Key
    # Organization: {user_id}/datasets/{timestamp}
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    s3_key = f"{user_id}/temporary_datasets/{timestamp}"
    
    # 2. Calculate Metadata & Size (BEFORE upload to avoid closed file issues)
    # Use the underlying file object if this is a FastAPI UploadFile
    actual_file = getattr(file_obj, "file", file_obj)

    # Get Size
    actual_file.seek(0, os.SEEK_END)
    file_size = actual_file.tell()
    actual_file.seek(0)
    
    # Get Schema and Rows
    row_count, schema_dict = inspect_temporary_dataset_metadata(file_obj)

    # Reset stream for upload
    actual_file.seek(0)
    
    # 3. Upload to S3
    success = upload_file_to_s3(file_obj, bucket_name, s3_key)
    if not success:
        raise Exception("Failed to upload file to S3")
    
    # 4. Save to DB
    new_dataset = TemporaryDataset(
        user_id=user_id,
        s3_key=s3_key,
        s3_bucket=bucket_name,
        file_size=file_size,
        row_count=row_count,
        feature_schema=json.dumps(schema_dict) 
    )

    db.add(new_dataset)
    db.commit()
    db.refresh(new_dataset)
    
    return new_dataset


def duplicate_dataset_in_s3(
    db: Session,
    user_id: int,
    bucket_name: str,
    source_key: str,
    destination_key: str,
    row_count: int,
    feature_schema: str,
    file_size: int
) -> TemporaryDataset:
    # 1. Trigger the S3 Copy (Server-to-Server)
    s3_client = get_s3_client()
    copy_source = {'Bucket': bucket_name, 'Key': source_key}
    s3_client.copy_object(Bucket=bucket_name, CopySource=copy_source, Key=destination_key)

    # 2. Create the TemporaryDataset record using existing metadata
    new_dataset = TemporaryDataset(
        user_id=user_id,
        s3_key=destination_key,
        s3_bucket=bucket_name,
        file_size=file_size,
        row_count=row_count,
        feature_schema=feature_schema
    )
    db.add(new_dataset)
    db.commit()
    db.refresh(new_dataset)
    return new_dataset

def inspect_temporary_dataset_metadata(file_obj):
    """
    Reads the file to extract metadata (rows, schema).
    Supports CSV, JSON, and Excel.
    """

    try:
        # Use the underlying file object if this is a FastAPI UploadFile
        print(f"DEBUG: file_obj type: {type(file_obj)}")
        print(f"DEBUG: file_obj dir: {dir(file_obj)}")
        actual_file = getattr(file_obj, "file", file_obj)
        # Use a placeholder since we don't rely on the original name
        upload_name = getattr(file_obj, "filename", "temp_dataset.csv") 
        ext = upload_name.lower().split('.')[-1]
        
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
        print(f"Error inspecting temporary dataset: {e}")
        return 0, {}


def upload_model_to_s3(
    db: Session,
    file_obj, 
    bucket_name: str, 
    user_id: int, 
    model_name: str,
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
        user_id=user_id,
        name=model_name,
        algorithm=algorithm,
        model_artifact_path=s3_key,
        status="COMPLETED"
    )
    db.add(new_experiment)
    db.commit()
    db.refresh(new_experiment)
    
    return new_experiment


def s3_delete_object(bucket_name: str, s3_key: str) -> bool:
    """
    Deletes an object from S3.
    """
    s3 = get_s3_client()
    try:
        s3.delete_object(Bucket=bucket_name, Key=s3_key)
        return True
    except NoCredentialsError:
        print("Credentials not available")
        return False
    except Exception as e:
        print(f"Failed to delete object from S3: {e}")
        return False

# Generate a presigned URL to share an S3 object
def create_presigned_download_url(bucket_name: str, s3_key: str, filename: str, expiration=3600):
    """
    Generate a presigned URL to share an S3 object
    """
    s3 = get_s3_client()
    try:
        response = s3.generate_presigned_url('get_object',
                                             Params={'Bucket': bucket_name,
                                                     'Key': s3_key,
                                                     'ResponseContentDisposition': f'attachment; filename="{filename}"'},
                                             ExpiresIn=expiration)
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return None

    return response


def load_dataset_as_dataframe(bucket_name: str, s3_key: str):
    """
    Helper to fetch a file from S3 and return a Pandas DataFrame.
    """
    s3 = get_s3_client()
    response = s3.get_object(Bucket=bucket_name, Key=s3_key)
    content = response['Body'].read()
    
    # Identify file type by extension
    ext = s3_key.split('.')[-1].lower()
    
    if ext == 'csv':
        return pd.read_csv(BytesIO(content))
    elif ext == 'json':
        # Handles most JSON formats in this app
        return pd.read_json(BytesIO(content))
    elif ext in ['xls', 'xlsx']:
        return pd.read_excel(BytesIO(content))
    
    return pd.read_csv(BytesIO(content))