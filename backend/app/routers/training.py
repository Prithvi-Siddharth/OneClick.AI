from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
from datetime import datetime

from app.db import get_db
from app.models import User, Dataset, Experiment
from app.security import get_current_user_id
from app.services.constants import ML_HYPERPARAMETERS, get_hyperparameters, get_grid_search_params
from app.services.model_factory import create_model_instance, get_base_model
from app.services.learning_algorithm_selector import recommend_algorithms_scoring
import json
import ast
import traceback
import joblib
import pandas as pd
import numpy as np
from io import BytesIO
from app.services.algorithm_info import ALGORITHM_DETAILS
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
    # Using the most recently uploaded Catalog dataset as the "active" one
    active_dataset = db.query(Dataset).filter(Dataset.user_id == int(user_id)).order_by(Dataset.id.desc()).first()
    
    # Fetch user for navbar profile
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    
    return templates.TemplateResponse("train_model.html", {
        "request": request, 
        "username": user.username if user else None,
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

    # Just return the ID. The frontend will redirect to /training?dataset_id={dataset_id}
    return JSONResponse(
        content={
            "message": "Dataset connected successfully",
            "dataset_id": dataset.id,
            "row_count": dataset.row_count,
            "file_size": dataset.file_size
        },
        status_code=status.HTTP_200_OK
    )

@router.get("/training")
def training_page(request: Request, db: Session = Depends(get_db), dataset_id: int = None):
    # Fetch all folders and datasets for sidebars/modals
    # (Same as before)
    # ... (skipping for brevity but including the logic change below)
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login")
    
    dataset = None
    if dataset_id:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.user_id == int(user_id)).first()
    
    # Fetch user for navbar profile
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    
    # Also fetch all catalog datasets for the modal
    datasets = db.query(Dataset).filter(Dataset.user_id == int(user_id)).all()
    
    return templates.TemplateResponse("training.html", {
        "request": request,
        "dataset": dataset,
        "username": user.username if user else None,
        "datasets": datasets,
    })

@router.get("/algorithm_details/{algo_name}")
def algorithm_details_page(algo_name: str, request: Request, db: Session = Depends(get_db), dataset_id: int = None):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login")
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    
    # Get details for the algorithm
    details = ALGORITHM_DETAILS.get(algo_name)
    if not details:
        raise HTTPException(status_code=404, detail="Algorithm details not found")
    
    return templates.TemplateResponse("algorithm_details.html", {
        "request": request,
        "username": user.username if user else None,
        "details": {**details, "id": algo_name},
        "dataset_id": dataset_id
    })
    

@router.get("/models")
def models_page(request: Request, db: Session = Depends(get_db), dataset_id: int = None, model: str = None):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login")
    
    dataset = None
    if dataset_id:
        dataset = db.query(Dataset).filter(
            Dataset.id == dataset_id, 
            Dataset.user_id == int(user_id)
        ).first()
    
    try:
        hyperparams = get_hyperparameters(model)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Model {model} not supported")
    
    # Fetch user for navbar profile
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    
    return templates.TemplateResponse("train_dataset.html", {
        "request": request,
        "username": user.username if user else None,
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

    # 2. Load dataset from Catalog
    dataset_id = data.get("dataset_id")
    if dataset_id:
        dataset = db.query(Dataset).filter(
            Dataset.id == int(dataset_id),
            Dataset.user_id == int(user_id)
        ).first()
    else:
        # Fallback to the newest dataset for this user
        dataset = db.query(Dataset).filter(
            Dataset.user_id == int(user_id)
        ).order_by(Dataset.id.desc()).first()
    
    if not dataset:
        return JSONResponse(status_code=404, content={"error": "No dataset found in catalog. Please upload one first."})

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
    dataset = db.query(Dataset).filter(Dataset.user_id == int(user_id)).order_by(Dataset.id.desc()).first()
    if not dataset:
        raise HTTPException(status_code=400, detail="No dataset found in catalog for training")
    
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

    model_task = ML_HYPERPARAMETERS.get(experiment.algorithm, {}).get("task", "unknown")

    # Fetch user for navbar profile
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    
    return templates.TemplateResponse("select_target.html", {
        "request": request,
        "username": user.username if user else None,
        "experiment_id": experiment_id,
        "columns": columns,
        "mode": mode,
        "model_name": model_name or experiment.algorithm,
        "model_task": model_task
    })

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    r2_score, mean_absolute_error, mean_squared_error,
    explained_variance_score, median_absolute_error, max_error,
    accuracy_score, precision_score, f1_score, recall_score,
    fbeta_score, confusion_matrix, cohen_kappa_score, matthews_corrcoef,
    roc_auc_score, log_loss, brier_score_loss,
    silhouette_score, calinski_harabasz_score, davies_bouldin_score,
)
from app.services.s3_operations import load_dataset_as_dataframe

@router.post("/final_train")
async def final_train(request: Request, db: Session = Depends(get_db)):
    try:
        user_id = get_current_user_id(request)
        if not user_id:
            return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"error": "Not authenticated"})

        data = await request.json()
        experiment_id_raw = data.get("experiment_id")
        target_column = data.get("target_column")  # None for clustering

        if not experiment_id_raw:
            return JSONResponse(status_code=400, content={"error": "Missing experiment_id"})

        experiment_id = int(experiment_id_raw)

        # 1. Fetch Experiment and Dataset info
        experiment = db.query(Experiment).filter(Experiment.id == experiment_id, Experiment.user_id == int(user_id)).first()
        if not experiment:
            return JSONResponse(status_code=404, content={"error": "Experiment not found for this user"})

        model_info = ML_HYPERPARAMETERS.get(experiment.algorithm)
        if not model_info:
            return JSONResponse(status_code=400, content={"error": f"Unknown algorithm: {experiment.algorithm}"})

        is_clustering = model_info["task"] == "clustering"

        if not is_clustering and not target_column:
            return JSONResponse(status_code=400, content={"error": "Missing target_column"})

        # Use the specific dataset if provided, otherwise newest
        dataset_id = data.get("dataset_id")
        if dataset_id:
            dataset = db.query(Dataset).filter(
                Dataset.id == int(dataset_id),
                Dataset.user_id == int(user_id)
            ).first()
        else:
            dataset = db.query(Dataset).filter(
                Dataset.user_id == int(user_id)
            ).order_by(Dataset.id.desc()).first()

        if not dataset:
            return JSONResponse(status_code=404, content={"error": "No dataset found in catalog"})

        print(f"DEBUG: Starting final_train for experiment {experiment_id_raw}, algorithm {experiment.algorithm}, target {target_column}")

        # 2. Load data from S3
        df = load_dataset_as_dataframe(dataset.s3_bucket, dataset.s3_key)

        # Basic cleanup
        df = df.dropna()
        if df.empty:
            return JSONResponse(status_code=400, content={"error": "Dataset is empty after dropping missing values."})

        # 3. Split features / target
        if is_clustering:
            X = df
        else:
            if target_column not in df.columns:
                return JSONResponse(status_code=400, content={"error": f"Target column '{target_column}' not found in dataset columns: {df.columns.tolist()}"})
            X = df.drop(columns=[target_column])
            y = df[target_column]
            if model_info["task"] == "classification" and (y.dtype == 'object' or y.dtype.name == 'category'):
                le = LabelEncoder()
                y = le.fit_transform(y)

        # 4. Prepare S3 metadata
        from app.services.s3_operations import get_s3_client
        s3 = get_s3_client()
        bucket_name = os.getenv("S3_BUCKET_NAME")
        if not bucket_name:
            return JSONResponse(status_code=500, content={"error": "S3_BUCKET_NAME not configured"})

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        model_filename = f"model_{experiment.algorithm}_{timestamp}.joblib"
        model_s3_key = f"{user_id}/models/{model_filename}"

        # 5. Build preprocessing pipeline
        numeric_features = X.select_dtypes(include=['int64', 'float64']).columns.tolist()
        categorical_features = X.select_dtypes(include=['object', 'category']).columns.tolist()

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
            ],
            sparse_threshold=0.0 if is_clustering else 0.3
        )

        # 6. Build full pipeline
        hyperparams = json.loads(experiment.hyperparameters) if experiment.hyperparameters else {}
        model_instance = create_model_instance(experiment.algorithm, hyperparams)

        pipeline = Pipeline(steps=[
            ('preprocessor', preprocessor),
            ('model', model_instance)
        ])

        # 7. Train
        if is_clustering:
            X_train, X_test = train_test_split(X, test_size=0.2, random_state=42)
            print(f"DEBUG: Fitting clustering pipeline for {experiment.algorithm}...")
            pipeline.fit(X_train)
        else:
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            print(f"DEBUG: Fitting supervised pipeline for {experiment.algorithm}...")
            pipeline.fit(X_train, y_train)

        # 8. Save pipeline to S3
        print(f"DEBUG: Saving pipeline to S3...")
        pipeline_buffer = BytesIO()
        joblib.dump(pipeline, pipeline_buffer)
        pipeline_buffer.seek(0)
        s3.put_object(Bucket=bucket_name, Key=model_s3_key, Body=pipeline_buffer.getvalue())

        experiment.model_artifact_path = model_s3_key
        experiment.name = model_filename

        # 9. Evaluate and build result payload
        results = {}
        comparison = []

        if is_clustering:
            labels = pipeline.predict(X_test)
            X_test_transformed = pipeline.named_steps['preprocessor'].transform(X_test)

            sil = silhouette_score(X_test_transformed, labels)
            ch = calinski_harabasz_score(X_test_transformed, labels)
            db_score = davies_bouldin_score(X_test_transformed, labels)
            inertia = float(pipeline.named_steps['model'].inertia_)

            results["metrics"] = {
                "silhouette_score": round(sil, 4),
                "calinski_harabasz": round(ch, 4),
                "davies_bouldin": round(db_score, 4),
                "inertia": round(inertia, 2),
                "n_clusters": int(pipeline.named_steps['model'].n_clusters)
            }

            # Cluster size distribution for bar chart
            unique, counts = np.unique(labels, return_counts=True)
            comparison = [{"cluster": int(c), "count": int(n)} for c, n in zip(unique, counts)]

        else:
            predictions = pipeline.predict(X_test)

            if model_info["task"] == "regression":
                r2 = r2_score(y_test, predictions)
                n  = len(y_test)
                p  = pipeline.named_steps['preprocessor'].transform(X_test).shape[1]
                adj_r2 = 1 - (1 - r2) * (n - 1) / (n - p - 1) if n > p + 1 else r2
                residuals = np.array(y_test, dtype=float) - np.array(predictions, dtype=float)

                metrics_dict = {
                    "r2_score":              round(r2, 4),
                    "adjusted_r2":           round(adj_r2, 4),
                    "mae":                   round(float(mean_absolute_error(y_test, predictions)), 4),
                    "mse":                   round(float(mean_squared_error(y_test, predictions)), 4),
                    "rmse":                  round(float(np.sqrt(mean_squared_error(y_test, predictions))), 4),
                    "median_absolute_error": round(float(median_absolute_error(y_test, predictions)), 4),
                    "max_error":             round(float(max_error(y_test, predictions)), 4),
                    "explained_variance":    round(float(explained_variance_score(y_test, predictions)), 4),
                    "residual_mean":         round(float(residuals.mean()), 4),
                    "residual_std":          round(float(residuals.std()), 4),
                }
                try:
                    from sklearn.metrics import mean_absolute_percentage_error
                    metrics_dict["mape"] = round(float(mean_absolute_percentage_error(y_test, predictions) * 100), 4)
                except Exception: pass
                try:
                    metrics_dict["pearson_correlation"] = round(float(np.corrcoef(
                        np.array(y_test, dtype=float), np.array(predictions, dtype=float))[0, 1]), 4)
                except Exception: pass
                model_step = pipeline.named_steps['model']
                try:
                    if hasattr(model_step, 'support_vectors_'):
                        metrics_dict['n_support_vectors'] = int(model_step.support_vectors_.shape[0])
                except Exception: pass
                try:
                    if experiment.algorithm == 'Lasso' and hasattr(model_step, 'coef_'):
                        metrics_dict['non_zero_coefficients'] = int(np.count_nonzero(model_step.coef_))
                except Exception: pass

                results["metrics"] = metrics_dict

            else:  # classification
                cm = confusion_matrix(y_test, predictions)
                is_binary = len(np.unique(y_test)) == 2

                metrics_dict = {
                    "accuracy":    round(float(accuracy_score(y_test, predictions)), 4),
                    "precision":   round(float(precision_score(y_test, predictions, average='weighted', zero_division=0)), 4),
                    "recall":      round(float(recall_score(y_test, predictions, average='weighted', zero_division=0)), 4),
                    "f1_score":    round(float(f1_score(y_test, predictions, average='weighted')), 4),
                    "f2_score":    round(float(fbeta_score(y_test, predictions, beta=2, average='weighted', zero_division=0)), 4),
                    "f0_5_score":  round(float(fbeta_score(y_test, predictions, beta=0.5, average='weighted', zero_division=0)), 4),
                    "cohen_kappa": round(float(cohen_kappa_score(y_test, predictions)), 4),
                    "mcc":         round(float(matthews_corrcoef(y_test, predictions)), 4),
                    "confusion_matrix": cm.tolist(),
                }
                if is_binary:
                    tn, fp, fn, tp = cm.ravel()
                    metrics_dict['specificity']               = round(tn / (tn + fp), 4) if (tn + fp) else 0.0
                    metrics_dict['false_positive_rate']       = round(fp / (fp + tn), 4) if (fp + tn) else 0.0
                    metrics_dict['false_negative_rate']       = round(fn / (fn + tp), 4) if (fn + tp) else 0.0
                    metrics_dict['false_discovery_rate']      = round(fp / (fp + tp), 4) if (fp + tp) else 0.0
                    metrics_dict['negative_predictive_value'] = round(tn / (tn + fn), 4) if (tn + fn) else 0.0
                if hasattr(pipeline, 'predict_proba'):
                    try:
                        proba = pipeline.predict_proba(X_test)
                        if is_binary:
                            metrics_dict['roc_auc']     = round(float(roc_auc_score(y_test, proba[:, 1])), 4)
                            metrics_dict['brier_score'] = round(float(brier_score_loss(y_test, proba[:, 1])), 4)
                        else:
                            metrics_dict['roc_auc']     = round(float(roc_auc_score(y_test, proba, multi_class='ovr', average='weighted')), 4)
                        metrics_dict['log_loss_val'] = round(float(log_loss(y_test, proba)), 4)
                    except Exception: pass
                model_step = pipeline.named_steps['model']
                try:
                    if hasattr(model_step, 'n_support_'):
                        metrics_dict['n_support_vectors'] = int(np.sum(model_step.n_support_))
                except Exception: pass
                try:
                    if hasattr(model_step, 'get_depth'):
                        metrics_dict['tree_depth'] = int(model_step.get_depth())
                except Exception: pass
                try:
                    if hasattr(model_step, 'n_estimators'):
                        metrics_dict['n_estimators'] = int(model_step.n_estimators)
                except Exception: pass

                results["metrics"] = metrics_dict

            for actual, pred in zip(y_test[:10], predictions[:10]):
                comparison.append({
                    "actual": float(actual) if hasattr(actual, "__float__") else actual,
                    "predicted": float(pred) if hasattr(pred, "__float__") else pred
                })

        # 10. Save to database
        experiment.metrics = json.dumps(results["metrics"])
        experiment.status = "COMPLETED"
        experiment.target_column = target_column  # None for clustering
        db.commit()

        print(f"DEBUG: Training complete. Metrics: {results['metrics']}")
        return {
            "status": "trained_pending_save",
            "metrics": results["metrics"],
            "comparison": comparison,
            "model_task": model_info["task"]
        }
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/suggest_algorithm")
def suggest_algorithm_page(request: Request, db: Session = Depends(get_db), dataset_id: int = None):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login")
    
    # Fetch user for navbar profile
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    
    return templates.TemplateResponse("algorithm_suggestion_form.html", {
        "request": request,
        "username": user.username if user else None,
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

    # Fetch user for navbar profile
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    
    return templates.TemplateResponse("algorithm_suggestion_results.html", {
        "request": request,
        "username": user.username if user else None,
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