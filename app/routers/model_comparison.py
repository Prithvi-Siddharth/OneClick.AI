from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
import pandas as pd
import numpy as np
import json
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
try:
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import LabelEncoder, StandardScaler
    from sklearn.impute import SimpleImputer
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.svm import SVC
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_curve, auc
except ImportError:
    pass
import time

from app.db import get_db
from app.models import Dataset, User
from app.security import get_current_user_id
from app.services.s3_operations import load_dataset_as_dataframe

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))

def train_and_evaluate(name, model, X_train, y_train, X_test, y_test):
    """
    Worker function to train a model and return metrics + ROC data.
    """
    try:
        start_time = time.time()
        model.fit(X_train, y_train)
        training_time = time.time() - start_time
        
        y_pred = model.predict(X_test)
        y_probs = None
        if hasattr(model, "predict_proba"):
            y_probs = model.predict_proba(X_test)[:, 1]
        
        metrics = {
            "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
            "precision": round(float(precision_score(y_test, y_pred, average='weighted', zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, y_pred, average='weighted', zero_division=0)), 4),
            "f1": round(float(f1_score(y_test, y_pred, average='weighted', zero_division=0)), 4),
            "training_time": round(float(training_time), 4)
        }
        
        roc_data = None
        if y_probs is not None:
            # For multi-class, simple binary ROC on class 1 or averaged is complex for this "fast" tool
            # For now, if binary, compute ROC. If multi-class, compute simple accuracy-based radar.
            if len(np.unique(y_test)) == 2:
                fpr, tpr, _ = roc_curve(y_test, y_probs)
                roc_auc = auc(fpr, tpr)
                roc_data = {
                    "fpr": fpr.tolist(),
                    "tpr": tpr.tolist(),
                    "auc": round(float(roc_auc), 4)
                }
            
        return {
            "name": name,
            "metrics": metrics,
            "roc": roc_data
        }
    except Exception as e:
        print(f"Error training {name}: {str(e)}")
        return {
            "name": name,
            "error": str(e)
        }

@router.get("/model_comparison/{dataset_id}", response_class=HTMLResponse)
def model_comparison_page(dataset_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return templates.TemplateResponse("login.html", {"request": request})
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.user_id == int(user_id)).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
        
    return templates.TemplateResponse("model_comparison.html", {
        "request": request,
        "username": user.username,
        "dataset": dataset
    })

@router.get("/api/compare-models/{dataset_id}")
async def api_compare_models(dataset_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.user_id == int(user_id)).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
        
    try:
        # 1. Load Data
        df = load_dataset_as_dataframe(dataset.s3_bucket, dataset.s3_key)
        
        # 2. Sampling (Max 10,000 for speed)
        if len(df) > 10000:
            df = df.sample(n=10000, random_state=42)
            
        # 3. Simple Preprocessing
        # Target is the last column
        target_col = df.columns[-1]
        X = df.drop(columns=[target_col])
        y = df[target_col]
        
        # Handle Target Encoding
        le = LabelEncoder()
        y = le.fit_transform(y.astype(str))
            
        # Feature Engineering (Basic)
        # Drop columns with too many NaNs
        X = X.dropna(axis=1, thresh=len(X) * 0.5)
        
        # Impute and Encode
        num_cols = X.select_dtypes(include=['int64', 'float64']).columns
        cat_cols = X.select_dtypes(include=['object', 'category']).columns
        
        X_processed = pd.DataFrame(index=X.index)
        
        if len(num_cols) > 0:
            num_imputer = SimpleImputer(strategy='median')
            X_processed[num_cols] = num_imputer.fit_transform(X[num_cols])
            scaler = StandardScaler()
            X_processed[num_cols] = scaler.fit_transform(X_processed[num_cols])
            
        if len(cat_cols) > 0:
            for col in cat_cols:
                # Simple label encoding for speed
                X_processed[col] = LabelEncoder().fit_transform(X[col].astype(str))
        
        X_train, X_test, y_train, y_test = train_test_split(X_processed, y, test_size=0.2, random_state=42)
        
        # 4. Parallel Training
        models = {
            "Logistic Regression": LogisticRegression(max_iter=1000, random_state=42),
            "Decision Tree": DecisionTreeClassifier(max_depth=10, random_state=42),
            "Random Forest": RandomForestClassifier(n_estimators=50, max_depth=10, random_state=42),
            "KNN Classifier": KNeighborsClassifier(n_neighbors=5),
            "SVC": SVC(probability=True, random_state=42)
        }
        
        results = []
        # Use ProcessPoolExecutor for parallel training outside the main thread
        with ProcessPoolExecutor(max_workers=min(len(models), os.cpu_count() or 1)) as executor:
            futures = [
                executor.submit(train_and_evaluate, name, model, X_train, y_train, X_test, y_test)
                for name, model in models.items()
            ]
            for future in futures:
                results.append(future.result())
                
        return JSONResponse(content={
            "success": True,
            "results": results,
            "dataset_name": dataset.filename
        })
        
    except Exception as e:
        print(f"Error in model comparison: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )
