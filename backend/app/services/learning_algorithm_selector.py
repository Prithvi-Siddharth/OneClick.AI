def recommend_algorithms_scoring(
    problem_type="classification",
    dataset_size="medium",
    feature_type="numerical",
    noise_level="medium",
    need_interpretability=False,
    linearity="unknown",
    class_balance="balanced",
    speed_requirement="moderate",
    n_features="medium"
):
    """
    Recommends top 3 machine learning algorithms based on user inputs.

    Parameters:
    ----------
    problem_type : str
        "classification", "regression", "clustering"

    dataset_size : str
        "small", "medium", "large"

    feature_type : str
        "numerical", "categorical", "mixed"

    noise_level : str
        "low", "medium", "high"

    need_interpretability : bool
        True / False

    linearity : str
        "linear", "non-linear", "unknown"

    class_balance : str
        "balanced", "imbalanced" (only for classification)

    speed_requirement : str
        "fast", "moderate", "no_constraint"

    n_features : str
        "low", "medium", "high"

    Returns:
    -------
    list
        Top 3 recommended algorithms
    """


    # ===============================
    # 1. Initialize Scores
    # ===============================

    scores = {
        # Regression
        "Linear Regression": 0,
        "Ridge (L2)": 0,
        "Lasso (L1)": 0,
        "SVR": 0,
        "KNN Regressor": 0,

        # Classification
        "Logistic Regression": 0,
        "SVC": 0,
        "KNN Classifier": 0,

        # General / Tree-based
        "Decision Tree": 0,
        "Random Forest": 0,

        # Clustering
        "KMeans Clustering": 0
    }

    # ===============================
    # 2. Problem Type Weighting
    # ===============================

    if problem_type == "regression":
        for algo in ["Linear Regression", "Ridge (L2)", "Lasso (L1)", "SVR", "KNN Regressor", "Decision Tree", "Random Forest"]:
            scores[algo] += 3

    elif problem_type == "classification":
        for algo in ["Logistic Regression", "SVC", "KNN Classifier", "Decision Tree", "Random Forest"]:
            scores[algo] += 3

    elif problem_type == "clustering":
        scores["KMeans Clustering"] += 5

    # ===============================
    # 3. Linearity
    # ===============================

    if linearity == "linear":
        scores["Linear Regression"] += 3
        scores["Logistic Regression"] += 3
        scores["Ridge (L2)"] += 2
        scores["Lasso (L1)"] += 2

    elif linearity == "non-linear":
        scores["Random Forest"] += 3
        scores["Decision Tree"] += 2
        scores["SVC"] += 2
        scores["KNN Classifier"] += 1
        scores["KNN Regressor"] += 1

    # ===============================
    # 4. Dataset Size
    # ===============================

    if dataset_size == "small":
        scores["KNN Classifier"] += 3
        scores["KNN Regressor"] += 3
        scores["SVC"] += 2

    elif dataset_size == "large":
        scores["Random Forest"] += 3
        scores["Ridge (L2)"] += 2
        scores["Lasso (L1)"] += 2

    # ===============================
    # 5. Noise Handling
    # ===============================

    if noise_level == "high":
        scores["Random Forest"] += 4
        scores["Ridge (L2)"] += 2
        scores["Lasso (L1)"] += 2

    elif noise_level == "low":
        scores["Linear Regression"] += 2
        scores["Logistic Regression"] += 2

    # ===============================
    # 6. Interpretability
    # ===============================

    if need_interpretability:
        scores["Linear Regression"] += 3
        scores["Logistic Regression"] += 3
        scores["Decision Tree"] += 3

    # ===============================
    # 7. Feature Type
    # ===============================

    if feature_type == "mixed":
        scores["Decision Tree"] += 2
        scores["Random Forest"] += 2
        scores["KNN Classifier"] += 1

    # ===============================
    # 8. Class Imbalance
    # ===============================

    if class_balance == "imbalanced":
        scores["Random Forest"] += 3
        scores["SVC"] += 2

    # ===============================
    # 9. Speed Constraint
    # ===============================

    if speed_requirement == "fast":
        scores["Linear Regression"] += 2
        scores["Logistic Regression"] += 2
        scores["Decision Tree"] += 2

    # ===============================
    # 10. High Dimensional Data
    # ===============================

    if n_features == "high":
        scores["Ridge (L2)"] += 3
        scores["Lasso (L1)"] += 3
        scores["SVC"] += 2

    # ===============================
    # 11. Sort & Return Top 3
    # ===============================

    sorted_algos = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    top_algorithms = [algo for algo, score in sorted_algos if score > 0]

    # Fallback safety
    if len(top_algorithms) < 3:
        return ["Random Forest", "SVC", "Decision Tree"]

    return top_algorithms[:3]


# result = recommend_algorithms_scoring(
#     problem_type="classification",
#     dataset_size="large",
#     noise_level="high",
#     linearity="non-linear",
#     class_balance="imbalanced"
# )

# print(result)


