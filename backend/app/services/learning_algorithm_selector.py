def recommend_algorithms(
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

    recommendations = []

    if problem_type == "regression":

        if need_interpretability:
            if linearity == "linear":
                recommendations = ["Linear Regression", "Ridge (L2)", "Lasso (L1)"]
            else:
                recommendations = ["Decision Tree", "Ridge (L2)", "Lasso (L1)"]

        else:
            if dataset_size == "small":
                recommendations = ["KNN Regressor", "SVR", "Decision Tree"]
            else:
                if noise_level == "high":
                    recommendations = ["Random Forest", "SVR", "Ridge (L2)"]
                else:
                    recommendations = ["Random Forest", "Decision Tree", "SVR"]

        # Feature dimensionality tweak
        if n_features == "high":
            recommendations.insert(0, "Ridge (L2)")

    # ===============================
    # 2. CLASSIFICATION LOGIC
    # ===============================

    elif problem_type == "classification":

        if need_interpretability:
            if feature_type == "numerical":
                recommendations = ["Logistic Regression", "Decision Tree", "SVC"]
            else:
                recommendations = ["Decision Tree", "Logistic Regression", "KNN Classifier"]

        else:
            if dataset_size == "small":
                recommendations = ["KNN Classifier", "SVC", "Decision Tree"]
            else:
                if noise_level == "high":
                    recommendations = ["Random Forest", "SVC", "KNN Classifier"]
                else:
                    recommendations = ["Random Forest", "SVC", "Decision Tree"]

        # Handle imbalance
        if class_balance == "imbalanced":
            recommendations.insert(0, "Random Forest")

        # Linearity preference
        if linearity == "linear":
            recommendations.insert(0, "Logistic Regression")

    # ===============================
    # 3. CLUSTERING LOGIC
    # ===============================

    elif problem_type == "clustering":

        if dataset_size == "small":
            recommendations = ["KMeans Clustering", "KNN Classifier", "Decision Tree"]
        else:
            if noise_level == "high":
                recommendations = ["KMeans Clustering", "Random Forest", "Decision Tree"]
            else:
                recommendations = ["KMeans Clustering", "KNN Classifier", "SVC"]

    # ===============================
    # 4. SPEED CONSTRAINT ADJUSTMENT
    # ===============================

    if speed_requirement == "fast":
        # Prefer simpler models
        fast_models = [
            "Linear Regression", "Logistic Regression",
            "Decision Tree", "KNN Classifier", "KNN Regressor"
        ]
        recommendations = sorted(
            recommendations,
            key=lambda x: x not in fast_models
        )

    # ===============================
    # 5. REMOVE DUPLICATES & RETURN TOP 3
    # ===============================

    # Preserve order while removing duplicates
    seen = set()
    final_recommendations = []
    for algo in recommendations:
        if algo not in seen:
            final_recommendations.append(algo)
            seen.add(algo)

    return final_recommendations[:3]