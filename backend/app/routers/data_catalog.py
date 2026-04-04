from fastapi import APIRouter, Depends, HTTPException, Request, Form, File, UploadFile, status
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
from datetime import datetime

from app.db import get_db
from app.models import User, Dataset, TemporaryDataset
from app.security import get_current_user_id
from app.services.s3_operations import (
    process_and_save_dataset, get_user_datasets, read_dataset_from_s3,
    s3_delete_object, create_presigned_download_url,
    process_and_save_dataset_temporary, duplicate_dataset_in_s3
)

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))

# upload dataset to data catalog
@router.post("/upload_dataset")
def upload_dataset(
    request: Request,
    db: Session = Depends(get_db),
    datasetFilename: str = Form(...),
    datasetDescription: str = Form(...),
    dataset_file: UploadFile = File(...),
):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
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

# rendering of the view_datasets.html to view all datasets in the data catalog
@router.get("/view_datasets")
def view_dataset(request: Request, db: Session = Depends(get_db), response_class=HTMLResponse):

    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    datasets = get_user_datasets(db, int(user_id))
    
    return templates.TemplateResponse("view_datasets.html", {"request": request, "username": user.username, "datasets": datasets})

#this route is used to preview the dataset
@router.get("/preview_dataset/{dataset_id}")
def preview_dataset(dataset_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.user_id == int(user_id)).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    #read from s3, the preview and stats of the dataset
    data = read_dataset_from_s3(
        bucket_name=dataset.s3_bucket,
        s3_key=dataset.s3_key,
        filename=dataset.filename,
        preview_limit=5
    )
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    return JSONResponse(content=data) #return the data

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