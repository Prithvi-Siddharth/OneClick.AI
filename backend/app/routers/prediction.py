from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
import joblib
import pandas as pd
from io import BytesIO
import os

from app.db import get_db
from app.models import Experiment
from app.services.s3_operations import get_s3_client

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
        # Check if error is due to missing columns
        missing_cols = []
        try:
            # Try to identify missing columns if it's a value error
            if "feature names seen at fit time" in str(e):
                return JSONResponse(status_code=400, content={
                    "error": "Input data schema mismatch",
                    "details": str(e)
                })
        except:
            pass
            
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")
