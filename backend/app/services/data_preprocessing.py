import pandas as pd
from io import BytesIO
import sklearn.preprocessing as preprocessing

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
                return {k: json_safe(v) for k, v in val.items()}
            elif isinstance(val, (list, tuple)):
                return [json_safe(v) for v in val]
            elif pd.isna(val):
                return None
            elif hasattr(val, 'item'): # Handle numpy types
                return val.item()
            return val

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
            "correlation_matrix": numeric_df.corr().to_dict() if not numeric_df.empty else {},
            "summary_stats": df_full.describe(include='all').to_dict(),
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
        return {"error": f"Pandas processing error: {str(e)}"}


def apply_preprocessing(df_full, operations, attributes):
    try:
        # attributes is now a list
        if not attributes:
            return df_full

        if operations.get("onehot"):
            # One-Hot is usually better applied as a batch if multiple columns selected
            # Filter for categorical columns in the selection
            valid_cats = [a for a in attributes if a in df_full.columns and df_full[a].dtype in ['object', 'category']]
            if valid_cats:
                encoder = preprocessing.OneHotEncoder(sparse_output=False, handle_unknown='ignore')
                encoded_data = encoder.fit_transform(df_full[valid_cats])
                encoded_df = pd.DataFrame(encoded_data, columns=encoder.get_feature_names_out(valid_cats), index=df_full.index)
                df_full = df_full.drop(columns=valid_cats).join(encoded_df)

        if operations.get("label"):
            for attribute in attributes:
                if attribute in df_full.columns:
                    encoder = preprocessing.LabelEncoder()
                    df_full[attribute] = encoder.fit_transform(df_full[attribute].astype(str))

        if operations.get("target"):
            for attribute in attributes:
                if attribute in df_full.columns:
                    # Target encoding requires a target column
                    target_col = df_full.columns[-1] if len(df_full.columns) > 1 else None
                    if target_col and target_col != attribute:
                        encoder = preprocessing.TargetEncoder()
                        df_full[attribute] = encoder.fit_transform(df_full[[attribute]], df_full[target_col])
                    else:
                        continue # Skip if no target column available for this attribute
        
        return df_full
    except Exception as e:
        return {"error": f"Pandas processing error: {str(e)}"}