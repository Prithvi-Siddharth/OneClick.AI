from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import joblib
import pandas as pd
from io import BytesIO
import os

from app.db import get_db
from app.models import Experiment, Dataset
from app.services.s3_operations import get_s3_client, load_dataset_as_dataframe

router = APIRouter()

@router.post("/v1/predict/{model_id}")
async def predict(model_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Live Prediction Endpoint.
    Accepts JSON data, applies the saved pipeline (preprocessing + model),
    and returns the prediction result.
    """
    # 1. Fetch Model Metadata
    experiment = db.query(Experiment).filter(Experiment.id == model_id).first()
    if not experiment or not experiment.model_artifact_path:
        raise HTTPException(status_code=404, detail="Model not found or not yet trained")

    # 2. Get Input Data
    try:
        input_json = await request.json()
        # Convert single object to list if necessary for DataFrame
        if isinstance(input_json, dict):
            input_df = pd.DataFrame([input_json])
        else:
            input_df = pd.DataFrame(input_json)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON input: {str(e)}")

    # 3. Load Pipeline from S3
    try:
        s3 = get_s3_client()
        bucket_name = os.getenv("S3_BUCKET_NAME")
        if not bucket_name:
            raise ValueError("S3_BUCKET_NAME not configured")
            
        response = s3.get_object(Bucket=bucket_name, Key=experiment.model_artifact_path)
        model_bytes = response['Body'].read()
        pipeline = joblib.load(BytesIO(model_bytes))
    except Exception as e:
        print(f"ERROR: Failed to load model {model_id} from S3: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to load model from storage: {str(e)}")

    # 4. Run Prediction
    try:
        # The pipeline automatically handles the ColumnTransformer (imputing, scaling, encoding)
        # as long as the input_df has the same column names as the original X_train.
        predictions = pipeline.predict(input_df)
        
        # Convert numpy types to native Python types for JSON response
        result = predictions.tolist()
        
        return {
            "model_id": model_id,
            "model_name": experiment.name,
            "status": "success",
            "predictions": result,
            "timestamp": pd.Timestamp.now().isoformat()
        }
    except Exception as e:
        print(f"ERROR: Prediction failed for model {model_id}: {str(e)}")
        
        # Determine error details and provide a 'Hint' for Postman/External users
        status_code = 500
        error_detail = str(e)
        hint = "Ensure your JSON keys match the column names used during training."

        if "feature names seen at fit time" in str(e):
            status_code = 400
            error_detail = "Input data schema mismatch"
            hint = f"The model expects these exact features: {str(e).split('feature names seen at fit time: ')[-1]}"

        return JSONResponse(
            status_code=status_code,
            content={
                "status": "error",
                "error": error_detail,
                "hint": hint,
                "model_id": model_id
            }
        )

# ── PREDICT USING CATALOG DATASET ───────────────────────────────────────────
@router.post("/v1/predict_catalog/{model_id}/{dataset_id}")
async def predict_catalog(model_id: int, dataset_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Predict using a dataset stored in the Data Catalog.
    Returns a preview of the results (first 50 rows).
    """
    # 1. Fetch Model and Dataset
    experiment = db.query(Experiment).filter(Experiment.id == model_id).first()
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()

    if not experiment or not experiment.model_artifact_path:
        raise HTTPException(status_code=404, detail="Model not found")
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # 2. Load Dataset from S3
    try:
        df = load_dataset_as_dataframe(dataset.s3_bucket, dataset.s3_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load dataset: {str(e)}")

    # 3. Load Pipeline from S3
    try:
        s3 = get_s3_client()
        bucket_name = os.getenv("S3_BUCKET_NAME")
        response = s3.get_object(Bucket=bucket_name, Key=experiment.model_artifact_path)
        pipeline = joblib.load(BytesIO(response['Body'].read()))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}")

    # 4. Run Prediction
    try:
        # Prepare data (drop target if exists in input)
        X = df.copy()
        if experiment.target_column in X.columns:
            X = X.drop(columns=[experiment.target_column])
        
        predictions = pipeline.predict(X)
        
        # 5. Build Result Preview (Limit to first 50)
        df_display = df.head(50).copy()
        df_display['Prediction'] = predictions[:50]
        
        return {
            "status": "success",
            "model_name": experiment.name,
            "dataset_name": dataset.filename,
            "total_rows": len(df),
            "preview_rows": df_display.to_dict('records'),
            "predictions": predictions.tolist() # returning all predictions in case needed for export
        }
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "error": str(e),
                "hint": "Check if the dataset schema matches the model requirements."
            }
        )
