try:
    import duckdb
except ImportError:
    duckdb = None

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# =========================
# CONFIG
# =========================

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET = os.getenv("S3_BUCKET_NAME")


# =========================
# CONNECTION
# =========================

def init_duckdb_connection():
    """
    Initialize DuckDB connection with S3 support
    """
    if duckdb is None:
        raise RuntimeError("DuckDB is not installed on this serverless environment. Please use client-side DuckDB-Wasm.")
    con = duckdb.connect()

    # Install & load S3 extension
    con.execute("INSTALL httpfs;")
    con.execute("LOAD httpfs;")

    # Set AWS credentials
    con.execute(f"SET s3_access_key_id='{AWS_ACCESS_KEY_ID}'")
    con.execute(f"SET s3_secret_access_key='{AWS_SECRET_ACCESS_KEY}'")
    con.execute(f"SET s3_region='{AWS_REGION}'")

    return con


# =========================
# S3 PATH BUILDER
# =========================

def build_s3_path(user_id: str, dataset: str, file_type: str):
    """
    Construct S3 path for dataset
    """
    return f"s3://{S3_BUCKET}/{user_id}/{dataset}/*.{file_type}"


# =========================
# FILE TYPE HANDLER
# =========================

def get_table_reference(s3_path: str, file_type: str):
    """
    Returns DuckDB table reference for given file type
    """
    if file_type == "csv":
        return f"read_csv_auto('{s3_path}')"

    elif file_type == "parquet":
        return f"read_parquet('{s3_path}')"

    else:
        raise ValueError("Unsupported file type. Only 'csv' and 'parquet' are supported.")


# =========================
# QUERY VALIDATION
# =========================

def validate_query(user_query: str):
    """
    Basic validation to prevent unsafe queries
    """
    query = user_query.strip().lower()

    if not query.startswith("select"):
        raise ValueError("Only SELECT queries are allowed")

    if "table" not in query:
        raise ValueError("Query must include TABLE placeholder")

    # Prevent dangerous keywords
    blocked_keywords = ["insert", "update", "delete", "drop", "alter", "create"]

    for keyword in blocked_keywords:
        if keyword in query:
            raise ValueError(f"Keyword '{keyword}' is not allowed")

    return True


# =========================
# QUERY BUILDER
# =========================

def build_query(user_query: str, table_ref: str):
    """
    Replace TABLE placeholder with actual table reference
    """
    return user_query.replace("TABLE", table_ref)


# =========================
# QUERY EXECUTION
# =========================

def execute_query(con, query: str):
    """
    Execute query and return JSON-friendly result
    """
    result = con.execute(query).fetchall()
    columns = [desc[0] for desc in con.description]

    data = [dict(zip(columns, row)) for row in result]

    return data


# =========================
# MAIN SERVICE FUNCTION
# =========================

def run_query_service(payload: dict):
    """
    Main function to be called by FastAPI route
    """
    try:
        # Extract payload
        user_id = payload["user_id"]
        dataset = payload["dataset"]
        user_query = payload["query"]
        file_type = payload.get("file_type", "csv")  # default csv

        # Validate query
        validate_query(user_query)

        # Initialize DuckDB
        con = init_duckdb_connection()

        # Build S3 path
        s3_path = build_s3_path(user_id, dataset, file_type)

        # Get table reference
        table_ref = get_table_reference(s3_path, file_type)

        # Build final query
        final_query = build_query(user_query, table_ref)

        # Execute
        data = execute_query(con, final_query)

        return {
            "status": "success",
            "row_count": len(data),
            "data": data
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }