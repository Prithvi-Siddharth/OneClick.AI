import os
import pandas as pd
import json
from dotenv import load_dotenv
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from fastapi import File, UploadFile
from app.db import engine, get_db
from app.models import Base, User, Dataset, Experiment, TemporaryDataset
from app.schemas import RegisterRequest, RegisterResponse
from app.security import hash_password, verify_password, create_access_token, get_current_user_id
from app.services.s3_operations import (
    process_and_save_dataset, 
    get_user_datasets, 
    get_user_models,
    upload_model_to_s3,
    read_dataset_from_s3,
    s3_delete_object,
    create_presigned_download_url,
    process_and_save_dataset_temporary,
    duplicate_dataset_in_s3,
    get_s3_client
)
from app.services.data_preprocessing import apply_preprocessing

from fastapi.middleware.cors import CORSMiddleware


# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

#creates an app
app = FastAPI(title="ML SaaS Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
from fastapi.staticfiles import StaticFiles

# directory of the templates
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Mount static files
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

#this command connects to the tidb and creates a table from the structure defined earlier
Base.metadata.create_all(bind=engine)

# rendering of home.html page
@app.get("/")
def read_root(request: Request, response_class=HTMLResponse):
    return templates.TemplateResponse("home.html", {"request": request})
    

# Rendering of the register.html page
@app.get("/register")
def register_page(request: Request, response_class=HTMLResponse):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/about_developers")
def about_developers(request: Request):
    return templates.TemplateResponse("about_developers.html", {"request": request})

@app.get("/about_mission")
def about_mission(request: Request):
    return templates.TemplateResponse("about_mission.html", {"request": request})

@app.get("/about_techstack")
def about_techstack(request: Request):
    return templates.TemplateResponse("about_techstack.html", {"request": request})

@app.get("/about_guide")
def about_guide(request: Request):
    return templates.TemplateResponse("about_guide.html", {"request": request})


# User registration endpoint
@app.post("/register")
async def register_user(
    request: Request, # raw request object, used to check content like headers and type 
    user_data: RegisterRequest = None, # the request input format given in schemas.py, pydantic schema for JSON input
    username: str = Form(default=None), # the username input field from the register.html page
    email: str = Form(default=None), # the email input field from register.html page
    password: str = Form(default=None), # the password input field from register.html page
    db: Session = Depends(get_db), # gives a db session to query and insert into db
):
    # Handle both JSON (API) and Form data (HTML form)
    if user_data:
        username = user_data.username
        email = user_data.email
        password = user_data.password
    
    # Validate required fields
    if not username or not email or not password: 
        if request.headers.get("content-type") == "application/json": # this is shown in the backend/ not in the UI
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All fields are required.",
            )
        else: # this is shown in the UI
            return templates.TemplateResponse(
                "register.html",
                {
                    "request": request,
                    "error": "All fields are required.", # this is variable to display in the UI, in register.html
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    
    # check if the username already exists
    existing_user = db.query(User).filter((User.username == username) | (User.email == email)).first()

    # if the username already exists, raise an error
    if existing_user:
        if request.headers.get("content-type") == "application/json":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email already exists.",
            )
        else:
            # this is to display in the UI, in register.html
            return templates.TemplateResponse( 
                "register.html",
                {
                    "request": request,
                    "error": "Username or email already exists.",
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    
    # create a new user
    new_user = User(
        username=username,
        email=email,
        password=hash_password(password),
    )

    # add the new user to the database
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Return JSON for API calls, HTML response for form submissions
    if request.headers.get("content-type") == "application/json":
        return RegisterResponse(
            user_id=new_user.user_id,
            username=new_user.username,
            email=new_user.email,
            created_at=new_user.created_at,
        )
    else:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "message": "Registration successful! You can now log in.",
            },
            status_code=status.HTTP_201_CREATED,
        )


# rendering of the login.html
@app.get("/login")
def login_page(request: Request, response_class=HTMLResponse):
    return templates.TemplateResponse("login.html", {"request": request})

# user login endpoint
@app.post("/login")
def login_user(
    # the email, password are taken from the form data
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):

    #checks if the user email already exists
    user = db.query(User).filter(User.email == email).first()

    # checks if the password is correct and modifies the variable error as query param here 
    if not user or not verify_password(password, user.password):
        return RedirectResponse(
            url="/login?error=invalid_credentials",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # access token is created
    access_token = create_access_token(
        data={"sub": str(user.user_id)}
    )

    # redirected to dashboard.html if the user is logged in successfully
    response = RedirectResponse(
        url="/dashboard",
        status_code=status.HTTP_303_SEE_OTHER,

    )

    # the response cookie is set
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,   # set True in production (HTTPS)
        samesite="lax",
    )

    return response


# rendering of the dashboard.html
@app.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    # checks if the user is logged in
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    # checks if the user exists
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    datasets = get_user_datasets(db, int(user_id), limit=5)
    models = get_user_models(db, int(user_id), limit=5)

    print(f"DEBUG Dashboard: ID={user_id}, User={user.username}, Datasets={len(datasets)}, Models={len(models)}")

    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "username": user.username,
        "datasets": datasets,
        "models": models
    })


# when the logout button is clicked, the access token cookie is deleted and redirected to login page
@app.get("/logout")
def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response


@app.post("/upload_dataset")
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


@app.post("/upload_model")
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


# rendering of the view_datasets.html
@app.get("/view_datasets")
def view_dataset(request: Request, db: Session = Depends(get_db), response_class=HTMLResponse):

    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    datasets = get_user_datasets(db, int(user_id))
    
    return templates.TemplateResponse("view_datasets.html", {"request": request, "username": user.username, "datasets": datasets})

@app.get("/view_models")
def view_models(request: Request, db: Session = Depends(get_db), response_class=HTMLResponse):

    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    models = get_user_models(db, int(user_id))
    
    return templates.TemplateResponse("view_models.html", {"request": request, "username": user.username, "models": models})

@app.get("/preview_model/{model_id}")
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

@app.delete("/delete_model/{model_id}")
def delete_model(model_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    model = db.query(Experiment).filter(Experiment.id == model_id, Experiment.user_id == int(user_id)).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Delete from S3
    bucket_name = os.getenv("S3_BUCKET_NAME")
    if model.model_artifact_path and bucket_name:
        s3_delete_object(bucket_name, model.model_artifact_path)
    
    # Delete from DB
    db.delete(model)
    db.commit()
    
    return JSONResponse(content={"message": "Model deleted successfully"})

@app.get("/download_model/{model_id}")
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

#this route is used to preview the dataset
@app.get("/preview_dataset/{dataset_id}")
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

@app.delete("/delete_dataset/{dataset_id}")
def delete_dataset(dataset_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.user_id == int(user_id)).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    # Delete from S3
    s3_key = dataset.s3_key
    s3_bucket = dataset.s3_bucket
    s3_delete_object(s3_bucket, s3_key)
    # Delete from database
    db.delete(dataset)
    db.commit()
    return JSONResponse(content={"message": "Dataset deleted successfully"})

@app.get("/download_dataset/{dataset_id}")
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


#preprocessing page
@app.get("/preprocessing")
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
@app.post("/temporary_upload_dataset")
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

# Update your connect_dataset route (around line 503)
@app.post('/connect_dataset')
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


@app.get("/preview_temporary_dataset/{temp_id}")
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
        filename=f"temp_{temp_id}.csv", # Placeholder name
        preview_limit=5
    )
    
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    
    return JSONResponse(content=data)

@app.get("/preprocess-dataset")
def preprocess_dataset(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return templates.TemplateResponse("preprocess-dataset.html", {
        "request": request,
        "username": user.username
    })

# Train model
@app.get("/train_model")
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
@app.post('/connect_dataset_train')
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

@app.get("/training")
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
    

@app.get("/models")
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
    
    return templates.TemplateResponse("models.html", {
        "request": request,
        "dataset": dataset,
        "model": {"name": model} if model else None
    })

#websocket route for testing
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    #accept the websocket connection
    await websocket.accept()
    print("Client connected")
    while True:
        #receive the message from the client
        data = await websocket.receive_text()
        #send the message to the client
        await websocket.send_text(f"Message text was: {data}")


#websocket route for preprocessing the dataset
@app.websocket("/preprocess-dataset/ws")
async def websocket_preprocess(websocket: WebSocket, db: Session = Depends(get_db)):
    #accept the websocket connection
    await websocket.accept()
    
    async def send_status(msg):
        await websocket.send_text(json.dumps({"type": "status", "message": msg}))

    async def send_preview(df):
        # head(5) and convert to records
        preview = df.head(5).where(pd.notnull(df), None).to_dict(orient="records")
        await websocket.send_text(json.dumps({"type": "preview", "data_preview": preview}))

    # helper to get user id from websocket
    token = websocket.cookies.get("access_token")
    user_id = None
    if token:
        try:
            from app.security import JWT_SECRET_KEY, JWT_ALGORITHM
            from jose import jwt
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("sub")
        except:
            pass

    if not user_id:
        await websocket.send_text(json.dumps({"type": "status", "message": "❌ Authentication failed. Please log in."}))
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
                s3 = get_s3_client()
                response = s3.get_object(Bucket=active_dataset.s3_bucket, Key=active_dataset.s3_key)
                from io import BytesIO
                df = pd.read_csv(BytesIO(response['Body'].read()))
                await send_preview(df)
                await send_status("✅ Preview loaded.")
            
            elif action == "apply_preprocessing":
                await send_status("📡 Backend received preprocessing request...")
                await send_status(f"📝 Processing dataset: {active_dataset.s3_key}")
                
                # 2. Load from S3
                s3 = get_s3_client()
                response = s3.get_object(Bucket=active_dataset.s3_bucket, Key=active_dataset.s3_key)
                from io import BytesIO
                df = pd.read_csv(BytesIO(response['Body'].read()))

                # 3. Apply preprocessing
                ops = message.get("operations", {})
                await send_status(f"⚙️ Applying operations: {ops}")
                processed_df = apply_preprocessing(df, ops)

                if isinstance(processed_df, dict) and "error" in processed_df:
                    await send_status(f"❌ Error: {processed_df['error']}")
                    continue

                # 4. Save result back to S3
                csv_buffer = BytesIO()
                processed_df.to_csv(csv_buffer, index=False)
                csv_buffer.seek(0)
                
                await send_status("💾 Saving changes to S3...")
                s3.put_object(Bucket=active_dataset.s3_bucket, Key=active_dataset.s3_key, Body=csv_buffer.getvalue())
                
                # 5. Send updated preview
                await send_preview(processed_df)
                await send_status("🚀 Preprocessing complete! The dataset has been updated.")
                
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "status", "message": f"❌ Critical Error: {str(e)}"}))
        except:
            pass
