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
from app.models import Experiment, TemporaryDataset
from app.services.model_factory import create_model_instance
import json
import ast
import traceback
import joblib
from io import BytesIO
from app.services.constants import ML_HYPERPARAMETERS
from app.services.model_factory import create_model_instance

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
        dataset = db.query(TemporaryDataset).filter(
            TemporaryDataset.id == dataset_id, 
            TemporaryDataset.user_id == int(user_id)
        ).first()
    
    try:
        hyperparams = get_hyperparameters(model)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Model {model} not supported")
    
    return templates.TemplateResponse("train_dataset.html", {
        "request": request,
        "dataset": dataset,
        "model": model,
        "hyperparameters": hyperparams
    })

@router.post("/tune_hyperparameters")
async def tune_hyperparameters(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"error": "Not authenticated"})
        
    data = await request.json()
    
    # 1. Save the state in a new Experiment record
    new_experiment = Experiment(
        user_id=int(user_id),
        algorithm=data.get("model_name"),
        hyperparameters=json.dumps(data.get("hyperparameters", {})),
        status="PENDING"
    )
    db.add(new_experiment)
    db.commit()
    db.refresh(new_experiment)
    # 2. Return the experiment ID so the frontend can redirect
    return {"status": "success", "experiment_id": new_experiment.id}


@router.get("/select_target/{experiment_id}")
def select_target_page(experiment_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login")

    experiment = db.query(Experiment).filter(Experiment.id == experiment_id, Experiment.user_id == int(user_id)).first()
    if not experiment:
        raise HTTPException(status_code =404, detail="Experiment not found")

    # Get the latest dataset to find column names
    dataset = db.query(TemporaryDataset).filter(TemporaryDataset.user_id == int(user_id)).order_by(TemporaryDataset.id.desc()).first()
    if not dataset:
        raise HTTPException(status_code=400, detail="No dataset found for training")
    
    # Robustly get columns from the actual S3 file to ensure preprocessed deletions are reflected
    try:
        from app.routers.preprocessing import read_df_from_s3
        df_columns = read_df_from_s3(dataset.s3_bucket, dataset.s3_key).columns.tolist()
        columns = df_columns
        
        # Sync the DB schema if it's different (optional but good for consistency)
        new_schema = {col: "unknown" for col in columns} # Types aren't strictly needed for the dropdown
        dataset.feature_schema = json.dumps(new_schema)
        db.commit()
    except Exception as e:
        print(f"Error fetching columns from S3: {e}")
        # Fallback to schema in DB if S3 fails
        try:
            if dataset.feature_schema:
                try:
                    schema = json.loads(dataset.feature_schema)
                except json.JSONDecodeError:
                    schema = ast.literal_eval(dataset.feature_schema)
            else:
                schema = {}
            columns = list(schema.keys())
        except Exception:
            columns = []

    return templates.TemplateResponse("select_target.html", {
        "request": request,
        "experiment_id": experiment_id,
        "columns": columns
    })

from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error, accuracy_score, f1_score
import pandas as pd
from app.services.s3_operations import load_dataset_as_dataframe

@router.post("/final_train")
async def final_train(request: Request, db: Session = Depends(get_db)):
    try:
        user_id = get_current_user_id(request)
        if not user_id:
            return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"error": "Not authenticated"})
            
        data = await request.json()
        experiment_id_raw = data.get("experiment_id")
        target_column = data.get("target_column")
        
        print(f"DEBUG: Starting final_train for experiment {experiment_id_raw}, target {target_column}")

        if not experiment_id_raw or not target_column:
            return JSONResponse(status_code=400, content={"error": "Missing experiment_id or target_column"})

        experiment_id = int(experiment_id_raw)
        
        # 1. Fetch Experiment and Dataset info
        experiment = db.query(Experiment).filter(Experiment.id == experiment_id, Experiment.user_id == int(user_id)).first()
        if not experiment:
             return JSONResponse(status_code=404, content={"error": "Experiment not found for this user"})
             
        # Use the newest temporary dataset for this user
        dataset = db.query(TemporaryDataset).filter(TemporaryDataset.user_id == int(user_id)).order_by(TemporaryDataset.id.desc()).first()
        if not dataset:
             return JSONResponse(status_code=404, content={"error": "No temporary dataset found"})
        
        print(f"DEBUG: Data found. Bucket: {dataset.s3_bucket}, Key: {dataset.s3_key}")
        
        # 2. Load the actual data from S3 into a Pandas DataFrame
        df = load_dataset_as_dataframe(dataset.s3_bucket, dataset.s3_key) 
        
        if target_column not in df.columns:
            return JSONResponse(status_code=400, content={"error": f"Target column '{target_column}' not found in dataset columns: {df.columns.tolist()}"})

        # 3. Prepare X and y
        X = df.drop(columns=[target_column])
        y = df[target_column]
        
        # Basic cleanup: drop any remaining rows with NaNs in the features or target
        X = X.dropna()
        y = y.loc[X.index] # Keep y aligned with X
        
        if X.empty:
            return JSONResponse(status_code=400, content={"error": "Dataset is empty after dropping missing values. Please preprocess your data first."})

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
        # 4. Initialize and Train Model
        hyperparams = json.loads(experiment.hyperparameters) if experiment.hyperparameters else {}
        model = create_model_instance(experiment.algorithm, hyperparams)
        
        print(f"DEBUG: Training model {experiment.algorithm}...")
        model.fit(X_train, y_train)
    
        # 4.5. Serialize and Save Model to S3
        print(f"DEBUG: Serializing and saving model...")
        model_buffer = BytesIO()
        joblib.dump(model, model_buffer)
        model_buffer.seek(0)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        model_filename = f"{experiment.algorithm}_{timestamp}.joblib"
        model_s3_key = f"{user_id}/models/{model_filename}"
        
        from app.services.s3_operations import get_s3_client
        s3 = get_s3_client()
        bucket_name = os.getenv("S3_BUCKET_NAME")
        s3.put_object(Bucket=bucket_name, Key=model_s3_key, Body=model_buffer.getvalue())
        
        experiment.model_artifact_path = model_s3_key
        experiment.name = model_filename

        # 5. Predict and Calculate Metrics
        predictions = model.predict(X_test)
        
        results = {}
        # Check task type from your constants.py
        model_info = ML_HYPERPARAMETERS.get(experiment.algorithm)
        
        if model_info["task"] == "regression":
            results["metrics"] = {
                "r2_score": r2_score(y_test, predictions),
                "mae": mean_absolute_error(y_test, predictions)
            }
        else:
            results["metrics"] = {
                "accuracy": accuracy_score(y_test, predictions),
                "f1_score": f1_score(y_test, predictions, average='weighted')
            }
    
        # 6. Prepare "Predicted vs Actual" for the chart (first 50 rows)
        comparison = []
        # Convert to native Python types for JSON serialization
        for actual, pred in zip(y_test[:10], predictions[:10]):
            comparison.append({
                "actual": float(actual) if hasattr(actual, "__float__") else actual, 
                "predicted": float(pred) if hasattr(pred, "__float__") else pred
            })
    
        # 7. Save to Database and Return
        experiment.metrics = json.dumps(results["metrics"])
        experiment.status = "COMPLETED"
        experiment.target_column = target_column
        db.commit()
    
        print(f"DEBUG: Training complete. Metrics: {results['metrics']}")
        return {
            "status": "success",
            "metrics": results["metrics"],
            "comparison": comparison
        }
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

