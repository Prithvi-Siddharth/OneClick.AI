import importlib
from app.services.constants import ML_HYPERPARAMETERS

def cast_hyperparameters(model_name: str, params: dict) -> dict:
    """Casts string hyperparameter values to their correct types (bool, int, float) based on metadata."""
    model_config = ML_HYPERPARAMETERS.get(model_name)
    if not model_config:
        return params
    
    meta = model_config.get("hyperparameters", {})
    casted_params = {}

    for key, value in params.items():
        if key not in meta:
            casted_params[key] = value
            continue
        
        expected_type = meta[key].get("type")
        
        # Handle "None" strings
        if value == "None" or value is None:
            casted_params[key] = None
            continue

        try:
            if expected_type == "bool":
                if isinstance(value, str):
                    casted_params[key] = value.lower() in ("true", "1", "yes")
                else:
                    casted_params[key] = bool(value)
            elif expected_type == "int":
                casted_params[key] = int(value)
            elif expected_type == "float":
                casted_params[key] = float(value)
            else:
                casted_params[key] = value
        except (ValueError, TypeError):
            print(f"WARNING: Failed to cast {key}={value} to {expected_type}. Using raw value.")
            casted_params[key] = value
            
    return casted_params

def create_model_instance(model_name: str, hyperparameters: dict):
    model_config = ML_HYPERPARAMETERS.get(model_name)
    if not model_config:
        raise ValueError(f"Model '{model_name}' is not supported.")

    # Cast hyperparameters to correct types before instantiation
    casted_params = cast_hyperparameters(model_name, hyperparameters)

    class_path = model_config["model_class"]
    module_path, class_name = class_path.rsplit(".", 1)

    module = importlib.import_module(module_path)
    model_class = getattr(module, class_name)

    model_instance = model_class(**casted_params)

    return model_instance

def get_base_model(model_name: str):
    """Returns an unfitted model instance with default parameters, for use as the estimator in GridSearchCV."""
    model_config = ML_HYPERPARAMETERS.get(model_name)
    if not model_config:
        raise ValueError(f"Model '{model_name}' is not supported.")

    class_path = model_config["model_class"]
    module_path, class_name = class_path.rsplit(".", 1)

    module = importlib.import_module(module_path)
    model_class = getattr(module, class_name)

    # Return with no args — GridSearchCV will set params via param_grid
    return model_class()

from sklearn import metrics

def get_model_stats(task_type: str, y_true, y_pred):
    if task_type == "regression":
        return {
            "R2 Score": metrics.r2_score(y_true, y_pred),
            "MAE": metrics.mean_absolute_error(y_true, y_pred),
            "MSE": metrics.mean_squared_error(y_true, y_pred)
        }
    else:
        return {
            "Accuracy": metrics.accuracy_score(y_true, y_pred),
            "F1 Score": metrics.f1_score(y_true, y_pred, average='weighted'),
            "Precision": metrics.precision_score(y_true, y_pred, average='weighted')
        }
