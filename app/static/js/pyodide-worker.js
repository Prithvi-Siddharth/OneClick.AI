// Pyodide WebAssembly Worker for Client-Side Machine Learning
// OneClick.AI - Local-First Compute Engine

importScripts("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js");

let pyodide = null;
let isReady = false;

// Initialize Pyodide and load foundational data science libraries
async function initPyodideWorker() {
    try {
        self.postMessage({ type: "STATUS", message: "Initializing Pyodide WebAssembly environment..." });
        
        pyodide = await loadPyodide({
            indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"
        });
        
        self.postMessage({ type: "STATUS", message: "Loading NumPy, Pandas, and Scikit-Learn into WebAssembly..." });
        await pyodide.loadPackage(["numpy", "pandas", "scikit-learn"]);
        
        // Define Python helper scripts in memory
        await pyodide.runPythonAsync(`
import json
import pandas as pd
import numpy as np
import io
import traceback
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler, MinMaxScaler
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.svm import SVC, SVR
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.cluster import KMeans
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    r2_score, mean_absolute_error, mean_squared_error,
    silhouette_score
)

print("OneClick.AI Python WebAssembly Engine Initialized Successfully")
        `);

        isReady = true;
        self.postMessage({ type: "READY", message: "Client compute engine initialized and ready." });
    } catch (err) {
        console.error("Pyodide init error:", err);
        self.postMessage({ type: "ERROR", error: "Failed to initialize Pyodide: " + err.toString() });
    }
}

// Execute in-browser model training
async function runTraining(payload) {
    const { csvData, targetColumn, algorithm, hyperparameters = {}, task = "classification" } = payload;

    if (!isReady) {
        throw new Error("Pyodide engine is still loading. Please wait.");
    }

    self.postMessage({ type: "PROGRESS", step: "Preparing dataset in browser memory...", percent: 20 });

    pyodide.globals.set("raw_csv_data", csvData);
    pyodide.globals.set("target_col", targetColumn);
    pyodide.globals.set("algo_name", algorithm);
    pyodide.globals.set("hparams_json", JSON.stringify(hyperparameters));
    pyodide.globals.set("task_type", task);

    self.postMessage({ type: "PROGRESS", step: "Preprocessing features & splitting train/test...", percent: 40 });

    const trainingScript = `
def execute_client_train():
    try:
        df = pd.read_csv(io.StringIO(raw_csv_data))
        df = df.dropna()
        hparams = json.loads(hparams_json)
        
        is_clustering = (task_type == "clustering")
        
        if is_clustering:
            X = pd.get_dummies(df, drop_first=True)
            y = None
        else:
            if target_col not in df.columns:
                return json.dumps({"error": f"Target column '{target_col}' not found"})
            X = df.drop(columns=[target_col])
            y = df[target_col]
            X = pd.get_dummies(X, drop_first=True)
            
            # Encode categorical target for classification
            if task_type == "classification" and (y.dtype == 'object' or y.dtype.name == 'category'):
                le = LabelEncoder()
                y = le.fit_transform(y)

        # Algorithm map
        algo_map = {
            "Decision Tree": (DecisionTreeClassifier if task_type == "classification" else DecisionTreeRegressor),
            "Random Forest": (RandomForestClassifier if task_type == "classification" else RandomForestRegressor),
            "SVM": (SVC if task_type == "classification" else SVR),
            "K-Nearest Neighbors": (KNeighborsClassifier if task_type == "classification" else KNeighborsRegressor),
            "Logistic/Linear Regression": (LogisticRegression if task_type == "classification" else LinearRegression),
            "KMeans": KMeans
        }
        
        # Instantiate model
        model_cls = algo_map.get(algo_name)
        if not model_cls:
            # Fallback by substring match
            for k, cls in algo_map.items():
                if k.lower() in algo_name.lower():
                    model_cls = cls
                    break
        
        if not model_cls:
            model_cls = DecisionTreeClassifier if task_type == "classification" else DecisionTreeRegressor
            
        # Clean hyperparameters
        cleaned_params = {}
        for k, v in hparams.items():
            if v is not None and v != "":
                if isinstance(v, str):
                    try:
                        cleaned_params[k] = int(v) if '.' not in v else float(v)
                    except ValueError:
                        cleaned_params[k] = v
                else:
                    cleaned_params[k] = v
                    
        # Apply model
        model = model_cls(**cleaned_params)
        
        metrics = {}
        comparison = []
        
        if is_clustering:
            model.fit(X)
            labels = model.labels_
            if len(set(labels)) > 1:
                metrics["silhouette_score"] = round(float(silhouette_score(X, labels)), 4)
            metrics["n_clusters"] = int(len(set(labels)))
            # Cluster counts
            unique, counts = np.unique(labels, return_counts=True)
            comparison = [{"cluster": int(u), "count": int(c)} for u, c in zip(unique, counts)]
        else:
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            
            if task_type == "classification":
                metrics["accuracy"] = round(float(accuracy_score(y_test, y_pred)), 4)
                metrics["precision"] = round(float(precision_score(y_test, y_pred, average="weighted", zero_division=0)), 4)
                metrics["recall"] = round(float(recall_score(y_test, y_pred, average="weighted", zero_division=0)), 4)
                metrics["f1_score"] = round(float(f1_score(y_test, y_pred, average="weighted", zero_division=0)), 4)
            else:
                metrics["r2_score"] = round(float(r2_score(y_test, y_pred)), 4)
                metrics["mae"] = round(float(mean_absolute_error(y_test, y_pred)), 4)
                metrics["rmse"] = round(float(np.sqrt(mean_squared_error(y_test, y_pred))), 4)
                
            # Sample comparison (up to 50 items for UI chart)
            sample_len = min(50, len(y_test))
            y_test_arr = np.array(y_test)[:sample_len]
            y_pred_arr = np.array(y_pred)[:sample_len]
            for act, pred in zip(y_test_arr, y_pred_arr):
                comparison.append({
                    "actual": float(act) if isinstance(act, (int, float, np.number)) else str(act),
                    "predicted": float(pred) if isinstance(pred, (int, float, np.number)) else str(pred)
                })

        return json.dumps({
            "status": "success",
            "metrics": metrics,
            "comparison": comparison,
            "model_task": task_type,
            "row_count": len(df),
            "features_used": list(X.columns)
        })
    except Exception as e:
        traceback.print_exc()
        return json.dumps({"error": str(e)})

execute_client_train()
`;

    self.postMessage({ type: "PROGRESS", step: `Training ${algorithm} on client CPU...`, percent: 75 });
    const resultJson = await pyodide.runPythonAsync(trainingScript);
    const result = JSON.parse(resultJson);

    if (result.error) {
        throw new Error(result.error);
    }

    self.postMessage({ type: "TRAIN_COMPLETE", result: result });
}

// In-browser EDA & summary calculation
async function runAutoEDA(csvData) {
    if (!isReady) throw new Error("Pyodide engine is still loading.");

    pyodide.globals.set("eda_csv_data", csvData);
    const edaScript = `
def execute_client_eda():
    df = pd.read_csv(io.StringIO(eda_csv_data))
    stats = {}
    for col in df.select_dtypes(include=[np.number]).columns:
        series = df[col].dropna()
        stats[col] = {
            "mean": round(float(series.mean()), 2),
            "median": round(float(series.median()), 2),
            "std": round(float(series.std()), 2),
            "min": round(float(series.min()), 2),
            "max": round(float(series.max()), 2),
            "nulls": int(df[col].isnull().sum())
        }
    return json.dumps(stats)

execute_client_eda()
`;
    const res = await pyodide.runPythonAsync(edaScript);
    self.postMessage({ type: "EDA_COMPLETE", stats: JSON.parse(res) });
}

// Worker message listener
self.onmessage = async function(event) {
    const { action, payload } = event.data;
    try {
        switch (action) {
            case "INIT":
                if (!isReady) await initPyodideWorker();
                break;
            case "TRAIN":
                await runTraining(payload);
                break;
            case "EDA":
                await runAutoEDA(payload);
                break;
            default:
                console.warn("Unknown worker action:", action);
        }
    } catch (err) {
        self.postMessage({ type: "ERROR", error: err.message || err.toString() });
    }
};

// Start initialization immediately
initPyodideWorker();
