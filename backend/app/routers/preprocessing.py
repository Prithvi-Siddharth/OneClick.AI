from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect, File, UploadFile, Form, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os, json, pandas as pd
from io import BytesIO
from datetime import datetime

from app.db import get_db
from app.models import User, Dataset, TemporaryDataset, PreprocessingLog
from app.security import get_current_user_id
from app.services.s3_operations import get_s3_client, process_and_save_dataset_temporary, duplicate_dataset_in_s3, read_dataset_from_s3
from app.services.data_preprocessing import apply_preprocessing

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))


def read_df_from_s3(s3_bucket: str, s3_key: str) -> pd.DataFrame:
    """
    Reads a dataset from S3 into a pandas DataFrame.
    Automatically detects file format from the S3 key extension.
    Supports: csv, json, xls, xlsx
    """
    s3 = get_s3_client()
    response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
    content = response['Body'].read()
    file_buffer = BytesIO(content)

    ext = s3_key.lower().rsplit('.', 1)[-1] if '.' in s3_key.split('/')[-1] else ''

    # If no extension found, sniff file content for Excel (ZIP/PK magic bytes)
    if ext not in ('csv', 'json', 'xls', 'xlsx'):
        if content[:4] == b'PK\x03\x04':  # ZIP magic bytes (xlsx is a ZIP)
            ext = 'xlsx'
        else:
            ext = 'csv'  # Default fallback

    if ext == 'csv':
        return pd.read_csv(file_buffer)
    elif ext == 'json':
        try:
            return pd.read_json(file_buffer, lines=True)
        except ValueError:
            file_buffer.seek(0)
            return pd.read_json(file_buffer)
    elif ext in ('xls', 'xlsx'):
        return pd.read_excel(file_buffer)
    else:
        return pd.read_csv(file_buffer)


#preprocessing page
@router.get("/preprocessing")
def preprocessing_page(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login")
    
    #fetch the users uploaded datasats in catalog, so that the user can select the dataset to preprocess
    datasets = db.query(Dataset).filter(Dataset.user_id == int(user_id)).all()
    
    #fetch the latest loaded dataset for preprocessing and display it in the preprocessing page
    active_dataset = db.query(TemporaryDataset).filter(TemporaryDataset.user_id == int(user_id)).order_by(TemporaryDataset.id.desc()).first()
    
    return templates.TemplateResponse("preprocessing.html", {
        "request": request, 
        "datasets": datasets,
        "active_dataset": active_dataset
    })

#temporary upload dataset into s3, when user is preprocessing
@router.post("/temporary_upload_dataset")
def temporary_upload_dataset(
    request: Request,
    db: Session = Depends(get_db),
    dataset_file: UploadFile = File(...),
):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user")
    
    try:
        bucket_name = os.getenv("S3_BUCKET_NAME")
        
        if not bucket_name:
            raise ValueError("S3_BUCKET_NAME not configured in environment variables")

        # Call the function
        result = process_and_save_dataset_temporary(
            db=db,
            user_id=int(user_id),
            file_obj=dataset_file,
            bucket_name=bucket_name
        )

        # Handle both dict and Dataset object responses
        if isinstance(result, dict):
            #returns dict with success/data/message
            if not result["success"]:
                return JSONResponse(
                    content={"error": result["message"]},
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            dataset = result["data"]
        else:
            #returns dataset object directly
            dataset = result
        
        # Return success response
        return JSONResponse(
            content={
                "message": "File uploaded successfully",
                "dataset_id": dataset.id,
                "row_count": dataset.row_count,
                "file_size": dataset.file_size
            },
            status_code=status.HTTP_200_OK
        )
        
    except HTTPException as e:
        return JSONResponse(
            content={"error": e.detail},
            status_code=e.status_code
        )
    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# connect dataset from data catalog for preprocessing
@router.post('/connect_dataset')
def connect_dataset(
    request: Request,
    db: Session = Depends(get_db),
    dataset_id: int = Form(...),
):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    # 1. Find the dataset in the Catalog (Dataset table)
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id, 
        Dataset.user_id == int(user_id)
    ).first()

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        bucket_name = os.getenv("S3_BUCKET_NAME")
        
        if not bucket_name:
            raise ValueError("S3_BUCKET_NAME not configured in environment variables")

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        source_ext = os.path.splitext(dataset.s3_key)[1]  # e.g. '.xlsx'

        # Call the function with required metadata from the catalog record
        temp_dataset = duplicate_dataset_in_s3(
            db=db,
            user_id=int(user_id),
            bucket_name=bucket_name,
            source_key=dataset.s3_key,
            destination_key=f"{dataset.user_id}/temporary_datasets/{timestamp}{source_ext}",
            row_count=dataset.row_count,
            feature_schema=dataset.feature_schema,
            file_size=dataset.file_size
        )
        
        # Return success response
        return JSONResponse(
            content={
                "message": "Dataset connected successfully",
                "dataset_id": temp_dataset.id,
                "row_count": temp_dataset.row_count,
                "file_size": temp_dataset.file_size
            },
            status_code=status.HTTP_200_OK
        )
        
    except HTTPException as e:
        return JSONResponse(
            content={"error": e.detail},
            status_code=e.status_code
        )
    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# this route is used to preview the temporary dataset
@router.get("/preview_temporary_dataset/{temp_id}")
def preview_temporary_dataset(temp_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    temp_dataset = db.query(TemporaryDataset).filter(TemporaryDataset.id == temp_id, TemporaryDataset.user_id == int(user_id)).first()
    if not temp_dataset:
        raise HTTPException(status_code=404, detail="Temporary dataset not found")
    
    # Read from S3 using existing service function
    data = read_dataset_from_s3(
        bucket_name=temp_dataset.s3_bucket,
        s3_key=temp_dataset.s3_key,
        filename=temp_dataset.s3_key.split('/')[-1],  # Use actual filename from S3 key
        preview_limit=5
    )
    
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    
    return JSONResponse(content=data)

# this route is used to preprocess the dataset
@router.get("/preprocess-dataset")
def preprocess_dataset(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    #fetching the path of dataset from db
    active_dataset = db.query(TemporaryDataset).filter(
                TemporaryDataset.user_id == int(user_id)
            ).order_by(TemporaryDataset.id.desc()).first()
    
    #fetching the dataset from s3 bucket.
    df = read_df_from_s3(active_dataset.s3_bucket, active_dataset.s3_key)
    
    return templates.TemplateResponse("preprocess-dataset.html", {
        "request": request,
        "username": user.username,
        "dataset": df,
        "dataset_id": active_dataset.id
    })

# this route is used to save the preprocessed dataset to the data catalog
@router.post("/save_preprocessed_dataset")
def save_preprocessed_dataset(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # 1. Fetch latest active temporary dataset for this user
    temp_dataset = db.query(TemporaryDataset).filter(
        TemporaryDataset.user_id == int(user_id)
    ).order_by(TemporaryDataset.id.desc()).first()

    if not temp_dataset:
        raise HTTPException(status_code=404, detail="No active preprocessed dataset found")
    
    try:
        bucket_name = os.getenv("S3_BUCKET_NAME")
        if not bucket_name:
            raise ValueError("S3_BUCKET_NAME not configured in environment variables")

        # 2. Promote to Dataset Catalog
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        permanent_key = f"{user_id}/datasets/{timestamp}_processed.csv"
        
        # 3. Server-side copy in S3
        s3 = get_s3_client()
        s3.copy_object(
            Bucket=bucket_name,
            CopySource={'Bucket': bucket_name, 'Key': temp_dataset.s3_key},
            Key=permanent_key
        )

        # 4. Create record in the main Dataset table
        dataset = Dataset(
            user_id=int(user_id),
            filename=f"Processed_{timestamp}.csv",
            s3_key=permanent_key,
            s3_bucket=bucket_name,
            file_size=temp_dataset.file_size,
            row_count=temp_dataset.row_count,
            description="Preprocessed via Studio",
            feature_schema=temp_dataset.feature_schema
        )

        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        
        return JSONResponse(content={"message": "Dataset saved to catalog successfully!"})
        
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

#websocket route for preprocessing the dataset
@router.websocket("/preprocess-dataset/ws")
async def websocket_preprocess(websocket: WebSocket, db: Session = Depends(get_db)):
    #accept the websocket connection
    await websocket.accept()
    
    async def send_status(msg):
        await websocket.send_text(json.dumps({"type": "status", "message": msg}))

    async def send_progress(percent, msg):
        await websocket.send_text(json.dumps({"type": "progress", "percentage": percent, "message": msg}))

    async def send_preview(df):
        # head(5) and convert to records
        preview = df.head(5).where(pd.notnull(df), None).to_dict(orient="records")
        # Extract column names and dtypes
        columns = [{"name": str(col), "dtype": str(dtype)} for col, dtype in df.dtypes.items()]
        await websocket.send_text(json.dumps({
            "type": "preview", 
            "data_preview": preview,
            "columns": columns
        }))

    async def send_history(temp_id):
        logs = db.query(PreprocessingLog).filter(
            PreprocessingLog.temp_dataset_id == temp_id,
            PreprocessingLog.user_id == int(user_id)
        ).order_by(PreprocessingLog.timestamp.asc()).all()
        
        history = [
            {
                "operation_type": log.operation_type,
                "operation_name": log.operation_name,
                "attributes": json.loads(log.attributes) if log.attributes else [],
                "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            }
            for log in logs
        ]
        await websocket.send_text(json.dumps({"type": "history", "data": history}))

    # helper to get user id from websocket
    token = websocket.cookies.get("access_token")
    user_id = None
    auth_error = "Token missing"
    if token:
        try:
            from app.security import JWT_SECRET_KEY, JWT_ALGORITHM
            from jose import jwt, JWTError
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("sub")
            if not user_id:
                auth_error = "User ID missing in token"
        except Exception as e:
            auth_error = f"Token validation failed: {str(e)}"

    if not user_id:
        await websocket.send_text(json.dumps({"type": "status", "message": f"❌ Authentication failed: {auth_error}. Please log in."}))
        await websocket.close()
        return

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            action = message.get("action")
            
            # Fetch latest active dataset for this user
            active_dataset = db.query(TemporaryDataset).filter(
                TemporaryDataset.user_id == int(user_id)
            ).order_by(TemporaryDataset.id.desc()).first()

            if not active_dataset:
                await send_status("❌ No active dataset found. Please upload one first.")
                continue

            if action == "get_preview":
                await send_status("📋 Fetching initial preview...")
                df = read_df_from_s3(active_dataset.s3_bucket, active_dataset.s3_key)
                await send_preview(df)
                await send_history(active_dataset.id)
                await send_status("✅ Preview loaded.")
            
            elif action == "apply_preprocessing":
                await send_progress(5, "📡 Backend received request...")
                ops = message.get("operations", {})
                attributes = message.get("attributes", [])
                await send_progress(10, f"� Loading dataset for {len(attributes)} attributes...")
                
                # 2. Load from S3
                df = read_df_from_s3(active_dataset.s3_bucket, active_dataset.s3_key)

                # 3. Apply preprocessing
                await send_progress(30, "⚙️ Applying transformations...")
                processed_df = apply_preprocessing(df, ops, attributes)

                if isinstance(processed_df, dict) and "error" in processed_df:
                    await send_progress(0, f"❌ Error: {processed_df['error']}")
                    continue

                # 4. Save result back to S3
                await send_progress(60, "💾 Generating processed file...")
                csv_buffer = BytesIO()
                processed_df.to_csv(csv_buffer, index=False)
                csv_buffer.seek(0)
                
                await send_progress(80, "☁️ Uploading changes to S3...")
                s3 = get_s3_client()
                file_content = csv_buffer.getvalue()
                s3.put_object(Bucket=active_dataset.s3_bucket, Key=active_dataset.s3_key, Body=file_content)
                
                # Update DB record with new schema and stats
                new_schema = {col: str(dtype) for col, dtype in processed_df.dtypes.items()}
                active_dataset.feature_schema = json.dumps(new_schema)
                active_dataset.row_count = len(processed_df)
                active_dataset.file_size = len(file_content)
                db.commit()
                db.refresh(active_dataset)
                
                # 5. Send updated preview
                await send_progress(95, "📋 Refreshing data preview...")
                await send_preview(processed_df)

                # 6. Log operations and send log update
                new_logs = []
                for step_type, op_list in ops.items():
                    for op_name in op_list:
                        log_entry = PreprocessingLog(
                            temp_dataset_id=active_dataset.id,
                            user_id=int(user_id),
                            operation_type=step_type,
                            operation_name=op_name,
                            attributes=json.dumps(attributes)
                        )
                        db.add(log_entry)
                        new_logs.append({
                            "operation_type": step_type,
                            "operation_name": op_name,
                            "attributes": attributes,
                            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                        })
                db.commit()
                await websocket.send_text(json.dumps({"type": "log_update", "data": new_logs}))
                
                await send_progress(100, "🚀 Preprocessing complete!")
                
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for user {user_id}")
    except HTTPException as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": e.detail}))
        except:
            pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "status", "message": f"❌ Critical Error: {str(e)}"}))
        except:
            pass

@router.get("/download_preprocessed_dataset/{dataset_id}")
def download_preprocessed_dataset(dataset_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    temp_dataset = db.query(TemporaryDataset).filter(
        TemporaryDataset.id == dataset_id, 
        TemporaryDataset.user_id == int(user_id)
    ).first()

    if not temp_dataset:
        raise HTTPException(status_code=404, detail="Temporary dataset not found")
    
    from app.services.s3_operations import create_presigned_download_url
    url = create_presigned_download_url(
        bucket_name=temp_dataset.s3_bucket,
        s3_key=temp_dataset.s3_key,
        filename=f"preprocessed_{dataset_id}.csv"
    )
    
    if not url:
        raise HTTPException(status_code=500, detail="Failed to generate download URL")
        
    return JSONResponse(content={"download_url": url})