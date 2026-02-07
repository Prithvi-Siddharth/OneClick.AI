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


def apply_preprocessing(df_full, operations):
    try:
        if operations.get("onehot"):
            # Select categorical columns
            cat_cols = df_full.select_dtypes(include=['object', 'category']).columns.tolist()
            if cat_cols:
                encoder = preprocessing.OneHotEncoder(sparse_output=False, handle_unknown='ignore')
                encoded_data = encoder.fit_transform(df_full[cat_cols])
                encoded_df = pd.DataFrame(encoded_data, columns=encoder.get_feature_names_out(cat_cols), index=df_full.index)
                # Drop original categorical columns and join encoded ones
                df_full = df_full.drop(columns=cat_cols).join(encoded_df)

        if operations.get("label"):
            for col in df_full.select_dtypes(include=['object', 'category']).columns:
                df_full[col] = df_full[col].astype('category').cat.codes

        if operations.get("minmax"):
            numeric_cols = df_full.select_dtypes(include=['number']).columns.tolist()
            if numeric_cols:
                scaler = preprocessing.MinMaxScaler()
                df_full[numeric_cols] = scaler.fit_transform(df_full[numeric_cols])
        
        return df_full
    except Exception as e:
        return {"error": f"Pandas processing error: {str(e)}"}