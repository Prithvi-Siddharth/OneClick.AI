import importlib
from app.services.constants import ML_HYPERPARAMETERS

def create_model_instance(model_name: str, hyperparameters: dict):
    model_config = ML_HYPERPARAMETERS.get(model_name)
    if not model_config:
        raise ValueError(f"Model '{model_name}' is not supported.")

    class_path = model_config["model_class"]
    module_path, class_name = class_path.rsplit(".", 1)

    module = importlib.import_module(module_path)
    model_class = getattr(module, class_name)

    model_instance = model_class(**hyperparameters)

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
