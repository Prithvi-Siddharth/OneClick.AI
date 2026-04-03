from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import os
from datetime import datetime

from app.db import get_db
from app.models import User, Dataset, Experiment, Note, PreprocessingLog, TemporaryDataset
from app.security import get_current_user_id, verify_password, hash_password
from app.services.s3_operations import upload_file_to_s3, s3_delete_object, create_presigned_download_url
from fastapi import File, UploadFile, Form
import json

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))

@router.get("/profile", response_class=HTMLResponse)
async def get_profile(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login")
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Aggregating Statistics
    dataset_count = db.query(Dataset).filter(Dataset.user_id == int(user_id)).count()
    experiment_count = db.query(Experiment).filter(Experiment.user_id == int(user_id)).count()
    deployed_count = db.query(Experiment).filter(Experiment.user_id == int(user_id), Experiment.status == "DEPLOYED").count()
    note_count = db.query(Note).filter(Note.user_id == int(user_id)).count()

    # Aggregating Recent Activity (limit each to last 5)
    recent_datasets = db.query(Dataset).filter(Dataset.user_id == int(user_id)).order_by(Dataset.upload_date.desc()).limit(5).all()
    recent_experiments = db.query(Experiment).filter(Experiment.user_id == int(user_id)).order_by(Experiment.created_at.desc()).limit(5).all()
    recent_notes = db.query(Note).filter(Note.user_id == int(user_id)).order_by(Note.created_at.desc()).limit(5).all()
    recent_preprocessing = db.query(PreprocessingLog).filter(PreprocessingLog.user_id == int(user_id)).order_by(PreprocessingLog.timestamp.desc()).limit(5).all()

    # Transform into a unified activity timeline
    activities = []

    for d in recent_datasets:
        activities.append({
            "type": "dataset_upload",
            "title": f"Uploaded Dataset: {d.filename}",
            "time": d.upload_date,
            "icon": "fa-cloud-upload-alt",
            "color": "#4caf50"
        })

    for e in recent_experiments:
        activities.append({
            "type": "experiment_run",
            "title": f"Ran Experiment: {e.name or 'Unnamed Experiment'}",
            "time": e.created_at,
            "icon": "fa-brain",
            "color": "#2196f3"
        })

    for n in recent_notes:
        activities.append({
            "type": "note_save",
            "title": "Saved a new sticky note",
            "time": n.created_at,
            "icon": "fa-sticky-note",
            "color": "#ffc107"
        })
    
    for p in recent_preprocessing:
        activities.append({
            "type": "preprocessing",
            "title": f"Processed {p.operation_name} on attributes",
            "time": p.timestamp,
            "icon": "fa-cogs",
            "color": "#9c27b0"
        })

    # Sort activities by newest first
    activities.sort(key=lambda x: x["time"] if x["time"] else datetime.min, reverse=True)
    activities = activities[:10]  # Show only last 10 total

    # Handle Profile Picture Presigned URL
    profile_pic_url = None
    if user.profile_pic_url:
        bucket_name = os.getenv("S3_BUCKET_NAME")
        profile_pic_url = create_presigned_download_url(
            bucket_name, 
            user.profile_pic_url, 
            f"avatar_{user.username}.jpg", # dummy filename
            expiration=3600
        )

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user,
        "username": user.username,
        "dataset_count": dataset_count,
        "experiment_count": experiment_count,
        "deployed_count": deployed_count,
        "note_count": note_count,
        "activities": activities,
        "joined_date": user.created_at.strftime("%B %d, %Y") if user.created_at else "Jan 01, 2026",
        "profile_pic": profile_pic_url
    })

@router.post("/profile/upload_pic")
async def upload_profile_pic(
    request: Request,
    profile_pic: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user_id = get_current_user_id(request)
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})
    
    bucket_name = os.getenv("S3_BUCKET_NAME")
    if not bucket_name:
        return JSONResponse(status_code=500, content={"error": "S3 bucket not configured"})
    
    # Generate unique path for profile pic
    ext = profile_pic.filename.split('.')[-1]
    s3_key = f"profile_pics/{user_id}/avatar_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{ext}"
    
    success = upload_file_to_s3(profile_pic, bucket_name, s3_key)
    if not success:
        return JSONResponse(status_code=500, content={"error": "Failed to upload to S3"})
    
    # Update user record
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    user.profile_pic_url = s3_key
    db.commit()
    
    return JSONResponse(content={"message": "Profile picture updated", "url": s3_key})

@router.put("/profile/settings")
async def update_settings(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user_id = get_current_user_id(request)
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    
    # Verify password before any changes
    if not verify_password(password, user.password):
        return JSONResponse(status_code=401, content={"error": "Incorrect password"})
    
    # Check if username or email already exists for another user
    existing_user = db.query(User).filter(
        ((User.username == username) | (User.email == email)) & 
        (User.user_id != user.user_id)
    ).first()
    
    if existing_user:
        return JSONResponse(status_code=400, content={"error": "Username or email already taken"})
    
    user.username = username
    user.email = email
    db.commit()
    
    return JSONResponse(content={"message": "Settings updated successfully"})

@router.put("/profile/change_password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db)
):
    user_id = get_current_user_id(request)
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    
    # Verify current password
    if not verify_password(current_password, user.password):
        return JSONResponse(status_code=401, content={"error": "Incorrect current password"})
    
    # Simple validation for new password length
    if len(new_password) < 6:
        return JSONResponse(status_code=400, content={"error": "New password must be at least 6 characters"})
    
    user.password = hash_password(new_password)
    db.commit()
    
    return JSONResponse(content={"message": "Password changed successfully"})

@router.delete("/profile/account")
async def delete_account(
    request: Request,
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user_id = get_current_user_id(request)
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    
    # Verify password
    if not verify_password(password, user.password):
        return JSONResponse(status_code=401, content={"error": "Incorrect password"})
    
    try:
        bucket_name = os.getenv("S3_BUCKET_NAME")
        
        # 1. Delete Datasets from S3 and DB
        datasets = db.query(Dataset).filter(Dataset.user_id == int(user_id)).all()
        for d in datasets:
            s3_delete_object(bucket_name, d.s3_key)
            db.delete(d)
        
        # 2. Delete Experiments (Models) from S3 and DB
        experiments = db.query(Experiment).filter(Experiment.user_id == int(user_id)).all()
        for e in experiments:
            if e.model_artifact_path:
                s3_delete_object(bucket_name, e.model_artifact_path)
            db.delete(e)
            
        # 3. Delete Temp Datasets
        temps = db.query(TemporaryDataset).filter(TemporaryDataset.user_id == int(user_id)).all()
        for t in temps:
            if t.s3_key and t.s3_key != "PENDING":
                s3_delete_object(bucket_name, t.s3_key)
            db.delete(t)
            
        # 4. Delete Profile Picture
        if user.profile_pic_url:
            s3_delete_object(bucket_name, user.profile_pic_url)
            
        # 5. Delete Logs and Notes
        db.query(PreprocessingLog).filter(PreprocessingLog.user_id == int(user_id)).delete()
        db.query(Note).filter(Note.user_id == int(user_id)).delete()
        
        # 6. Delete User
        db.delete(user)
        db.commit()
        
        # Clear cookie
        from fastapi.responses import RedirectResponse
        response = JSONResponse(content={"message": "Account deleted successfully"})
        response.delete_cookie(key="access_token")
        return response
        
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"error": f"Failed to delete account: {str(e)}"})
