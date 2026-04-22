import numpy as np
import pandas as pd
from scipy import stats as scipy_stats


def calculate_eda_stats(df: pd.DataFrame, column: str) -> dict:
    """
    Computes EDA statistics for a given column.
    Handles both numeric and categorical columns.
    Returns a JSON-serializable dict.
    """
    if column not in df.columns:
        return {"error": f"Column '{column}' not found in dataset."}

    col_data = df[column]
    is_numeric = pd.api.types.is_numeric_dtype(col_data)

    result = {
        "column": column,
        "dtype": str(col_data.dtype),
        "total_count": int(len(col_data)),
        "null_count": int(col_data.isnull().sum()),
        "null_percent": round(float(col_data.isnull().mean() * 100), 2),
        "is_numeric": is_numeric,
    }

    if is_numeric:
        clean = col_data.dropna()

        if len(clean) == 0:
            result["error"] = "All values are null."
            return result

        q1 = float(clean.quantile(0.25))
        q3 = float(clean.quantile(0.75))
        iqr = q3 - q1
        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr
        outlier_count = int(((clean < lower_fence) | (clean > upper_fence)).sum())

        mode_series = clean.mode()
        mode_val = round(float(mode_series.iloc[0]), 4) if not mode_series.empty else None

        result.update({
            "mean": round(float(clean.mean()), 4),
            "median": round(float(clean.median()), 4),
            "mode": mode_val,
            "std": round(float(clean.std()), 4),
            "min": round(float(clean.min()), 4),
            "max": round(float(clean.max()), 4),
            "skewness": round(float(scipy_stats.skew(clean)), 4),
            "kurtosis": round(float(scipy_stats.kurtosis(clean)), 4),
            "q1": round(q1, 4),
            "q3": round(q3, 4),
            "iqr": round(iqr, 4),
            "outlier_count": outlier_count,
        })
    else:
        value_counts = col_data.value_counts()
        result.update({
            "unique_count": int(col_data.nunique()),
            "top_value": str(value_counts.index[0]) if not value_counts.empty else None,
            "top_count": int(value_counts.iloc[0]) if not value_counts.empty else 0,
        })

    return result


def get_plot_data(df: pd.DataFrame, col1: str, col2: str = None, plot_type: str = "histogram") -> dict:
    """
    Returns JSON-ready plot data for Plotly.js rendering.
    Supports: histogram, box, scatter, bar.
    Data is sampled/binned server-side to keep payloads small.
    """
    MAX_SCATTER_POINTS = 2000
    MAX_BAR_CATEGORIES = 30

    try:
        if col1 not in df.columns:
            return {"error": f"Column '{col1}' not found in dataset."}
        if col2 and col2 not in df.columns:
            return {"error": f"Column '{col2}' not found in dataset."}

        if plot_type == "histogram":
            col_data = df[col1].dropna()
            if not pd.api.types.is_numeric_dtype(col_data):
                return {"error": f"Column '{col1}' is not numeric. Use Bar chart for categorical columns."}

            counts, bin_edges = np.histogram(col_data, bins="auto")
            bin_centers = [round(float((bin_edges[i] + bin_edges[i + 1]) / 2), 4) for i in range(len(counts))]

            return {
                "plot_type": "histogram",
                "x": bin_centers,
                "y": [int(v) for v in counts],
                "col1": col1,
            }

        elif plot_type == "box":
            col_data = df[col1].dropna()
            if not pd.api.types.is_numeric_dtype(col_data):
                return {"error": f"Column '{col1}' is not numeric. Use Bar chart for categorical columns."}

            q1 = float(col_data.quantile(0.25))
            median = float(col_data.median())
            q3 = float(col_data.quantile(0.75))
            iqr_val = q3 - q1
            lower_fence = max(float(col_data.min()), q1 - 1.5 * iqr_val)
            upper_fence = min(float(col_data.max()), q3 + 1.5 * iqr_val)
            outliers = col_data[(col_data < q1 - 1.5 * iqr_val) | (col_data > q3 + 1.5 * iqr_val)]

            return {
                "plot_type": "box",
                "col1": col1,
                "q1": round(q1, 4),
                "median": round(median, 4),
                "q3": round(q3, 4),
                "lower_fence": round(lower_fence, 4),
                "upper_fence": round(upper_fence, 4),
                "outliers": [round(float(v), 4) for v in outliers.tolist()[:200]],
            }

        elif plot_type == "scatter":
            if not col2:
                return {"error": "Scatter plot requires a second attribute (Attribute 2)."}

            clean_df = df[[col1, col2]].dropna()
            if not pd.api.types.is_numeric_dtype(clean_df[col1]):
                return {"error": f"Column '{col1}' must be numeric for a scatter plot."}
            if not pd.api.types.is_numeric_dtype(clean_df[col2]):
                return {"error": f"Column '{col2}' must be numeric for a scatter plot."}

            if len(clean_df) > MAX_SCATTER_POINTS:
                clean_df = clean_df.sample(MAX_SCATTER_POINTS, random_state=42)

            return {
                "plot_type": "scatter",
                "x": [round(float(v), 4) for v in clean_df[col1].tolist()],
                "y": [round(float(v), 4) for v in clean_df[col2].tolist()],
                "col1": col1,
                "col2": col2,
            }

        elif plot_type == "bar":
            col_data = df[col1].dropna()
            value_counts = col_data.value_counts().head(MAX_BAR_CATEGORIES)

            return {
                "plot_type": "bar",
                "x": [str(v) for v in value_counts.index.tolist()],
                "y": [int(v) for v in value_counts.values.tolist()],
                "col1": col1,
            }

        else:
            return {"error": f"Unknown plot type: '{plot_type}'. Supported: histogram, box, scatter, bar."}

    except KeyError as e:
        return {"error": f"Column not found: {str(e)}"}
    except Exception as e:
        return {"error": f"Plot generation failed: {str(e)}"}
