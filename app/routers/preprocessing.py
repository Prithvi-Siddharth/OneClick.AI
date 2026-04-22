from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect, File, UploadFile, Form, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.concurrency import run_in_threadpool
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os, json, pandas as pd, duckdb
from io import BytesIO
from datetime import datetime

from app.db import get_db
from app.models import User, Dataset, TemporaryDataset, PreprocessingLog
from app.security import get_current_user_id
from app.services.s3_operations import get_s3_client, process_and_save_dataset_temporary, duplicate_dataset_in_s3, read_dataset_from_s3
from typing import Optional
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
    
    # fetch the latest loaded dataset for preprocessing and display it in the preprocessing page
    active_dataset = db.query(TemporaryDataset).filter(TemporaryDataset.user_id == int(user_id)).order_by(TemporaryDataset.id.desc()).first()
    
    # Fetch user for navbar profile
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    
    return templates.TemplateResponse("preprocessing.html", {
        "request": request, 
        "username": user.username if user else None,
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

        # Save to TemporaryDataset (Sandbox)
        from app.services.s3_operations import process_and_save_dataset_temporary
        temp_dataset = process_and_save_dataset_temporary(
            db=db,
            user_id=int(user_id),
            file_obj=dataset_file,
            filename=dataset_file.filename,
            bucket_name=bucket_name
        )
        
        # Return success response
        return JSONResponse(
            content={
                "message": "File uploaded for preprocessing successfully",
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
    
    # 1. Find the source dataset in the Catalog (Dataset table)
    source_dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id, 
        Dataset.user_id == int(user_id)
    ).first()

    if not source_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # 2. Duplicate it to the TemporaryDataset table (Sandbox)
    # this also makes it the newest entry in the database (Latest ID)
    from app.services.s3_operations import duplicate_dataset_in_s3
    try:
        new_temp = duplicate_dataset_in_s3(
            db=db,
            user_id=int(user_id),
            bucket_name=source_dataset.s3_bucket,
            source_key=source_dataset.s3_key,
            filename=source_dataset.filename,
            row_count=source_dataset.row_count,
            feature_schema=source_dataset.feature_schema,
            file_size=source_dataset.file_size
        )
        
        return JSONResponse(
            content={
                "message": "Dataset connected to Studio successfully",
                "dataset_id": new_temp.id,
                "row_count": new_temp.row_count,
                "file_size": new_temp.file_size
            },
            status_code=status.HTTP_200_OK
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# this route is used to preview the temporary dataset
@router.get("/preview_dataset/{dataset_id}")
def preview_dataset(dataset_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # First, check the permanent Catalog (Dataset table)
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.user_id == int(user_id)).first()
    
    # If not found, check the temporary Sandbox (TemporaryDataset table)
    if not dataset:
        dataset = db.query(TemporaryDataset).filter(TemporaryDataset.id == dataset_id, TemporaryDataset.user_id == int(user_id)).first()
        
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found in Catalog or Sandbox")
    
    # Read from S3 using existing service function
    try:
        print(f"DEBUG: Previewing dataset {dataset_id} for user {user_id}")
        print(f"DEBUG: Found record: {dataset.filename} (Table: {'Dataset' if hasattr(dataset, 'description') else 'TemporaryDataset'})")
        print(f"DEBUG: S3 Path: s3://{dataset.s3_bucket}/{dataset.s3_key}")
        
        data = read_dataset_from_s3(
            bucket_name=dataset.s3_bucket,
            s3_key=dataset.s3_key,
            filename=dataset.s3_key.split('/')[-1],
            preview_limit=5
        )
        
        if isinstance(data, dict) and "error" in data:
            print(f"DEBUG: read_dataset_from_s3 returned error: {data['error']}")
            raise HTTPException(status_code=500, detail=data["error"])
        
        return JSONResponse(content=data)
    except Exception as e:
        print(f"DEBUG: Exception in preview_dataset: {str(e)}")
        import traceback
        traceback.print_exc()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Server error during preview: {str(e)}")

# this route is used to preprocess the dataset
@router.get("/preprocess-dataset")
def preprocess_dataset(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # fetching the path of dataset from temp table
    active_dataset = db.query(TemporaryDataset).filter(
                TemporaryDataset.user_id == int(user_id)
            ).order_by(TemporaryDataset.id.desc()).first()
    
    if not active_dataset:
        return RedirectResponse(url="/preprocessing?error=no_active_dataset")

    # OPTIMIZATION: Use the stored feature schema if available to avoid expensive S3 read on page load
    dataset_metadata = None
    if active_dataset.feature_schema and active_dataset.feature_schema.strip():
        try:
            import json
            # Ensure it's valid JSON
            schema = json.loads(active_dataset.feature_schema)
            if isinstance(schema, dict) and schema:
                dataset_metadata = {
                    "columns": list(schema.keys()),
                    "dtypes": schema
                }
        except Exception as e:
            # If schema is invalid, we will fall back to S3 read below
            pass

    # Fallback: If no schema is stored, do a light-weight header-only read from S3
    if not dataset_metadata:
        try:
            # We only need headers for the initial UI render (Selection cards)
            s3 = get_s3_client()
            response = s3.get_object(Bucket=active_dataset.s3_bucket, Key=active_dataset.s3_key)
            s3_key = active_dataset.s3_key.lower()
            
            if s3_key.endswith('.csv'):
                line = next(response['Body'].iter_lines()).decode('utf-8')
                import csv
                from io import StringIO
                reader = csv.reader(StringIO(line))
                columns = next(reader)
            elif s3_key.endswith(('.xls', '.xlsx')):
                # For Excel, we still have to read a bit more, but nrows=0 is fast
                import pandas as pd
                from io import BytesIO
                content = response['Body'].read()
                df_headers = pd.read_excel(BytesIO(content), nrows=0)
                columns = df_headers.columns.tolist()
            else:
                # Default to full read if format unknown
                df = read_df_from_s3(active_dataset.s3_bucket, active_dataset.s3_key)
                columns = df.columns.tolist()
            
            dataset_metadata = {
                "columns": columns,
                "dtypes": {col: "unknown" for col in columns}
            }
        except Exception as e:
            print(f"Fallback header read failed: {e}")
            df = read_df_from_s3(active_dataset.s3_bucket, active_dataset.s3_key)
            dataset_metadata = {
                "columns": df.columns.tolist(),
                "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()}
            }
    
    return templates.TemplateResponse("preprocess-dataset.html", {
        "request": request,
        "username": user.username,
        "dataset": dataset_metadata,
        "dataset_id": active_dataset.id
    })

# this route is used to save the preprocessed dataset to the data catalog

#websocket route for preprocessing the dataset
@router.websocket("/preprocess-dataset/ws/{dataset_id}")
@router.websocket("/preprocess-dataset/ws")
async def websocket_preprocess(websocket: WebSocket, dataset_id: Optional[int] = None, db: Session = Depends(get_db)):
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
            PreprocessingLog.temp_dataset_id == temp_id, # Keeping column name for now to avoid migration
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
        await websocket.send_text(json.dumps({"type": "status", "message": f"Authentication failed: {auth_error}. Please log in."}))
        await websocket.close()
        return

    
    while True:
        try:
            data = await websocket.receive_text()
            print(f"DEBUG: WebSocket message received: {data}")
            message = json.loads(data)
            action = message.get("action")
            print(f"DEBUG: Action: {action}, Dataset ID from URL: {dataset_id}")
            
            # Fetch active dataset - prioritize the specific ID if passed via WS URL
            if dataset_id:
                active_dataset = db.query(TemporaryDataset).filter(
                    TemporaryDataset.id == dataset_id,
                    TemporaryDataset.user_id == int(user_id)
                ).first()
            else:
                active_dataset = db.query(TemporaryDataset).filter(
                    TemporaryDataset.user_id == int(user_id)
                ).order_by(TemporaryDataset.id.desc()).first()

            if not active_dataset:
                await send_status("No active dataset found. Please upload one first.")
                continue

            if action == "get_visualization":
                col1 = message.get("col1", "")
                col2 = message.get("col2") or None
                plot_type = message.get("plot_type", "histogram")

                if not col1:
                    await websocket.send_text(json.dumps({"type": "error", "message": "No column specified for visualization."}))
                    continue

                from app.services.visualization_service import calculate_eda_stats, get_plot_data

                df = await run_in_threadpool(read_df_from_s3, active_dataset.s3_bucket, active_dataset.s3_key)
                eda_stats = await run_in_threadpool(calculate_eda_stats, df, col1)
                plot_data = await run_in_threadpool(get_plot_data, df, col1, col2, plot_type)

                await websocket.send_text(json.dumps({
                    "type": "visualization_result",
                    "eda_stats": eda_stats,
                    "plot_data": plot_data,
                }))
                continue

            if action == "run_sql":
                query = message.get("query", "")
                try:
                    # Load dataset
                    df = await run_in_threadpool(read_df_from_s3, active_dataset.s3_bucket, active_dataset.s3_key)
                    
                    # DuckDB can query the pandas DataFrame 'df' directly by name
                    # We'll make 'data' available as an alias for the dataframe
                    data = df 
                    results_df = duckdb.query(query).to_df()
                    
                    # Convert to list of dicts (handling NaN for JSON)
                    # We use .replace({pd.NA: None}) or similar for better JSON compatibility
                    results = results_df.astype(object).where(pd.notnull(results_df), None).to_dict(orient="records")
                    
                    await websocket.send_text(json.dumps({
                        "type": "query_results",
                        "data": results
                    }))
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"SQL Error: {str(e)}"
                    }))
                continue

            if action == "get_preview":
                await send_status("Fetching initial preview...")
                # Offload blocking S3 read to a threadpool
                df = await run_in_threadpool(read_df_from_s3, active_dataset.s3_bucket, active_dataset.s3_key)
                await send_preview(df)
                await send_history(active_dataset.id)
                await send_status("Preview loaded.")
                
            elif action == "apply_preprocessing":
                await send_progress(5, "Backend received request...")
                ops = message.get("operations", {})
                attributes = message.get("attributes", [])
                target_column = message.get("target_column", None)
                await send_progress(10, f"Loading dataset for {len(attributes)} attributes...")
                    
                # Offload blocking S3 read to a threadpool
                df = await run_in_threadpool(read_df_from_s3, active_dataset.s3_bucket, active_dataset.s3_key)

                # Offload blocking preprocessing application to a threadpool
                await send_progress(30, "Applying transformations...")
                processed_df = await run_in_threadpool(apply_preprocessing, df, ops, attributes, target_column)

                if isinstance(processed_df, dict) and "error" in processed_df:
                    await websocket.send_text(json.dumps({"type": "error", "message": processed_df['error']}))
                    continue

                # Offload blocking to_csv to a threadpool
                await send_progress(60, "Generating processed file...")
                csv_buffer = BytesIO()
                await run_in_threadpool(processed_df.to_csv, csv_buffer, index=False)
                csv_buffer.seek(0)
                    
                await send_progress(80, "Uploading changes to S3...")
                s3 = get_s3_client()
                file_content = csv_buffer.getvalue()
                # Consider offloading s3.put_object if it's slow/blocking
                await run_in_threadpool(s3.put_object, Bucket=active_dataset.s3_bucket, Key=active_dataset.s3_key, Body=file_content)
                    
                # Update DB record with new schema and stats
                new_schema = {col: str(dtype) for col, dtype in processed_df.dtypes.items()}
                active_dataset.feature_schema = json.dumps(new_schema)
                active_dataset.row_count = len(processed_df)
                active_dataset.file_size = len(file_content)
                db.commit()
                db.refresh(active_dataset)
                        
                # 5. Send updated preview
                await send_progress(95, "Refreshing data preview...")
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
                    
                await send_progress(100, "Preprocessing complete!")
                
        except WebSocketDisconnect:
            print(f"WebSocket disconnected for user {user_id}")
            break
        except HTTPException as e:
            try:
                await websocket.send_text(json.dumps({"type": "error", "message": e.detail}))
            except:
                break
        except Exception as e:
            print(f"WebSocket execution error: {str(e)}")
            try:
                await websocket.send_text(json.dumps({"type": "error", "message": f"Critical Error: {str(e)}"}))
            except:
                break

@router.get("/download_preprocessed_dataset/{dataset_id}")
def download_preprocessed_dataset(dataset_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id, 
        Dataset.user_id == int(user_id)
    ).first()

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    from app.services.s3_operations import create_presigned_download_url
    url = create_presigned_download_url(
        bucket_name=dataset.s3_bucket,
        s3_key=dataset.s3_key,
        filename=f"preprocessed_{dataset_id}.csv"
    )
    
    if not url:
        raise HTTPException(status_code=500, detail="Failed to generate download URL")
        
    return JSONResponse(content={"download_url": url})


@router.post("/save_preprocessed_dataset")
async def save_preprocessed_dataset(request: Request, db: Session = Depends(get_db)):
    # 1. Authentication Check
    user_id = get_current_user_id(request)
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})
    
    # 2. Get the custom name from the request body
    try:
        data = await request.json()
    except:
        return JSONResponse(status_code=400, content={"error": "Invalid request body"})
        
    custom_name = data.get("custom_name", "Processed_Dataset")

    # Ensure it has a .csv extension
    if not custom_name.lower().endswith('.csv'):
        custom_name += ".csv"

    # 3. Fetch the latest temporary dataset for this user
    temp_dataset = db.query(TemporaryDataset).filter(
        TemporaryDataset.user_id == int(user_id)
    ).order_by(TemporaryDataset.id.desc()).first()

    if not temp_dataset:
        return JSONResponse(status_code=404, content={"error": "No preprocessed data found to save"})

    try:
        bucket_name = temp_dataset.s3_bucket
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        
        # Create a unique path in S3 using your custom name
        permanent_key = f"{user_id}/datasets/{timestamp}_{custom_name}"
        
        # 4. Perform the Server-side copy in S3
        s3 = get_s3_client()
        s3.copy_object(
            Bucket=bucket_name,
            CopySource={'Bucket': bucket_name, 'Key': temp_dataset.s3_key},
            Key=permanent_key
        )

        # 5. Create the permanent record in the Dataset table
        new_dataset = Dataset(
            user_id=int(user_id),
            filename=custom_name, # Your chosen name
            s3_key=permanent_key,
            s3_bucket=bucket_name,
            file_size=temp_dataset.file_size,
            row_count=temp_dataset.row_count,
            description="Preprocessed via Studio",
            feature_schema=temp_dataset.feature_schema
        )

        db.add(new_dataset)
        db.commit()
        db.refresh(new_dataset)
        
        return JSONResponse(content={
            "message": f"Successfully saved '{custom_name}' to your Data Catalog!",
            "dataset_id": new_dataset.id
        })
        
    except Exception as e:
        print(f"Error saving dataset: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Failed to save dataset: " + str(e)})
