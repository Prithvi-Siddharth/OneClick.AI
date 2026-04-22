ALGORITHM_DETAILS = {
    "LinearRegression": {
        "name": "Linear Regression",
        "icon": "fas fa-chart-line",
        "color": "#3498db",
        "overview": "Predicts continuous values based on linear relationships between independent and dependent variables.",
        "how_it_works": "It fits a straight line (the regression line) that minimizes the sum of squared errors between predicted and actual values. The goal is to find the best-fitting coefficients for each feature.",
        "mechanics": "The equation is y = β₀ + β₁x₁ + ... + βₙxₙ + ε, where β₀ is the intercept and βᵢ are coefficients.",
        "strengths": ["Interpretable", "Efficient to train", "Works well for linear relationships"],
        "weaknesses": ["Assumes linearity", "Sensitive to outliers", "Prone to underfitting"],
        "use_cases": ["Real Estate Price Prediction", "Sales Forecasting", "Risk Assessment"]
    },
    "LogisticRegression": {
        "name": "Logistic Regression",
        "icon": "fas fa-toggle-on",
        "color": "#e74c3c",
        "overview": "A classification algorithm used to estimate the probability of a binary outcome (yes/no, 0/1).",
        "how_it_works": "Instead of fitting a line, it uses the Sigmoid function to map any real-valued number into a value between 0 and 1, representing a probability.",
        "mechanics": "Uses the Logit function: p / (1-p) = e^(β₀ + β₁x). If the probability is > 0.5, the outcome is classified as 1.",
        "strengths": ["Simple and robust", "Provides probability scores", "Less prone to overfitting in low dimensions"],
        "weaknesses": ["Assumes linear boundaries", "Sensitive to multicollinearity", "Not for complex non-linear data"],
        "use_cases": ["Spam Email Detection", "Credit Default Prediction", "Disease Diagnosis (Binary)"]
    },
    "DecisionTree": {
        "name": "Decision Tree",
        "icon": "fas fa-tree",
        "color": "#2ecc71",
        "overview": "A versatile algorithm that can perform both classification and regression tasks by splitting data into branches.",
        "how_it_works": "It recursively partitions the data based on feature values that best separate the target classes, creating a tree-like structure of decisions.",
        "mechanics": "Uses metrics like Gini Impurity or Information Gain (Entropy) to determine the best splits at each node.",
        "strengths": ["Easy to visualize", "Handles non-linear data", "Requires little data preprocessing"],
        "weaknesses": ["Prone to overfitting (deep trees)", "Unstable (small data changes change the tree)", "Biased towards features with many levels"],
        "use_cases": ["Customer Segmentation", "Medical Diagnosis", "Credit Scoring"]
    },
    "RandomForest": {
        "name": "Random Forest",
        "icon": "fas fa-forest",
        "color": "#27ae60",
        "overview": "An ensemble method that builds multiple decision trees and merges them to get a more accurate and stable prediction.",
        "how_it_works": "It creates 'forest' of trees, usually trained with the 'bagging' method (bootstrap aggregating), using a random subset of features for each split.",
        "mechanics": "Aggregates the results of many trees (voting for classification, averaging for regression) to reduce variance.",
        "strengths": ["Highly accurate", "Handles large datasets well", "Low risk of overfitting"],
        "weaknesses": ["Computationally expensive", "Slower than single trees", "Black-box complexity"],
        "use_cases": ["Fraud Detection", "Risk Analysis", "Stock Market Analysis"]
    },
    "KNeighborsClassifier": {
        "name": "KNN Classifier",
        "icon": "fas fa-users",
        "color": "#9b59b6",
        "overview": "A non-parametric, lazy learning algorithm that classifies data points based on their proximity to others.",
        "how_it_works": "To predict a label, it finds the 'K' nearest points in the training set and assigns the most common label among them.",
        "mechanics": "Relies on distance metrics like Euclidean or Manhattan distance to find neighbors.",
        "strengths": ["Simple to understand", "No training phase (lazy)", "Adapts to new data easily"],
        "weaknesses": ["Computationally intensive for large data", "Sensitive to irrelevant features", "Requires careful scaling of features"],
        "use_cases": ["Image Recognition", "Simple Recommenders", "Pattern Recognition"]
    },
    "KNeighborsRegressor": {
        "name": "KNN Regressor",
        "icon": "fas fa-project-diagram",
        "color": "#8e44ad",
        "overview": "Similar to KNN Classifier, but predicts numerical values instead of categories.",
        "how_it_works": "It finds the 'K' nearest neighbors and calculates the average (or weighted average) of their target values to make a prediction.",
        "mechanics": "Uses local interpolation of the target variable from its nearest neighbors.",
        "strengths": ["Simple", "Handles non-linear relationships", "No assumptions about data distribution"],
        "weaknesses": ["Slow for large data", "Sensitive to outliers", "Affected by data scale"],
        "use_cases": ["Economic Forecasting", "Sensor Data Prediction", "Local Trend Analysis"]
    },
    "KMeans": {
        "name": "KMeans Clustering",
        "icon": "fas fa-cubes",
        "color": "#f1c40f",
        "overview": "An unsupervised learning algorithm that groups similar data points into clusters without pre-defined labels.",
        "how_it_works": "It partition 'n' observations into 'k' clusters in which each observation belongs to the cluster with the nearest mean (centroid).",
        "mechanics": "Iteratively calculates centroids and reassigns points until the within-cluster sum of squares is minimized.",
        "strengths": ["Fast and efficient", "Scales to large data", "Easy to implement"],
        "weaknesses": ["Requires pre-defining 'K'", "Sensitive to initial centroids", "Assumes spherical clusters"],
        "use_cases": ["Market Segmentation", "Anomaly Detection", "Document Clustering"]
    },
    "SVC": {
        "name": "SVC",
        "icon": "fas fa-vector-square",
        "color": "#e67e22",
        "overview": "Support Vector Classifier finds the optimal hyperplane that maximizes the margin between different classes.",
        "how_it_works": "It maps input vectors into higher-dimensional space and constructs a boundary (hyperplane) that separates points of different classes as wide as possible.",
        "mechanics": "Uses 'Support Vectors' (data points nearest the hyperplane) to define the boundary and 'Kernel Trick' for non-linear data.",
        "strengths": ["Effective in high dimensions", "Memory efficient", "Versatile kernels"],
        "weaknesses": ["Slow on large datasets", "Sensititve to tuning", "No direct probability estimates"],
        "use_cases": ["Face Detection", "Text Classification", "Bioinformatics"]
    },
    "SVR": {
        "name": "SVR",
        "icon": "fas fa-bezier-curve",
        "color": "#d35400",
        "overview": "Support Vector Regression uses the same principles as SVM but for predicting continuous values.",
        "how_it_works": "It tries to fit the best line within a predefined error margin (epsilon-tube) rather than just minimizing the squared error.",
        "mechanics": "Finds a function f(x) that deviates from target yi by no more than ε, while being as flat as possible.",
        "strengths": ["Robust to outliers", "Handles high dimensions", "Excellent for complex regression"],
        "weaknesses": ["Complex to tune", "High training time", "Black box nature"],
        "use_cases": ["Energy Load Prediction", "Financial Analysis", "Complex Physical Systems"]
    },
    "Lasso": {
        "name": "Lasso (L1)",
        "icon": "fas fa-filter",
        "color": "#34495e",
        "overview": "A linear regression variant that uses L1 regularization to penalize the absolute size of coefficients.",
        "how_it_works": "It adds a penalty term equal to the sum of absolute coefficients, which can shrink some coefficients exactly to zero.",
        "mechanics": "Cost = RSS + λ * Σ|βᵢ|. This effectively performs automatic feature selection.",
        "strengths": ["Automatic feature selection", "Prevents overfitting", "Simplifies models"],
        "weaknesses": ["Can be unstable with many features", "Better for sparse models", "May discard useful correlated features"],
        "use_cases": ["Feature Importance Ranking", "High-Dimensional Data", "Gene Expression Analysis"]
    },
    "Ridge": {
        "name": "Ridge (L2)",
        "icon": "fas fa-mountain",
        "color": "#2c3e50",
        "overview": "A linear regression variant that uses L2 regularization to prevent coefficients from becoming too large.",
        "how_it_works": "It adds a penalty term proportional to the square of the magnitude of coefficients, shrinking them towards zero but never exactly zero.",
        "mechanics": "Cost = RSS + λ * Σβᵢ². It keeps all features but shrinks their influence.",
        "strengths": ["Prevents overfitting", "Stable even with multicollinearity", "Good for dense models"],
        "weaknesses": ["Does not perform feature selection", "Requires λ tuning", "Retains all features (complex)"],
        "use_cases": ["Multi-collinear Datasets", "General Model Regularization", "Image Denoising"]
    }
}
