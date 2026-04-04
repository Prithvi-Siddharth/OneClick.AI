from fastapi import APIRouter, Depends, HTTPException, Request, Form, File, UploadFile, status
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os, json

from app.db import get_db
from app.models import User, Experiment
from app.security import get_current_user_id
from app.services.s3_operations import get_user_models, upload_model_to_s3, s3_delete_object, create_presigned_download_url

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))

# this route is used to upload models to model catalog
@router.post("/upload_model")
def upload_model(
    request: Request,
    db: Session = Depends(get_db),
    modelName: str = Form(...),
    modelAlgorithm: str = Form(...),
    model_file: UploadFile = File(...),
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

        # Validate file extension
        filename = model_file.filename
        if not (filename.endswith('.pkl') or filename.endswith('.joblib')):
             return JSONResponse(
                content={"error": "Invalid file format. Only .pkl and .joblib are supported."},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        
        # Call the S3 service function
        model = upload_model_to_s3(
            db=db,
            file_obj=model_file,
            bucket_name=bucket_name,
            user_id=int(user_id),
            model_name=modelName,
            algorithm=modelAlgorithm
        )

        return JSONResponse(
            content={
                "message": "Model uploaded successfully",
                "model_id": model.id,
                "name": model.name,
                "algorithm": model.algorithm,
                "status": "COMPLETED"
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )



# this route is used to view all models in model catalog
@router.get("/view_models")
def view_models(request: Request, db: Session = Depends(get_db), response_class=HTMLResponse):

    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    models = get_user_models(db, int(user_id))
    
    return templates.TemplateResponse("view_models.html", {"request": request, "username": user.username, "models": models})

# this route is used to preview the model
@router.get("/preview_model/{model_id}")
def preview_model(model_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    model = db.query(Experiment).filter(Experiment.id == model_id, Experiment.user_id == int(user_id)).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Return basic metadata and metrics
    import json
    try:
        metrics = json.loads(model.metrics) if model.metrics else {}
        params = json.loads(model.hyperparameters) if model.hyperparameters else {}
    except:
        metrics = {}
        params = {}

    return JSONResponse(content={
        "name": model.name,
        "algorithm": model.algorithm,
        "status": model.status,
        "target_column": model.target_column,
        "metrics": metrics,
        "params": params,
        "created_at": model.created_at.strftime("%Y-%m-%d %H:%M:%S")
    })

# this route is used to delete the model
@router.delete("/delete_model/{model_id}")
def delete_model(model_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    model = db.query(Experiment).filter(Experiment.id == model_id, Experiment.user_id == int(user_id)).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    try:
        # 1. Delete from S3 first
        bucket_name = os.getenv("S3_BUCKET_NAME")
        if model.model_artifact_path and bucket_name:
            # This will raise an Exception if S3 deletion fails (e.g. Access Denied)
            s3_delete_object(bucket_name, model.model_artifact_path)
        
        # 2. Only if S3 is successful, delete from DB
        db.delete(model)
        db.commit()
        
        return JSONResponse(content={"message": "Model deleted successfully from S3 and database"})
    except Exception as e:
        db.rollback()
        print(f"ERROR: Model deletion failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete model: {str(e)}")

# this route is used to download the model
@router.get("/download_model/{model_id}")
def download_model(model_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    model = db.query(Experiment).filter(Experiment.id == model_id, Experiment.user_id == int(user_id)).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    bucket_name = os.getenv("S3_BUCKET_NAME")
    if not bucket_name:
        raise HTTPException(status_code=500, detail="S3_BUCKET_NAME not configured")
    
    # Generate presigned URL
    url = create_presigned_download_url(
        bucket_name=bucket_name,
        s3_key=model.model_artifact_path,
        filename=model.name if model.name.endswith(('.pkl', '.joblib')) else f"{model.name}.joblib"
    )
    
    return JSONResponse(content={"download_url": url})