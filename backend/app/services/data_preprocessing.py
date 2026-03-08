import pandas as pd
import numpy as np
from io import BytesIO
from sklearn import preprocessing
from sklearn.impute import KNNImputer
from fastapi import HTTPException 

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


def apply_preprocessing(df_full, operations, attributes):
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
            df_full = df_full.drop_duplicates()
        if "drop_attr" in drop_ops:
            df_full = df_full.drop(columns=[a for a in attributes if a in df_full.columns], errors='ignore')
            # If we dropped attributes, we should update the lists for subsequent steps
            attributes = [a for a in attributes if a in df_full.columns]
            numeric_attrs = [a for a in attributes if a in df_full.columns and pd.api.types.is_numeric_dtype(df_full[a])]
            categorical_attrs = [a for a in attributes if a in df_full.columns and not pd.api.types.is_numeric_dtype(df_full[a])]

        # Step 3: Missing Value Imputation
        missing_ops = operations.get("missing_values", [])
        for attr in attributes:
            if attr not in df_full.columns: continue
            if "mean" in missing_ops and pd.api.types.is_numeric_dtype(df_full[attr]):
                df_full[attr] = df_full[attr].fillna(df_full[attr].mean())
            elif "median" in missing_ops and pd.api.types.is_numeric_dtype(df_full[attr]):
                df_full[attr] = df_full[attr].fillna(df_full[attr].median())
            elif "mode" in missing_ops:
                mode_val = df_full[attr].mode()
                if not mode_val.empty:
                    df_full[attr] = df_full[attr].fillna(mode_val[0])
            elif "drop_rows" in missing_ops:
                df_full = df_full.dropna(subset=[attr])
            elif "knn" in missing_ops and numeric_attrs:
                imputer = KNNImputer(n_neighbors=5)
                df_full[numeric_attrs] = imputer.fit_transform(df_full[numeric_attrs])
        
        # Step 4: Outlier Handling
        outlier_ops = operations.get("outliers", [])
        if outlier_ops:
            for attr in attributes:
                if attr in df_full.columns and not pd.api.types.is_numeric_dtype(df_full[attr]):
                    raise HTTPException(
                        status_code=400,
                        detail="Attribute is not numeric"
                    )

        for attr in numeric_attrs:

            if "iqr" in outlier_ops:
                q1 = df_full[attr].quantile(0.25)
                q3 = df_full[attr].quantile(0.75)
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                df_full[attr] = df_full[attr].clip(lower=lower, upper=upper)

            elif "zscore" in outlier_ops:
                mean = df_full[attr].mean()
                std = df_full[attr].std()
                lower = mean - 3 * std
                upper = mean + 3 * std
                df_full[attr] = df_full[attr].clip(lower=lower, upper=upper)

            elif "mean" in outlier_ops:
                # Replace IQR outliers with column mean
                q1 = df_full[attr].quantile(0.25)
                q3 = df_full[attr].quantile(0.75)
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
        
                mean_val = df_full[attr].mean() 
                mask = (df_full[attr] < lower) | (df_full[attr] > upper)
                df_full.loc[mask, attr] = mean_val
                df_full[attr] = df_full[attr].fillna(mean_val)

            elif "median" in outlier_ops:
                # Replace IQR outliers with column median
                q1 = df_full[attr].quantile(0.25)
                q3 = df_full[attr].quantile(0.75)
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
        
                med_val = df_full[attr].median()
                mask = (df_full[attr] < lower) | (df_full[attr] > upper)
                df_full.loc[mask, attr] = med_val
                df_full[attr] = df_full[attr].fillna(med_val)
        
        # Step 5: Encoding
        encoding_ops = operations.get("encoding", [])
        if encoding_ops:
            for attr in attributes:
                if attr in df_full.columns and pd.api.types.is_numeric_dtype(df_full[attr]):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Attribute '{attr}' is not categorical. Encoding requires categorical data."
                    )
        
        if "onehot" in encoding_ops and categorical_attrs:
            df_full = pd.get_dummies(df_full, columns=categorical_attrs, drop_first=True)
            # Categorical attributes are gone now, update metadata
            categorical_attrs = []
        
        if "label" in encoding_ops:
            for attr in categorical_attrs:
                le = preprocessing.LabelEncoder()
                df_full[attr] = le.fit_transform(df_full[attr].astype(str))
        
        if "target" in encoding_ops and categorical_attrs:
            # Assume last column is target if not specified
            target_col = df_full.columns[-1]
            for attr in categorical_attrs:
                if attr != target_col:
                    means = df_full.groupby(attr)[target_col].mean()
                    df_full[attr] = df_full[attr].map(means)

        # Step 6: Feature Scaling
        scaling_ops = [op for op in operations.get("scaling", []) if op]
        if scaling_ops:
            for attr in attributes:
                if attr in df_full.columns and not pd.api.types.is_numeric_dtype(df_full[attr]):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Attribute '{attr}' is not numeric. Scaling requires numeric data."
                    )
        
        if numeric_attrs:
            if "minmax" in scaling_ops:
                scaler = preprocessing.MinMaxScaler()
                df_full[numeric_attrs] = scaler.fit_transform(df_full[numeric_attrs])
            elif "standard" in scaling_ops or "zscore_scale" in scaling_ops:
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
        if trans_ops:
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
                pt = preprocessing.PowerTransformer(method='yeo-johnson')
                df_full[[attr]] = pt.fit_transform(df_full[[attr]])
        
        if "binning" in trans_ops or "discretization" in trans_ops:
            for attr in numeric_attrs:
                df_full[attr] = pd.qcut(df_full[attr], q=5, labels=False, duplicates='drop')

        # Steps 8-10: Simplified Placeholders for now as they often require target columns or specific params
        # Feature Selection, Data Reduction, Imbalanced Data usually happen right before training
        
        return df_full
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"Pandas processing error: {str(e)}"}
