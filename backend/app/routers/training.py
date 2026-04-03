from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
from datetime import datetime

from app.db import get_db
from app.models import Dataset, TemporaryDataset, Experiment
from app.security import get_current_user_id
from app.services.s3_operations import duplicate_dataset_in_s3
from app.services.constants import ML_HYPERPARAMETERS, get_hyperparameters, get_grid_search_params
from app.services.model_factory import create_model_instance, get_base_model
from app.services.learning_algorithm_selector import recommend_algorithms_scoring
import json
import ast
import traceback
import joblib
import pandas as pd
from io import BytesIO
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder, LabelEncoder
from sklearn.impute import SimpleImputer

ALGO_MAPPING = {
    "Linear Regression": "LinearRegression",
    "Ridge (L2)": "Ridge",
    "Lasso (L1)": "Lasso",
    "SVR": "SVR",
    "KNN Regressor": "KNeighborsRegressor",
    "Logistic Regression": "LogisticRegression",
    "SVC": "SVC",
    "KNN Classifier": "KNeighborsClassifier",
    "Decision Tree": "DecisionTree",
    "Random Forest": "RandomForest",
    "KMeans Clustering": "KMeans"
}

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
            filename=dataset.filename, # ADD THIS
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


@router.post("/auto_tune")
async def auto_tune(request: Request, db: Session = Depends(get_db)):
    """Runs GridSearchCV in a background thread to automatically find best hyperparameters."""
    import asyncio
    from sklearn.model_selection import GridSearchCV
    from sklearn.preprocessing import LabelEncoder

    user_id = get_current_user_id(request)
    if not user_id:
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"error": "Not authenticated"})

    data = await request.json()
    model_name = data.get("model_name")
    target_column = data.get("target_column")

    if not model_name or not target_column:
        return JSONResponse(status_code=400, content={"error": "Missing model_name or target_column"})

    # 1. Guard: clustering models are not supported by GridSearchCV
    model_info = ML_HYPERPARAMETERS.get(model_name)
    if not model_info:
        return JSONResponse(status_code=400, content={"error": f"Model '{model_name}' is not supported."})
    if model_info["task"] == "clustering":
        return JSONResponse(status_code=400, content={"error": f"Auto-Tune is not supported for clustering models like '{model_name}'. GridSearchCV requires a labelled target column."})

    # 2. Load dataset from S3
    dataset = db.query(TemporaryDataset).filter(
        TemporaryDataset.user_id == int(user_id)
    ).order_by(TemporaryDataset.id.desc()).first()
    if not dataset:
        return JSONResponse(status_code=404, content={"error": "No temporary dataset found. Please load a dataset first."})

    try:
        from app.services.s3_operations import load_dataset_as_dataframe
        df = load_dataset_as_dataframe(dataset.s3_bucket, dataset.s3_key)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Failed to load dataset from S3: {str(e)}"})

    if target_column not in df.columns:
        return JSONResponse(status_code=400, content={"error": f"Target column '{target_column}' not found in dataset."})

    # 3. Prepare X, y (same logic as /final_train)
    df = df.dropna()
    if df.empty:
        return JSONResponse(status_code=400, content={"error": "Dataset is empty after dropping missing values."})

    X = df.drop(columns=[target_column])
    y = df[target_column]
    X = pd.get_dummies(X, drop_first=True)

    if model_info["task"] == "classification" and (y.dtype == "object" or y.dtype.name == "category"):
        le = LabelEncoder()
        y = le.fit_transform(y)

    from sklearn.model_selection import train_test_split
    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=42)

    # 4. Build GridSearchCV
    scoring = "accuracy" if model_info["task"] == "classification" else "r2"
    param_grid = get_grid_search_params(model_name)
    base_model = get_base_model(model_name)

    grid_search = GridSearchCV(
        estimator=base_model,
        param_grid=param_grid,
        cv=3,
        scoring=scoring,
        n_jobs=-1,
        refit=False   # We don't need the fitted model, just best_params_
    )

    # 5. Run GridSearchCV in a thread pool so we don't block the async event loop
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, lambda: grid_search.fit(X_train, y_train))
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"GridSearchCV failed: {str(e)}"})

    best_params = grid_search.best_params_
    best_score = round(grid_search.best_score_, 4)
    print(f"DEBUG: Auto-tune complete. Best params: {best_params}, Best CV score ({scoring}): {best_score}")

    # 6. Save as a new Experiment record (same format as /tune_hyperparameters)
    new_experiment = Experiment(
        user_id=int(user_id),
        algorithm=model_name,
        hyperparameters=json.dumps(best_params),
        status="PENDING"
    )
    db.add(new_experiment)
    db.commit()
    db.refresh(new_experiment)

    return {
        "status": "success",
        "experiment_id": new_experiment.id,
        "best_params": best_params,
        "best_cv_score": best_score,
        "scoring": scoring
    }


@router.get("/select_target/{experiment_id}")
def select_target_page(
    experiment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    mode: str = "manual",       # "manual" or "auto_tune"
    model_name: str = None      # passed through for auto_tune mode
):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login")

    experiment = db.query(Experiment).filter(Experiment.id == experiment_id, Experiment.user_id == int(user_id)).first()
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

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
        "columns": columns,
        "mode": mode,
        "model_name": model_name or experiment.algorithm
    })

from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error, accuracy_score, f1_score
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

        # Basic cleanup: drop any remaining rows with NaNs
        df = df.dropna()
        if df.empty:
            return JSONResponse(status_code=400, content={"error": "Dataset is empty after dropping missing values."})

        X = df.drop(columns=[target_column])
        y = df[target_column]
        
        # 3. Model Configuration & Pipeline Setup
        
        # Determine task type
        model_info = ML_HYPERPARAMETERS.get(experiment.algorithm)
        
        # Label encode classification targets if they are non-numeric
        if model_info["task"] == "classification" and (y.dtype == 'object' or y.dtype.name == 'category'):
            from sklearn.preprocessing import LabelEncoder
            le = LabelEncoder()
            y = le.fit_transform(y)
    
        # 4. Prepare S3 & Model Metadata
        from app.services.s3_operations import get_s3_client
        s3 = get_s3_client()
        bucket_name = os.getenv("S3_BUCKET_NAME")
        if not bucket_name:
            return JSONResponse(status_code=500, content={"error": "S3_BUCKET_NAME not configured"})

        # Generate standard filename and key
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        model_filename = f"model_{experiment.algorithm}_{timestamp}.joblib"
        model_s3_key = f"{user_id}/models/{model_filename}"

        # 5. Define Feature Groups (Preprocessing Automation)
        # We handle this inside the Pipeline to avoid training-serving skew
        numeric_features = X.select_dtypes(include=['int64', 'float64']).columns.tolist()
        categorical_features = X.select_dtypes(include=['object', 'category']).columns.tolist()

        # Define Transformers
        numeric_transformer = Pipeline(steps=[
            ('imputer', SimpleImputer(strategy='median')),
            ('scaler', StandardScaler())
        ])

        categorical_transformer = Pipeline(steps=[
            ('imputer', SimpleImputer(strategy='constant', fill_value='missing')),
            ('onehot', OneHotEncoder(handle_unknown='ignore'))
        ])

        preprocessor = ColumnTransformer(
            transformers=[
                ('num', numeric_transformer, numeric_features),
                ('cat', categorical_transformer, categorical_features)
            ])

        # 6. Initialize Model and Build Pipeline
        hyperparams = json.loads(experiment.hyperparameters) if experiment.hyperparameters else {}
        model_instance = create_model_instance(experiment.algorithm, hyperparams)

        pipeline = Pipeline(steps=[
            ('preprocessor', preprocessor),
            ('model', model_instance)
        ])

        # 7. Train and Save Test Split
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        print(f"DEBUG: Training full inference pipeline for {experiment.algorithm}...")
        pipeline.fit(X_train, y_train)

        # 8. Serialize and Save to S3
        print(f"DEBUG: Saving full pipeline to S3...")
        pipeline_buffer = BytesIO()
        joblib.dump(pipeline, pipeline_buffer)
        pipeline_buffer.seek(0)
        
        s3.put_object(Bucket=bucket_name, Key=model_s3_key, Body=pipeline_buffer.getvalue())

        # Update experiment record
        experiment.model_artifact_path = model_s3_key
        experiment.name = model_filename

        # 5. Predict using the pipeline and Calculate Metrics
        predictions = pipeline.predict(X_test)
        
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
            "status": "trained_pending_save",
            "metrics": results["metrics"],
            "comparison": comparison
        }
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/suggest_algorithm")
def suggest_algorithm_page(request: Request, db: Session = Depends(get_db), dataset_id: int = None):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login")
    
    return templates.TemplateResponse("algorithm_suggestion_form.html", {
        "request": request,
        "dataset_id": dataset_id
    })

@router.post("/suggest_algorithm")
async def suggest_algorithm_results(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login")
    
    form_data = await request.form()
    
    # Extract form values with defaults from the service function signiture
    problem_type = form_data.get("problem_type", "classification")
    dataset_size = form_data.get("dataset_size", "medium")
    feature_type = form_data.get("feature_type", "numerical")
    noise_level = form_data.get("noise_level", "medium")
    need_interpretability = form_data.get("need_interpretability") == "true"
    linearity = form_data.get("linearity", "unknown")
    class_balance = form_data.get("class_balance", "balanced")
    speed_requirement = form_data.get("speed_requirement", "moderate")
    n_features = form_data.get("n_features", "medium")
    dataset_id = form_data.get("dataset_id")

    # Call the suggestion logic
    top_3_raw = recommend_algorithms_scoring(
        problem_type=problem_type,
        dataset_size=dataset_size,
        feature_type=feature_type,
        noise_level=noise_level,
        need_interpretability=need_interpretability,
        linearity=linearity,
        class_balance=class_balance,
        speed_requirement=speed_requirement,
        n_features=n_features
    )

    # Use ML_HYPERPARAMETERS for descriptions
    from app.services.constants import ML_HYPERPARAMETERS
    
    recommended_algos = []
    for raw_name in top_3_raw:
        mapped_name = ALGO_MAPPING.get(raw_name, raw_name)
        info = ML_HYPERPARAMETERS.get(mapped_name, {})
        recommended_algos.append({
            "display_name": raw_name,
            "mapped_name": mapped_name,
            "task": info.get("task", "unknown"),
        })

    return templates.TemplateResponse("algorithm_suggestion_results.html", {
        "request": request,
        "recommended_algorithms": recommended_algos,
        "dataset_id": dataset_id
    })

@router.post("/save_to_catalog")
async def save_to_catalog(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    experiment_id = data.get("experiment_id")
    custom_name = data.get("custom_name")

    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()

    if not custom_name.endswith('.joblib'):
        custom_name += ".joblib"
        
    experiment.name = custom_name
    experiment.status = "COMPLETED"
    db.commit()
    
    return {"status": "success", "message": "Model saved to catalog as " + custom_name}