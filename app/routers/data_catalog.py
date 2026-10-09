from fastapi import APIRouter, Depends, HTTPException, Request, Form, File, UploadFile, status
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
from datetime import datetime

from app.db import get_db
from app.models import User, Dataset, TemporaryDataset, Folder, Experiment
from app.security import get_current_user_id
from sqlalchemy import or_
from typing import Optional
from app.services.s3_operations import (
    process_and_save_dataset, get_user_datasets, read_dataset_from_s3,
    s3_delete_object, create_presigned_download_url,
    process_and_save_dataset_temporary, duplicate_dataset_in_s3,
    load_dataset_as_dataframe, get_s3_client
)
from app.services.visualization_service import calculate_eda_stats, get_plot_data
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
import json, pandas as pd
try:
    import duckdb
except ImportError:
    duckdb = None

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))

# upload dataset to data catalog
@router.post("/upload_dataset")
def upload_dataset(
    request: Request,
    db: Session = Depends(get_db),
    datasetFilename: str = Form(...),
    datasetDescription: Optional[str] = Form(None),
    dataset_file: UploadFile = File(...),
    folder_id: Optional[str] = Form(None)
):
    # Handle empty string from frontend
    try:
        folder_id = int(folder_id) if folder_id and str(folder_id).strip() else None
    except (ValueError, TypeError):
        folder_id = None

    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    if not datasetDescription or not datasetDescription.strip():
        return JSONResponse(
            content={"error": "A description is required for the dataset."},
            status_code=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        bucket_name = os.getenv("S3_BUCKET_NAME")
        
        if not bucket_name:
            raise ValueError("S3_BUCKET_NAME not configured in environment variables")

        # Ensure the filename has the correct extension from the uploaded file
        original_filename = dataset_file.filename
        if original_filename:
            ext = os.path.splitext(original_filename)[1]
            if ext and not datasetFilename.endswith(ext):
                datasetFilename += ext
        
        # Call the function
        result = process_and_save_dataset(
            db=db,
            user_id=int(user_id),
            filename=datasetFilename,
            file_obj=dataset_file,
            bucket_name=bucket_name,
            description=datasetDescription,
            folder_id=folder_id
        )

        # Handle both dict and Dataset object responses
        if isinstance(result, dict):
            # New format: returns dict with success/data/message
            if not result["success"]:
                return JSONResponse(
                    content={"error": result["message"]},
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            dataset = result["data"]
        else:
            # Old format: returns Dataset object directly
            dataset = result
        
        # Return success response
        return JSONResponse(
            content={
                "message": "File uploaded successfully",
                "dataset_id": dataset.id,
                "filename": dataset.filename,
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

# Create a new folder
@router.post("/create_folder")
def create_folder(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    parent_id: Optional[str] = Form(None),
    folder_type: str = Form(...) # "dataset" or "model"
):
    # Handle empty string from frontend
    try:
        parent_id = int(parent_id) if parent_id and str(parent_id).strip() else None
    except (ValueError, TypeError):
        parent_id = None

    user_id = get_current_user_id(request)
    if not user_id:
        return JSONResponse(content={"error": "Not authenticated"}, status_code=401)
    
    new_folder = Folder(
        name=name,
        parent_id=parent_id if parent_id else None,
        user_id=int(user_id),
        folder_type=folder_type
    )
    db.add(new_folder)
    db.commit()
    db.refresh(new_folder)
    return JSONResponse(content={"message": "Folder created successfully", "id": new_folder.id})

@router.delete("/api/delete_folder/{folder_id}")
def delete_folder(folder_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Ownership Check
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == int(user_id)).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    # Empty-Check: 1. Subfolders
    subfolders_count = db.query(Folder).filter(Folder.parent_id == folder_id).count()
    if subfolders_count > 0:
        return JSONResponse(status_code=400, content={"error": "Folder is not empty (contains subfolders)"})
    
    # Empty-Check: 2. Catalog Items (based on folder type)
    if folder.folder_type == "dataset":
        item_count = db.query(Dataset).filter(Dataset.folder_id == folder_id).count()
    else:
        # Assuming folder_type == "model"
        item_count = db.query(Experiment).filter(Experiment.folder_id == folder_id).count()
        
    if item_count > 0:
        return JSONResponse(status_code=400, content={"error": f"Folder is not empty (contains {folder.folder_type}s)"})
    
    # All checks passed
    db.delete(folder)
    db.commit()
    return {"message": "Folder deleted successfully"}

# Move dataset to a folder
@router.post("/move_dataset/{dataset_id}")
def move_dataset(
    dataset_id: int,
    request: Request,
    folder_id: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    # Handle empty string from frontend
    try:
        folder_id = int(folder_id) if folder_id and str(folder_id).strip() else None
    except (ValueError, TypeError):
        folder_id = None

    user_id = get_current_user_id(request)
    if not user_id:
        return JSONResponse(content={"error": "Not authenticated"}, status_code=401)
    
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.user_id == int(user_id)).first()
    if not dataset:
        return JSONResponse(content={"error": "Dataset not found"}, status_code=404)
    
    dataset.folder_id = folder_id if folder_id else None
    db.commit()
    return JSONResponse(content={"message": "Dataset moved successfully"})

# rendering of the view_datasets.html to view all datasets in the data catalog
@router.get("/view_datasets")
def view_dataset(
    request: Request, 
    db: Session = Depends(get_db), 
    folder_id: Optional[str] = None,
    search: Optional[str] = None,
    date: Optional[str] = None,
    response_class=HTMLResponse
):
    # Handle empty string from frontend
    try:
        folder_id = int(folder_id) if folder_id and str(folder_id).strip() else None
    except (ValueError, TypeError):
        folder_id = None

    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    # Base query for datasets
    dataset_query = db.query(Dataset).filter(Dataset.user_id == int(user_id))
    
    # Advanced Filtering (Search/Date)
    is_search = False
    if search or date:
        is_search = True
        filters = []
        if search:
            filters.append(Dataset.filename.ilike(f"%{search}%"))
        
        if date:
            try:
                search_date = datetime.strptime(date, '%Y-%m-%d').date()
                filters.append(db.func.date(Dataset.upload_date) == search_date)
            except ValueError:
                pass
        
        if len(filters) > 1:
            dataset_query = dataset_query.filter(or_(*filters))
        elif len(filters) == 1:
            dataset_query = dataset_query.filter(filters[0])
    else:
        # Filter by folder
        dataset_query = dataset_query.filter(Dataset.folder_id == folder_id)

    datasets = dataset_query.order_by(Dataset.upload_date.desc()).all()
    
    # Fetch subfolders (only if not searching globally)
    folders = []
    if not is_search:
        folders = db.query(Folder).filter(
            Folder.user_id == int(user_id),
            Folder.folder_type == "dataset",
            Folder.parent_id == folder_id
        ).all()

    # Breadcrumbs logic
    breadcrumbs = []
    if folder_id:
        curr = db.query(Folder).filter(Folder.id == folder_id).first()
        while curr:
            breadcrumbs.insert(0, {"id": curr.id, "name": curr.name})
            if curr.parent_id:
                curr = db.query(Folder).filter(Folder.id == curr.parent_id).first()
            else:
                curr = None
    
    return templates.TemplateResponse("view_datasets.html", {
        "request": request, 
        "username": user.username, 
        "datasets": datasets,
        "folders": folders,
        "current_folder_id": folder_id,
        "breadcrumbs": breadcrumbs,
        "search_query": search,
        "search_date": date,
        "is_search": is_search
    })

# API for fetching catalog contents as JSON (used in Preprocessing etc)
@router.get("/api/catalog/contents")
def get_catalog_contents(
    request: Request,
    db: Session = Depends(get_db),
    folder_id: Optional[str] = None
):
    # Handle empty string from frontend
    try:
        folder_id = int(folder_id) if folder_id and str(folder_id).strip() else None
    except (ValueError, TypeError):
        folder_id = None

    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Folders
    folders = db.query(Folder).filter(
        Folder.user_id == int(user_id),
        Folder.folder_type == "dataset",
        Folder.parent_id == folder_id
    ).all()
    
    # Datasets
    datasets = db.query(Dataset).filter(
        Dataset.user_id == int(user_id),
        Dataset.folder_id == folder_id
    ).order_by(Dataset.upload_date.desc()).all()
    
    # Breadcrumbs
    breadcrumbs = []
    if folder_id:
        curr = db.query(Folder).filter(Folder.id == folder_id).first()
        while curr:
            breadcrumbs.insert(0, {"id": curr.id, "name": curr.name})
            if curr.parent_id:
                curr = db.query(Folder).filter(Folder.id == curr.parent_id).first()
            else:
                curr = None
                
    return {
        "folders": [{"id": f.id, "name": f.name} for f in folders],
        "datasets": [{"id": d.id, "filename": d.filename, "upload_date": d.upload_date.strftime('%Y-%m-%d')} for d in datasets],
        "breadcrumbs": breadcrumbs
    }

#this route is used to preview the dataset
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
        data = read_dataset_from_s3(
            bucket_name=dataset.s3_bucket,
            s3_key=dataset.s3_key,
            filename=dataset.s3_key.split('/')[-1], # Use actual filename from S3 key
            preview_limit=5
        )
        
        if isinstance(data, dict) and "error" in data:
            raise HTTPException(status_code=500, detail=data["error"])
        
        return JSONResponse(content=data)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Server error during preview: {str(e)}")

# this route is used to delete the dataset
@router.delete("/delete_dataset/{dataset_id}")
def delete_dataset(dataset_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.user_id == int(user_id)).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
        
    try:
        # 1. Attempt to delete from S3 first
        s3_key = dataset.s3_key
        s3_bucket = dataset.s3_bucket
        if s3_key and s3_bucket:
            s3_delete_object(s3_bucket, s3_key)
        
        # 2. Only if S3 is confirmed clean, delete from database
        db.delete(dataset)
        db.commit()
        
        return JSONResponse(content={"message": "Dataset deleted successfully from S3 and database"})
    except Exception as e:
        db.rollback()
        print(f"ERROR: Deletion failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete dataset: {str(e)}")

# this route is used to download the dataset
@router.get("/download_dataset/{dataset_id}")
def download_dataset(dataset_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.user_id == int(user_id)).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
        
    url = create_presigned_download_url(
        bucket_name=dataset.s3_bucket,
        s3_key=dataset.s3_key,
        filename=dataset.filename
    )
    
    if not url:
        raise HTTPException(status_code=500, detail="Failed to generate download URL")
        
    return JSONResponse(content={"download_url": url})


# WebSocket route for Query and Visualization tools in Data Catalog
@router.websocket("/data-catalog/ws/{dataset_id}")
async def websocket_data_catalog(websocket: WebSocket, dataset_id: int, db: Session = Depends(get_db)):
    await websocket.accept()

    # Authentication
    token = websocket.cookies.get("access_token")
    user_id = None
    if token:
        try:
            from app.security import JWT_SECRET_KEY, JWT_ALGORITHM
            from jose import jwt
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("sub")
        except Exception:
            pass

    if not user_id:
        await websocket.send_text(json.dumps({"type": "error", "message": "Authentication failed. Please log in."}))
        await websocket.close()
        return

    # Fetch dataset metadata to verify ownership
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.user_id == int(user_id)).first()
    if not dataset:
        await websocket.send_text(json.dumps({"type": "error", "message": "Dataset not found or access denied."}))
        await websocket.close()
        return

    while True:
        try:
            data = await websocket.receive_text()
            message = json.loads(data)
            action = message.get("action")

            if action == "run_sql":
                query = message.get("query", "")
                try:
                    df = await run_in_threadpool(load_dataset_as_dataframe, dataset.s3_bucket, dataset.s3_key)
                    # Use 'data' as alias for the dataframe in SQL
                    data = df
                    results_df = duckdb.query(query).to_df()
                    results = results_df.astype(object).where(pd.notnull(results_df), None).to_dict(orient="records")
                    await websocket.send_text(json.dumps({"type": "query_results", "data": results}))
                except Exception as e:
                    await websocket.send_text(json.dumps({"type": "error", "message": f"SQL Error: {str(e)}"}))

            elif action == "get_visualization":
                col1 = message.get("col1", "")
                col2 = message.get("col2") or None
                plot_type = message.get("plot_type", "histogram")

                if not col1:
                    await websocket.send_text(json.dumps({"type": "error", "message": "No column specified for visualization."}))
                    continue

                df = await run_in_threadpool(load_dataset_as_dataframe, dataset.s3_bucket, dataset.s3_key)
                eda_stats = await run_in_threadpool(calculate_eda_stats, df, col1)
                plot_data = await run_in_threadpool(get_plot_data, df, col1, col2, plot_type)

                await websocket.send_text(json.dumps({
                    "type": "visualization_result",
                    "eda_stats": eda_stats,
                    "plot_data": plot_data,
                }))

            elif action == "get_schema":
                # Return column list for visualization dropdowns
                if dataset.feature_schema:
                    schema = json.loads(dataset.feature_schema)
                    columns = list(schema.keys())
                else:
                    df = await run_in_threadpool(load_dataset_as_dataframe, dataset.s3_bucket, dataset.s3_key)
                    columns = df.columns.tolist()
                
                await websocket.send_text(json.dumps({
                    "type": "schema",
                    "columns": columns
                }))

        except WebSocketDisconnect:
            break
        except Exception as e:
            await websocket.send_text(json.dumps({"type": "error", "message": f"Critical Error: {str(e)}"}))
            break
    