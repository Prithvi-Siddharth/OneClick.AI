ML_HYPERPARAMETERS = {
    "LinearRegression": {
        "model_class": "sklearn.linear_model.LinearRegression",
        "task": "regression",
        "hyperparameters": {
            "fit_intercept": {
                "type": "bool",
                "default": True,
                "options": [True, False],
                "description": "Whether to calculate intercept"
            },
            "normalize": {
                "type": "bool",
                "default": False,
                "options": [True, False],
                "description": "Normalize features before fitting"
            },
            "copy_X": {
                "type": "bool",
                "default": True,
                "options": [True, False],
                "description": "Copy or overwrite X"
            },
            "n_jobs": {
                "type": "int",
                "default": None,
                "range": [-1, 1, 2, 4, 8],
                "description": "Parallel jobs for computation"
            },
            "positive": {
                "type": "bool",
                "default": False,
                "options": [True, False],
                "description": "Force coefficients to be positive"
            }
        },
        "grid_search_params": {
            "fit_intercept": [True, False],
            "positive": [True, False]
        }
    },

    "LogisticRegression": {
        "model_class": "sklearn.linear_model.LogisticRegression",
        "task": "classification",
        "hyperparameters": {
            "C": {
                "type": "float",
                "default": 1.0,
                "range": [0.01, 0.1, 1.0, 10.0, 100.0],
                "description": "Inverse regularization strength"
            },
            "penalty": {
                "type": "str",
                "default": "l2",
                "options": ["l1", "l2", "elasticnet", "none"],
                "description": "Type of regularization"
            },
            "solver": {
                "type": "str",
                "default": "lbfgs",
                "options": ["lbfgs", "liblinear", "saga", "newton-cg", "sag"],
                "description": "Optimization algorithm"
            },
            "max_iter": {
                "type": "int",
                "default": 100,
                "range": [100, 500, 1000, 5000, 10000],
                "description": "Max iterations for convergence"
            },
            "multi_class": {
                "type": "str",
                "default": "auto",
                "options": ["auto", "ovr", "multinomial"],
                "description": "Multi-class strategy"
            }
        },
        # LogisticRegression: penalty and solver have compatibility constraints.
        # l1  -> only liblinear, saga
        # l2  -> lbfgs, liblinear, newton-cg, sag, saga
        # elasticnet -> only saga (also needs l1_ratio)
        # Using a list of param dicts avoids invalid combinations that cause sklearn errors.
        "grid_search_params": [
            {"C": [0.01, 0.1, 1.0, 10.0, 100.0], "penalty": ["l2"],         "solver": ["lbfgs", "liblinear", "newton-cg", "sag"], "max_iter": [100, 500]},
            {"C": [0.01, 0.1, 1.0, 10.0, 100.0], "penalty": ["l1"],         "solver": ["liblinear", "saga"],                      "max_iter": [100, 500]},
            {"C": [0.01, 0.1, 1.0, 10.0, 100.0], "penalty": ["elasticnet"], "solver": ["saga"],                                   "max_iter": [100, 500], "l1_ratio": [0.25, 0.5, 0.75]}
        ]
    },

    "DecisionTree": {
        "model_class": "sklearn.tree.DecisionTreeClassifier",
        "task": "classification",
        "hyperparameters": {
            "max_depth": {
                "type": "int",
                "default": None,
                "range": [None, 2, 5, 10, 20, 50],
                "description": "Max depth of tree, controls overfitting"
            },
            "min_samples_split": {
                "type": "int",
                "default": 2,
                "range": [2, 5, 10, 20],
                "description": "Min samples required to split a node"
            },
            "min_samples_leaf": {
                "type": "int",
                "default": 1,
                "range": [1, 2, 5, 10, 20],
                "description": "Min samples required at a leaf node"
            },
            "max_features": {
                "type": "str",
                "default": None,
                "options": [None, "sqrt", "log2"],
                "description": "Features to consider for best split"
            },
            "criterion": {
                "type": "str",
                "default": "gini",
                "options": ["gini", "entropy", "log_loss"],
                "description": "Split quality measure"
            }
        },
        "grid_search_params": {
            "max_depth": [None, 5, 10, 20],
            "min_samples_split": [2, 5, 10],
            "min_samples_leaf": [1, 2, 5],
            "criterion": ["gini", "entropy"],
            "max_features": [None, "sqrt", "log2"]
        }
    },

    "RandomForest": {
        "model_class": "sklearn.ensemble.RandomForestClassifier",
        "task": "classification",
        "hyperparameters": {
            "n_estimators": {
                "type": "int",
                "default": 100,
                "range": [100, 200, 500, 1000, 2000],
                "description": "Number of trees"
            },
            "max_depth": {
                "type": "int",
                "default": None,
                "range": [None, 5, 10, 20, 50],
                "description": "Max depth of each tree"
            },
            "min_samples_split": {
                "type": "int",
                "default": 2,
                "range": [2, 5, 10, 20],
                "description": "Min samples to split a node"
            },
            "max_features": {
                "type": "str",
                "default": "sqrt",
                "options": ["sqrt", "log2", None],
                "description": "Features considered at each split"
            },
            "bootstrap": {
                "type": "bool",
                "default": True,
                "options": [True, False],
                "description": "Whether to use bootstrap samples"
            }
        },
        "grid_search_params": {
            "n_estimators": [50, 100, 200],
            "max_depth": [None, 5, 10],
            "min_samples_split": [2, 5, 10],
            "min_samples_leaf": [1, 2, 5],
            "max_features": ["sqrt", "log2"],
            "bootstrap": [True, False]
        }
    },

    "KNeighborsClassifier": {
        "model_class": "sklearn.neighbors.KNeighborsClassifier",
        "task": "classification",
        "hyperparameters": {
            "n_neighbors": {
                "type": "int",
                "default": 5,
                "range": [1, 3, 5, 10, 20, 50],
                "description": "Number of neighbors"
            },
            "weights": {
                "type": "str",
                "default": "uniform",
                "options": ["uniform", "distance"],
                "description": "Uniform or distance-weighted votes"
            },
            "metric": {
                "type": "str",
                "default": "minkowski",
                "options": ["euclidean", "manhattan", "minkowski", "chebyshev"],
                "description": "Distance calculation method"
            },
            "p": {
                "type": "int",
                "default": 2,
                "options": [1, 2],
                "description": "Power for Minkowski (1=manhattan, 2=euclidean)"
            },
            "algorithm": {
                "type": "str",
                "default": "auto",
                "options": ["auto", "ball_tree", "kd_tree", "brute"],
                "description": "Algorithm for nearest neighbor search"
            }
        },
        "grid_search_params": {
            "n_neighbors": [3, 5, 7, 11, 15],
            "weights": ["uniform", "distance"],
            "metric": ["euclidean", "manhattan", "minkowski"],
            "p": [1, 2],
            "algorithm": ["auto", "ball_tree", "kd_tree", "brute"]
        }
    },

    "KNeighborsRegressor": {
        "model_class": "sklearn.neighbors.KNeighborsRegressor",
        "task": "regression",
        "hyperparameters": {
            "n_neighbors": {
                "type": "int",
                "default": 5,
                "range": [1, 3, 5, 10, 20, 50],
                "description": "Number of neighbors"
            },
            "weights": {
                "type": "str",
                "default": "uniform",
                "options": ["uniform", "distance"],
                "description": "How neighbors are weighted in prediction"
            },
            "metric": {
                "type": "str",
                "default": "minkowski",
                "options": ["euclidean", "manhattan", "minkowski", "chebyshev"],
                "description": "Distance metric"
            },
            "p": {
                "type": "int",
                "default": 2,
                "options": [1, 2],
                "description": "Minkowski power parameter"
            },
            "leaf_size": {
                "type": "int",
                "default": 30,
                "range": [10, 20, 30, 50, 100],
                "description": "Affects speed of ball_tree/kd_tree"
            }
        },
        "grid_search_params": {
            "n_neighbors": [3, 5, 7, 11, 15],
            "weights": ["uniform", "distance"],
            "metric": ["euclidean", "manhattan", "minkowski"],
            "p": [1, 2],
            "leaf_size": [10, 20, 30, 50]
        }
    },

    "KMeans": {
        "model_class": "sklearn.cluster.KMeans",
        "task": "clustering",
        "hyperparameters": {
            "n_clusters": {
                "type": "int",
                "default": 8,
                "range": [2, 3, 5, 8, 10, 15, 20],
                "description": "Number of clusters"
            },
            "init": {
                "type": "str",
                "default": "k-means++",
                "options": ["k-means++", "random"],
                "description": "Centroid initialization strategy"
            },
            "max_iter": {
                "type": "int",
                "default": 300,
                "range": [100, 300, 500, 1000],
                "description": "Max iterations per single run"
            },
            "n_init": {
                "type": "int",
                "default": 10,
                "range": [10, 20, 30, 50],
                "description": "Number of times run with different seeds"
            },
            "tol": {
                "type": "float",
                "default": 1e-4,
                "range": [1e-4, 1e-3, 1e-2, 1e-1],
                "description": "Convergence tolerance"
            }
        }
    },

    "SVC": {
        "model_class": "sklearn.svm.SVC",
        "task": "classification",
        "hyperparameters": {
            "C": {
                "type": "float",
                "default": 1.0,
                "range": [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0],
                "description": "Regularization — higher = less regularization"
            },
            "kernel": {
                "type": "str",
                "default": "rbf",
                "options": ["rbf", "linear", "poly", "sigmoid"],
                "description": "Decision boundary shape"
            },
            "gamma": {
                "type": "str",
                "default": "scale",
                "options": ["scale", "auto", 0.001, 0.01, 0.1, 1.0],
                "description": "Kernel coefficient"
            },
            "degree": {
                "type": "int",
                "default": 3,
                "range": [2, 3, 4, 5],
                "description": "Degree for poly kernel only"
            },
            "class_weight": {
                "type": "str",
                "default": None,
                "options": [None, "balanced"],
                "description": "Handle class imbalance"
            }
        },
        # SVC: degree only matters for kernel="poly"; using a list of dicts
        # prevents wasting CV folds on degree when kernel != poly.
        "grid_search_params": [
            {"C": [0.1, 1.0, 10.0, 100.0], "kernel": ["rbf", "linear", "sigmoid"], "gamma": ["scale", "auto", 0.001, 0.01, 0.1], "class_weight": [None, "balanced"]},
            {"C": [0.1, 1.0, 10.0, 100.0], "kernel": ["poly"],                     "gamma": ["scale", "auto"],                      "class_weight": [None, "balanced"], "degree": [2, 3, 4]}
        ]
    },

    "SVR": {
        "model_class": "sklearn.svm.SVR",
        "task": "regression",
        "hyperparameters": {
            "C": {
                "type": "float",
                "default": 1.0,
                "range": [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0],
                "description": "Regularization strength"
            },
            "kernel": {
                "type": "str",
                "default": "rbf",
                "options": ["rbf", "linear", "poly", "sigmoid"],
                "description": "Kernel type"
            },
            "epsilon": {
                "type": "float",
                "default": 0.1,
                "range": [0.01, 0.05, 0.1, 0.5, 1.0],
                "description": "Margin of tolerance"
            },
            "gamma": {
                "type": "str",
                "default": "scale",
                "options": ["scale", "auto", 0.001, 0.01, 0.1, 1.0],
                "description": "Kernel coefficient"
            },
            "degree": {
                "type": "int",
                "default": 3,
                "range": [2, 3, 4, 5],
                "description": "Degree for poly kernel only"
            }
        },
        # SVR: same degree/poly split as SVC.
        "grid_search_params": [
            {"C": [0.1, 1.0, 10.0, 100.0], "kernel": ["rbf", "linear", "sigmoid"], "epsilon": [0.01, 0.1, 0.5], "gamma": ["scale", "auto"]},
            {"C": [0.1, 1.0, 10.0, 100.0], "kernel": ["poly"],                     "epsilon": [0.01, 0.1, 0.5], "gamma": ["scale", "auto"], "degree": [2, 3, 4]}
        ]
    },

    "Lasso": {
        "model_class": "sklearn.linear_model.Lasso",
        "task": "regression",
        "hyperparameters": {
            "alpha": {
                "type": "float",
                "default": 1.0,
                "range": [0.0001, 0.001, 0.01, 0.1, 1.0, 10.0, 100.0],
                "description": "Regularization strength — higher zeros more coefficients"
            },
            "max_iter": {
                "type": "int",
                "default": 1000,
                "range": [100, 500, 1000, 5000, 10000],
                "description": "Max iterations for convergence"
            },
            "tol": {
                "type": "float",
                "default": 1e-4,
                "range": [1e-6, 1e-4, 1e-3, 1e-2],
                "description": "Tolerance for convergence"
            },
            "fit_intercept": {
                "type": "bool",
                "default": True,
                "options": [True, False],
                "description": "Whether to fit intercept term"
            },
            "selection": {
                "type": "str",
                "default": "cyclic",
                "options": ["cyclic", "random"],
                "description": "Order of coefficient updates"
            }
        },
        "grid_search_params": {
            "alpha": [0.0001, 0.001, 0.01, 0.1, 1.0, 10.0],
            "max_iter": [1000, 5000, 10000],
            "tol": [1e-4, 1e-3, 1e-2],
            "fit_intercept": [True, False],
            "selection": ["cyclic", "random"]
        }
    },

    "Ridge": {
        "model_class": "sklearn.linear_model.Ridge",
        "task": "regression",
        "hyperparameters": {
            "alpha": {
                "type": "float",
                "default": 1.0,
                "range": [0.0001, 0.001, 0.01, 0.1, 1.0, 10.0, 100.0],
                "description": "Regularization strength — higher = stronger shrinkage"
            },
            "fit_intercept": {
                "type": "bool",
                "default": True,
                "options": [True, False],
                "description": "Whether to fit intercept term"
            },
            "solver": {
                "type": "str",
                "default": "auto",
                "options": ["auto", "svd", "cholesky", "lsqr", "saga", "sag"],
                "description": "Solver algorithm"
            },
            "max_iter": {
                "type": "int",
                "default": None,
                "range": [None, 100, 500, 1000, 5000, 10000],
                "description": "Max iterations for solvers that support it"
            },
            "tol": {
                "type": "float",
                "default": 1e-3,
                "range": [1e-6, 1e-4, 1e-3, 1e-2],
                "description": "Precision of solution"
            }
        },
        "grid_search_params": {
            "alpha": [0.0001, 0.001, 0.01, 0.1, 1.0, 10.0, 100.0],
            "fit_intercept": [True, False],
            "solver": ["auto", "svd", "cholesky", "lsqr"],
            "max_iter": [None, 100, 500, 1000],
            "tol": [1e-4, 1e-3, 1e-2]
        }
    }
}

def get_model_names():
    return list(ML_HYPERPARAMETERS.keys())

def get_models_by_task(task: str):
    return {k: v for k, v in ML_HYPERPARAMETERS.items() if v["task"] == task}

def get_hyperparameters(model_name: str):
    model = ML_HYPERPARAMETERS.get(model_name)
    if not model:
        raise ValueError(f"Model '{model_name}' not found.")
    return model["hyperparameters"]

def get_default_params(model_name: str):
    params = get_hyperparameters(model_name)
    return {k: v["default"] for k, v in params.items()}

def get_grid_search_params(model_name: str) -> dict:
    """Returns the param_grid dict for use with GridSearchCV."""
    model = ML_HYPERPARAMETERS.get(model_name)
    if not model:
        raise ValueError(f"Model '{model_name}' not found.")
    return model.get("grid_search_params", {})