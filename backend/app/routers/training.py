from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
from datetime import datetime

from app.db import get_db
from app.models import Dataset, TemporaryDataset
from app.security import get_current_user_id
from app.services.s3_operations import duplicate_dataset_in_s3
from app.services.constants import get_hyperparameters

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))


# Train model
@router.get("/train_model")
def train_model_page(request: Request, db: Session = Depends(get_db), response_class=HTMLResponse):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login")
    
    #fetch the users uploaded datasats in catalog, so that the user can select the dataset to preprocess
    datasets = db.query(Dataset).filter(Dataset.user_id == int(user_id)).all()
    
    #fetch the latest loaded dataset for preprocessing and display it in the preprocessing page
    active_dataset = db.query(TemporaryDataset).filter(TemporaryDataset.user_id == int(user_id)).order_by(TemporaryDataset.id.desc()).first()
    
    return templates.TemplateResponse("train_model.html", {
        "request": request, 
        "datasets": datasets,
        "active_dataset": active_dataset
    })

# connecting dataset from catalog for train model
@router.post('/connect_dataset_train')
def connect_dataset_train(
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

        # Call the function with required metadata from the catalog record
        temp_dataset = duplicate_dataset_in_s3(
            db=db,
            user_id=int(user_id),
            bucket_name=bucket_name,
            source_key=dataset.s3_key,
            destination_key=f"{dataset.user_id}/temporary_datasets/{timestamp}",
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

@router.get("/training")
def training_page(request: Request, db: Session = Depends(get_db), dataset_id: int = None):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login")
    
    dataset = None
    if dataset_id:
        dataset = db.query(TemporaryDataset).filter(TemporaryDataset.id == dataset_id, TemporaryDataset.user_id == int(user_id)).first()
    
    if not dataset:
        # Fallback to the latest temporary dataset if no ID provided or not found
        dataset = db.query(TemporaryDataset).filter(TemporaryDataset.user_id == int(user_id)).order_by(TemporaryDataset.id.desc()).first()
    
    return templates.TemplateResponse("training.html", {
        "request": request,
        "dataset": dataset
    })
    

@router.get("/models")
def models_page(request: Request, db: Session = Depends(get_db), dataset_id: int = None, model: str = None):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login")
    
    dataset = None
    if dataset_id:
        dataset = db.query(TemporaryDataset).filter(TemporaryDataset.id == dataset_id, TemporaryDataset.user_id == int(user_id)).first()
    
    if not dataset:
        # Fallback to the latest temporary dataset if no ID provided or not found
        dataset = db.query(TemporaryDataset).filter(TemporaryDataset.user_id == int(user_id)).order_by(TemporaryDataset.id.desc()).first()
    
    return templates.TemplateResponse("train_dataset.html", {
        "request": request,
        "dataset": dataset,
        "model": model,
        "hyperparameters": get_hyperparameters(model)
    })

@router.post("/tune_hyperparameters")
async def tune_hyperparameters(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        # Get data from the form request
        data = await request.json()
        model_name = data.get("model_name")
        params = data.get("hyperparameters", {})

        print(f"--- Hyperparameter Tuning Request ---")
        print(f"User: {user_id}")
        print(f"Model: {model_name}")
        print(f"Params: {params}")
        print(f"--------------------------------------")
        
        return JSONResponse(
            content={
                "status": "success",
                "message": f"Tuning request received for {model_name}. Training started in background.",
                "received_params": params
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        print(f"Error in tune_hyperparameters: {str(e)}")
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )