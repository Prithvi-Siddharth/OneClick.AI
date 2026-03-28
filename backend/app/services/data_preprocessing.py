import pandas as pd
import numpy as np
from io import BytesIO
from sklearn import preprocessing
from sklearn.impute import KNNImputer
from fastapi import HTTPException
from sklearn.decomposition import PCA, TruncatedSVD
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.feature_selection import VarianceThreshold, SelectKBest, f_classif, f_regression, chi2

def get_dataset_preview_and_stats(file_buffer, extension, preview_limit=5):
    try:
        # Normalize input
        if isinstance(file_buffer, bytes):
            file_buffer = BytesIO(file_buffer)

        # Load dataset
        if extension == 'csv':
            df_full = pd.read_csv(file_buffer)
        elif extension == 'json':
            try:
                df_full = pd.read_json(file_buffer, lines=True)
            except ValueError:
                file_buffer.seek(0)
                df_full = pd.read_json(file_buffer)
        elif extension in ['xls', 'xlsx']:
            df_full = pd.read_excel(file_buffer)
        else:
            return {"error": f"Unsupported extension: {extension}"}

        # Column type separation
        numeric_df = df_full.select_dtypes(include=['number'])
        categorical_cols = df_full.select_dtypes(include=['object', 'category']).columns.tolist()
        datetime_cols = df_full.select_dtypes(include=['datetime64']).columns.tolist()
        bool_cols = df_full.select_dtypes(include=['bool']).columns.tolist()

        # Safe outlier count
        def count_outliers(series):
            std = series.std()
            if std == 0 or pd.isna(std):
                return 0
            return ((series - series.mean()).abs() > 3 * std).sum()

        # Helper to sanitize dicts for JSON (replaces NaN with None and handles numpy types)
        def json_safe(val):
            if isinstance(val, dict):
                return {k: json_safe(v) for k, v in val.items() if k is not None} # Minor fix for dict keys
            elif isinstance(val, (list, tuple)):
                return [json_safe(v) for v in val]
            elif pd.isna(val) or val is pd.NA:
                return None
            elif hasattr(val, 'item'): # Handle numpy types
                return val.item()
            return val

        # Ensure numeric_df only has finite values for correlation and skewness
        numeric_clean = numeric_df.dropna()

        stats = {
            "total_rows": int(len(df_full)),
            "column_names": df_full.columns.tolist(),
            "data_types": df_full.dtypes.astype(str).to_dict(),
            "missing_values": df_full.isnull().sum().to_dict(),
            "duplicate_rows": int(df_full.duplicated().sum()),
            "unique_counts": df_full.nunique().to_dict(),
            "categorical_variables": categorical_cols,
            "numeric_variables": numeric_df.columns.tolist(),
            "date_variables": datetime_cols,
            "boolean_variables": bool_cols,
            "correlation_matrix": numeric_clean.corr().to_dict() if not numeric_clean.empty else {},
            "summary_stats": df_full.describe(include='all').where(pd.notnull(df_full.describe(include='all')), None).to_dict(),
            "outliers": numeric_df.apply(count_outliers).to_dict(),
            "skewness": numeric_df.skew().to_dict()
        }

        # preview
        df_preview = df_full.head(preview_limit)
        df_preview = df_preview.where(pd.notnull(df_preview), None)

        preview_records = df_preview.to_dict(orient="records")

        return {
            "data_preview": json_safe(preview_records),
            "stats": json_safe(stats)
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"Pandas processing error: {str(e)}"}


def apply_preprocessing(df_full, operations, attributes, target_column=None):
    """
    Applies preprocessing operations to the dataframe.
    
    operations: dict like {"encoding": ["onehot", "label"], "scaling": ["minmax"]}
    attributes: list of column names like ["column1", "column2"]
    """
    try:
        if not attributes or not any(operations.values()):
            raise HTTPException(
                status_code=400,
                detail="No attributes or operations selected"
            )

        # Helper to get numeric/categorical attributes from the selected ones
        numeric_attrs = [a for a in attributes if a in df_full.columns and pd.api.types.is_numeric_dtype(df_full[a])]
        categorical_attrs = [a for a in attributes if a in df_full.columns and not pd.api.types.is_numeric_dtype(df_full[a])]

        # Step 2: Drop Columns
        drop_ops = operations.get("drop_columns", [])
        if "remove_duplicates" in drop_ops:
            df_full = df_full.drop_duplicates().reset_index(drop=True)
        if "drop_attr" in drop_ops:
            df_full = df_full.drop(columns=[a for a in attributes if a in df_full.columns], errors='ignore')
            # If we dropped attributes, we should update the lists for subsequent steps
            attributes = [a for a in attributes if a in df_full.columns]
            numeric_attrs = [a for a in attributes if a in df_full.columns and pd.api.types.is_numeric_dtype(df_full[a])]
            categorical_attrs = [a for a in attributes if a in df_full.columns and not pd.api.types.is_numeric_dtype(df_full[a])]

        # Step 3: Missing Value Imputation
        missing_ops = operations.get("missing_values", [])
        if missing_ops:
            valid_attrs = [a for a in attributes if a in df_full.columns]

            if "drop_rows" in missing_ops:
                df_full = df_full.dropna(subset=valid_attrs)
                attributes = [a for a in attributes if a in df_full.columns]

            elif "knn" in missing_ops and numeric_attrs:
                if not numeric_attrs:
                    raise HTTPException(
                        status_code=400,
                        detail="KNN imputation requires at least one numeric column to be selected."
                    )
                all_numeric = df_full.select_dtypes(include='number').columns.tolist()
                imputer = KNNImputer(n_neighbors=5)
                df_full[all_numeric] = imputer.fit_transform(df_full[all_numeric])

            else:
                for attr in valid_attrs:
                    if "mean" in missing_ops:
                        if not pd.api.types.is_numeric_dtype(df_full[attr]):
                            raise HTTPException(
                                status_code=400,
                                detail=f"Mean imputation requires numeric columns. '{attr}' is not numeric."
                            )
                        df_full[attr] = df_full[attr].fillna(df_full[attr].mean())
                    elif "median" in missing_ops:
                        if not pd.api.types.is_numeric_dtype(df_full[attr]):
                            raise HTTPException(
                                status_code=400,
                                detail=f"Median imputation requires numeric columns. '{attr}' is not numeric."
                            )
                        df_full[attr] = df_full[attr].fillna(df_full[attr].median())
                    elif "mode" in missing_ops:
                        mode_val = df_full[attr].mode()
                        if not mode_val.empty:
                            df_full[attr] = df_full[attr].fillna(mode_val[0])
        
        # Step 4: Outlier Handling
        outlier_ops = operations.get("outliers", [])
        if outlier_ops:
            for attr in attributes:
                if attr in df_full.columns and not pd.api.types.is_numeric_dtype(df_full[attr]):
                    raise HTTPException(
                        status_code=400,
                        detail="Attribute is not numeric"
                    )
        if outlier_ops:
            for attr in numeric_attrs:
                q1 = df_full[attr].quantile(0.25)
                q3 = df_full[attr].quantile(0.75)
                iqr_val = q3 - q1
                lower = q1 - 1.5 * iqr_val
                upper = q3 + 1.5 * iqr_val

                if "iqr" in outlier_ops:
                    df_full[attr] = df_full[attr].clip(lower=lower, upper=upper)

                elif "zscore" in outlier_ops:
                    mean = df_full[attr].mean()
                    std = df_full[attr].std()
                    if std == 0:
                        continue
                    df_full[attr] = df_full[attr].clip(
                        lower=mean - 3 * std,
                        upper=mean + 3 * std
                    )

                elif "replace_mean" in outlier_ops:
                    mean_val = df_full[attr].mean() 
                    mask = (df_full[attr] < lower) | (df_full[attr] > upper)
                    df_full.loc[mask, attr] = mean_val
                    df_full[attr] = df_full[attr].fillna(mean_val)

                elif "replace_median" in outlier_ops:
                    med_val = df_full[attr].median()
                    mask = (df_full[attr] < lower) | (df_full[attr] > upper)
                    df_full.loc[mask, attr] = med_val
                    df_full[attr] = df_full[attr].fillna(med_val)
            
                elif "replace_mode" in outlier_ops:
                    mode_series = df_full[attr].mode()
                    if not mode_series.empty:
                        mode_val = mode_series[0]                              
                        mask = (df_full[attr] < lower) | (df_full[attr] > upper)
                        df_full.loc[mask, attr] = mode_val                    
                        df_full[attr] = df_full[attr].fillna(mode_val)        

        
        # Step 5: Encoding
        encoding_ops = operations.get("encoding", [])
        if encoding_ops:
            for attr in attributes:
                if attr in df_full.columns and pd.api.types.is_numeric_dtype(df_full[attr]):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Attribute '{attr}' is not categorical. Encoding requires categorical data."
                    )
        
        # After onehot encoding, refresh numeric_attrs
        if "onehot" in encoding_ops and categorical_attrs:
            df_full = pd.get_dummies(df_full, columns=categorical_attrs, drop_first=True)
            # Cast bool columns to int for downstream compatibility
            bool_cols = df_full.select_dtypes(include='bool').columns
            df_full[bool_cols] = df_full[bool_cols].astype(int)
            categorical_attrs = []
            numeric_attrs = [a for a in df_full.columns if pd.api.types.is_numeric_dtype(df_full[a])]
        
        if "label" in encoding_ops:
            if not categorical_attrs:
                raise HTTPException(
                    status_code=400,
                    detail="Label encoding requires at least one categorical column to be selected."
                )
            for attr in categorical_attrs:
                le = preprocessing.LabelEncoder()
                df_full[attr] = le.fit_transform(df_full[attr].astype(str))
        
        if "target" in encoding_ops and categorical_attrs:
            if not target_column or target_column not in df_full.columns:
                raise HTTPException(
                    status_code=400,
                    detail="Target Encoding requires a target column to be selected."
                )
            for attr in categorical_attrs:
                if attr != target_column:
                    means = df_full.groupby(attr)[target_column].mean()
                    df_full[attr] = df_full[attr].map(means)
                    # Fill any unmapped categories with global mean
                    global_mean = df_full[target_column].mean()
                    df_full[attr] = df_full[attr].fillna(global_mean)
        
        if "freq" in encoding_ops and categorical_attrs:
            for attr in categorical_attrs:
                freq = df_full[attr].value_counts(normalize=True)
                df_full[attr] = df_full[attr].map(freq)
                df_full[attr] = df_full[attr].fillna(0)   # ← NaN categories get frequency 0
        
        if "ordinal" in encoding_ops and categorical_attrs:
            for attr in categorical_attrs:
                try:
                    # Sort for deterministic ordering
                    unique_values = sorted(df_full[attr].dropna().unique())
                except TypeError:
                    # Mixed types — fall back to appearance order
                    unique_values = df_full[attr].dropna().unique()
                value_to_rank = {value: rank for rank, value in enumerate(unique_values)}
                df_full[attr] = df_full[attr].map(value_to_rank)

        # Step 6: Feature Scaling
        scaling_ops = [op for op in operations.get("scaling", []) if op]

        # Refresh numeric_attrs to capture columns encoded in Step 5
        numeric_attrs = [
            a for a in attributes
            if a in df_full.columns and pd.api.types.is_numeric_dtype(df_full[a])
        ]

        if scaling_ops:
            # Validate all selected attributes are numeric
            for attr in attributes:
                if attr in df_full.columns and not pd.api.types.is_numeric_dtype(df_full[attr]):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Attribute '{attr}' is not numeric. Scaling requires numeric data."
                    )

            # Validate no missing values
            if numeric_attrs and df_full[numeric_attrs].isnull().any().any():
                raise HTTPException(
                    status_code=400,
                    detail="Scaling requires no missing values. Please apply missing value imputation first (Step 3)."
                )

        if scaling_ops and numeric_attrs:
            if "minmax" in scaling_ops:
                constant_cols = [a for a in numeric_attrs if df_full[a].nunique() <= 1]
                if constant_cols:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Columns {constant_cols} have zero variance and cannot be MinMax scaled."
                    )
                scaler = preprocessing.MinMaxScaler()
                df_full[numeric_attrs] = scaler.fit_transform(df_full[numeric_attrs])

            elif "zscore_scale" in scaling_ops:
                scaler = preprocessing.StandardScaler()
                df_full[numeric_attrs] = scaler.fit_transform(df_full[numeric_attrs])

            elif "robust" in scaling_ops:
                scaler = preprocessing.RobustScaler()
                df_full[numeric_attrs] = scaler.fit_transform(df_full[numeric_attrs])

            elif "maxabs" in scaling_ops:
                scaler = preprocessing.MaxAbsScaler()
                df_full[numeric_attrs] = scaler.fit_transform(df_full[numeric_attrs])

        # Step 7: Transformations
        trans_ops = [op for op in operations.get("transformations", []) if op]
        if trans_ops and numeric_attrs:
            # Validate all selected attributes are numeric
            for attr in attributes:
                if attr in df_full.columns and not pd.api.types.is_numeric_dtype(df_full[attr]):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Attribute '{attr}' is not numeric. Transformations require numeric data."
                    )

            for attr in numeric_attrs:
                if "log" in trans_ops:
                    df_full[attr] = np.log1p(df_full[attr].clip(lower=0))

                elif "sqrt" in trans_ops:
                    df_full[attr] = np.sqrt(df_full[attr].clip(lower=0))

                elif "reciprocal" in trans_ops:
                    df_full[attr] = 1 / (df_full[attr].replace(0, np.nan))

                elif "yeojohnson" in trans_ops:
                    if df_full[attr].isnull().any():
                        raise HTTPException(
                            status_code=400,
                            detail=f"Yeo-Johnson requires no missing values in '{attr}'. Apply imputation first."
                        )
                    pt = preprocessing.PowerTransformer(method='yeo-johnson')
                    df_full[[attr]] = pt.fit_transform(df_full[[attr]])

                elif "boxcox" in trans_ops:
                    if df_full[attr].isnull().any():
                        raise HTTPException(
                            status_code=400,
                            detail=f"Box-Cox requires no missing values in '{attr}'. Apply imputation first."
                        )
                    pt = preprocessing.PowerTransformer(method='box-cox')
                    df_full[[attr]] = pt.fit_transform(df_full[[attr]].clip(lower=1e-6))

            # Binning gets its own clean loop — outside the per-attr loop
            if "binning" in trans_ops:
                for attr in numeric_attrs:
                    if df_full[attr].isnull().any():
                        raise HTTPException(
                            status_code=400,
                            detail=f"Binning requires no missing values in '{attr}'. Apply imputation first."
                        )
                    q = min(5, df_full[attr].nunique())
                    if q < 2:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Column '{attr}' has too few unique values for binning."
                        )
                    df_full[attr] = pd.qcut(
                        df_full[attr], q=q, labels=False, duplicates='drop'
                    ).astype(float)

        # Step 8: Feature Selection
        feature_selection_ops = [op for op in operations.get("feature_selection", []) if op]
        if feature_selection_ops:
            # Validate regardless of numeric_attrs state
            for attr in attributes:
                if attr in df_full.columns and not pd.api.types.is_numeric_dtype(df_full[attr]):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Attribute '{attr}' is not numeric. Feature selection requires numeric data."
                    )
            if not numeric_attrs:
                raise HTTPException(
                    status_code=400,
                    detail="No numeric columns selected. Feature selection requires numeric data."
                )

            if "low_variance" in feature_selection_ops:
                col_max = df_full[numeric_attrs].max().max()
                threshold = 0.01 if col_max <= 1.0 else 0.1
                selector = VarianceThreshold(threshold=threshold)
                selector.fit(df_full[numeric_attrs])
                cols_to_drop = [c for c, keep in zip(numeric_attrs, selector.get_support()) if not keep]
                df_full = df_full.drop(columns=cols_to_drop)
                numeric_attrs = [c for c in numeric_attrs if c not in cols_to_drop]

            if "kbest" in feature_selection_ops:
                if not target_column or target_column not in df_full.columns:
                    raise HTTPException(status_code=400, detail="K-best requires a target column.")
                feature_cols = [c for c in numeric_attrs if c != target_column]
                if not feature_cols:
                    raise HTTPException(status_code=400, detail="No feature columns remaining for k-best.")
                if df_full[feature_cols].isnull().any().any():
                    raise HTTPException(status_code=400, detail="K-best requires no missing values. Apply imputation first.")
                is_continuous = pd.api.types.is_float_dtype(df_full[target_column]) and \
                                df_full[target_column].nunique() > 20
                score_func = f_regression if is_continuous else f_classif
                k = min(10, len(feature_cols))
                selector = SelectKBest(score_func, k=k)
                selector.fit(df_full[feature_cols], df_full[target_column])
                new_cols = [feature_cols[i] for i, s in enumerate(selector.get_support()) if s]
                cols_to_drop = [c for c in feature_cols if c not in new_cols]
                df_full = df_full.drop(columns=cols_to_drop)
                numeric_attrs = [c for c in numeric_attrs if c not in cols_to_drop]

            if "correlation_threshold" in feature_selection_ops:
                corr_matrix = df_full[numeric_attrs].corr().abs()
                upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
                to_drop = [col for col in upper.columns if any(upper[col] > 0.9)]
                df_full = df_full.drop(columns=to_drop)
                numeric_attrs = [c for c in numeric_attrs if c not in to_drop]

            if "tree_importance" in feature_selection_ops:
                if not target_column or target_column not in df_full.columns:
                    raise HTTPException(status_code=400, detail="Tree importance requires a target column.")
                feature_cols = [c for c in numeric_attrs if c != target_column]
                if not feature_cols:
                    raise HTTPException(status_code=400, detail="No feature columns remaining for tree importance.")
                if df_full[feature_cols].isnull().any().any():
                    raise HTTPException(status_code=400, detail="Tree importance requires no missing values. Apply imputation first.")
                from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
                is_continuous = pd.api.types.is_float_dtype(df_full[target_column]) and \
                                df_full[target_column].nunique() > 20
                rf = RandomForestRegressor(n_estimators=100, random_state=42) if is_continuous \
                    else RandomForestClassifier(n_estimators=100, random_state=42)
                rf.fit(df_full[feature_cols], df_full[target_column])
                importances = pd.Series(rf.feature_importances_, index=feature_cols)
                selected = importances[importances >= importances.mean()].index.tolist()
                cols_to_drop = [c for c in feature_cols if c not in selected]
                df_full = df_full.drop(columns=cols_to_drop)
                numeric_attrs = [c for c in numeric_attrs if c not in cols_to_drop]

            if "chi2" in feature_selection_ops:
                if not target_column or target_column not in df_full.columns:
                    raise HTTPException(status_code=400, detail="Chi-squared requires a target column.")
                if (df_full[numeric_attrs] < 0).any().any():
                    raise HTTPException(status_code=400, detail="Chi-squared requires non-negative values. Apply MinMax scaling first.")
                if df_full[numeric_attrs].isnull().any().any():
                    raise HTTPException(status_code=400, detail="Chi-squared requires no missing values. Apply imputation first.")
                k = min(10, len(numeric_attrs))
                selector = SelectKBest(chi2, k=k)
                selector.fit(df_full[numeric_attrs], df_full[target_column])
                selected = df_full[numeric_attrs].columns[selector.get_support()].tolist()
                cols_to_drop = [c for c in numeric_attrs if c not in selected]
                df_full = df_full.drop(columns=cols_to_drop)
                numeric_attrs = selected

        # Step 9: Data Reduction
        data_reduction_ops = [op for op in operations.get("data_reduction", []) if op]
        if data_reduction_ops:
            if not numeric_attrs:
                raise HTTPException(
                    status_code=400,
                    detail="Data reduction requires at least 2 numeric columns."
                )
            for attr in attributes:
                if attr in df_full.columns and not pd.api.types.is_numeric_dtype(df_full[attr]):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Attribute '{attr}' is not numeric. Data reduction requires numeric data."
                    )

            if "pca" in data_reduction_ops:
                if df_full[numeric_attrs].isnull().any().any():
                    raise HTTPException(status_code=400,
                        detail="PCA requires no missing values. Apply imputation first (Step 3).")

                col_stds = df_full[numeric_attrs].std()
                if col_stds.max() / (col_stds.min() + 1e-9) > 100:
                    print("WARNING: PCA features have very different scales. Apply scaling first.")

                n_samples, n_features = len(df_full), len(numeric_attrs)
                max_components = min(n_samples, n_features)
                if max_components < 2:
                    raise HTTPException(status_code=400,
                        detail="PCA requires at least 2 columns and 2 rows.")

                pca = PCA(n_components=0.95, svd_solver='full') if max_components >= 10 \
                    else PCA(n_components=max_components - 1)

                try:
                    transformed = pca.fit_transform(df_full[numeric_attrs])
                except ValueError as e:
                    raise HTTPException(status_code=400,
                        detail=f"PCA failed: {str(e)}. Try scaling first.")

                new_cols = [f"PC{i+1}" for i in range(transformed.shape[1])]
                remaining = df_full.drop(columns=numeric_attrs).reset_index(drop=True)
                df_full = pd.concat([remaining, pd.DataFrame(transformed, columns=new_cols)], axis=1)
                numeric_attrs = new_cols

            elif "lda" in data_reduction_ops:
                if not target_column or target_column not in df_full.columns:
                    raise HTTPException(status_code=400, detail="LDA requires a target column.")

                lda_feature_cols = [c for c in numeric_attrs if c != target_column]
                if not lda_feature_cols:
                    raise HTTPException(status_code=400,
                        detail="No feature columns remaining for LDA.")

                if df_full[lda_feature_cols].isnull().any().any():
                    raise HTTPException(status_code=400,
                        detail="LDA requires no missing values. Apply imputation first (Step 3).")

                n_classes = df_full[target_column].nunique()
                if n_classes < 2:
                    raise HTTPException(status_code=400,
                        detail=f"LDA requires at least 2 classes in target. Found: {n_classes}.")

                max_lda_components = min(len(lda_feature_cols), n_classes - 1)
                lda = LinearDiscriminantAnalysis(n_components=max_lda_components)

                try:
                    transformed = lda.fit_transform(
                        df_full[lda_feature_cols], df_full[target_column].astype(str)
                    )
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=f"LDA failed: {str(e)}")

                new_cols = [f"LDA{i+1}" for i in range(transformed.shape[1])]
                remaining = df_full.drop(columns=lda_feature_cols).reset_index(drop=True)
                df_full = pd.concat([remaining, pd.DataFrame(transformed, columns=new_cols)], axis=1)
                numeric_attrs = new_cols

            elif "ica" in data_reduction_ops:
                from sklearn.decomposition import FastICA

                if df_full[numeric_attrs].isnull().any().any():
                    raise HTTPException(status_code=400,
                        detail="ICA requires no missing values. Apply imputation first (Step 3).")

                n_components = max(1, min(len(numeric_attrs) - 1, len(df_full) - 1))
                ica = FastICA(n_components=n_components, random_state=42, max_iter=1000, tol=0.01)

                try:
                    transformed = ica.fit_transform(df_full[numeric_attrs])
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"ICA failed: {str(e)}")

                new_cols = [f"IC{i+1}" for i in range(transformed.shape[1])]
                remaining = df_full.drop(columns=numeric_attrs).reset_index(drop=True)
                df_full = pd.concat([remaining, pd.DataFrame(transformed, columns=new_cols)], axis=1)
                numeric_attrs = new_cols

        # Step 10: Imbalanced Data
        imbalanced_data_ops = [op for op in operations.get("imbalanced_data", []) if op]
        if imbalanced_data_ops:
            if not target_column or target_column not in df_full.columns:
                raise HTTPException(
                    status_code=400,
                    detail="Imbalanced data handling requires a target column. Please select one in Section 0."
                )

            if df_full[target_column].isnull().any():
                raise HTTPException(
                    status_code=400,
                    detail="Target column contains missing values. Apply imputation first (Step 3)."
                )

            smote_feature_cols = [c for c in numeric_attrs if c != target_column]
            if not smote_feature_cols:
                raise HTTPException(
                    status_code=400,
                    detail="No feature columns available after excluding target column."
                )

            # Validate target is categorical
            n_classes = df_full[target_column].nunique()
            if n_classes > 20 or pd.api.types.is_float_dtype(df_full[target_column]):
                raise HTTPException(
                    status_code=400,
                    detail="Imbalanced data handling requires a categorical target column."
                )

            if "smote" in imbalanced_data_ops:
                if df_full[smote_feature_cols].isnull().any().any():
                    raise HTTPException(
                        status_code=400,
                        detail="SMOTE requires no missing values. Apply imputation first (Step 3)."
                    )

                min_class_count = df_full[target_column].value_counts().min()
                k_neighbors = min(5, min_class_count - 1)
                if k_neighbors < 1:
                    raise HTTPException(
                        status_code=400,
                        detail=f"SMOTE requires at least 2 samples in minority class. Found: {min_class_count}."
                    )

                try:
                    from imblearn.over_sampling import SMOTE
                    other_cols = [c for c in df_full.columns
                                  if c not in smote_feature_cols and c != target_column]
                    if other_cols:
                        print(f"WARNING: Columns {other_cols} will be dropped after SMOTE.")

                    smote = SMOTE(k_neighbors=k_neighbors)
                    X_res, y_res = smote.fit_resample(
                        df_full[smote_feature_cols], df_full[target_column]
                    )
                    df_res = pd.DataFrame(X_res, columns=smote_feature_cols)
                    df_res[target_column] = y_res
                    df_full = df_res

                except ImportError:
                    raise HTTPException(
                        status_code=500,
                        detail="imbalanced-learn not installed. Run: pip install imbalanced-learn"
                    )

            if "class_weights" in imbalanced_data_ops:
                from sklearn.utils.class_weight import compute_class_weight
                weights = compute_class_weight(
                    'balanced',
                    classes=np.unique(df_full[target_column]),
                    y=df_full[target_column]
                )
                weight_dict = dict(zip(
                    np.unique(df_full[target_column]).tolist(),
                    weights.tolist()
                ))
                df_full.attrs['class_weights'] = weight_dict
                print(f"Class weights computed: {weight_dict}")

        return df_full
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"Pandas processing error: {str(e)}"}