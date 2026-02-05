import os
from dotenv import load_dotenv
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
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
    duplicate_dataset_in_s3
)

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
# directory of the templates
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

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


@app.get("/preview_dataset/{dataset_id}")
def preview_dataset(dataset_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.user_id == int(user_id)).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    # Read from S3
    data = read_dataset_from_s3(
        bucket_name=dataset.s3_bucket,
        s3_key=dataset.s3_key,
        filename=dataset.filename,
        preview_limit=5
    )
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    return JSONResponse(content=data)

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


# Change this route in main.py (around line 431)
@app.get("/preprocessing")
def preprocessing_page(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login")
    
    # Fetch user's uploaded datasets to show in the catalog dropdown
    datasets = db.query(Dataset).filter(Dataset.user_id == int(user_id)).all()
    
    # Fetch the latest loaded dataset for preprocessing
    active_dataset = db.query(TemporaryDataset).filter(TemporaryDataset.user_id == int(user_id)).order_by(TemporaryDataset.id.desc()).first()
    
    return templates.TemplateResponse("preprocessing.html", {
        "request": request, 
        "datasets": datasets,
        "active_dataset": active_dataset
    })

@app.get("/train_model")
def train_model_page(request: Request, response_class=HTMLResponse):
    return templates.TemplateResponse("train_model.html", {"request": request})

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