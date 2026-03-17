# Query Service Implementation Guide

This guide explains how to use the `QueryService` to enable "Chat with My Data" and interactive SQL querying within the Data Catalog.

## 1. Overview: What is DuckDB?
DuckDB is a high-performance analytical database that runs *in-process*. For our platform, its most powerful feature is the ability to query CSV and Parquet files directly from **AWS S3** without needing to import them into a traditional database first.

## 2. Service Interface: `run_query_service`
Located in: [query_service.py]

### 2.2 Internal Logic: How it Works
The `run_query_service` function acts as an orchestrator. Here is the step-by-step internal workflow:

1.  **Extraction**: It extracts `user_id`, `dataset`, `query`, and `file_type` from the input payload.
2.  **Pre-Validation**: Before touching the database, it calls `validate_query()` to ensure the command is a `SELECT` and contains the `TABLE` keyword.
3.  **DuckDB Initialization**:
    *   It creates a fresh in-memory DuckDB connection.
    *   It installs/loads the `httpfs` extension (required for S3).
    *   It sets AWS credentials (`s3_access_key_id`, etc.) for the session using environment variables.
4.  **Path Construction**: It builds a wildcard S3 path: `s3://bucket/user_id/dataset/*.extension`. This allows DuckDB to treat multiple files in a folder as a single dataset.
5.  **Dynamic Table Mapping**:
    *   It wraps the S3 path in a DuckDB function: `read_csv_auto()` for CSVs or `read_parquet()` for Parquet.
    *   Example: `read_csv_auto('s3://my-bucket/123/my-data/*.csv')`.
6.  **Query Injection**: It replaces the `TABLE` placeholder in the user's SQL with this generated function call.
7.  **Analytical Execution**: The final query (e.g., `SELECT * FROM read_csv_auto(...)`) is executed. DuckDB streams the data from S3, filters it, and returns the result.
8.  **Serialization**: The results are converted into a list of dictionaries (JSON-ready) and returned.

---

### 2.3 Sample Input Formats (JSON)
The backend expects a POST body in JSON format.

**Example 1: Querying a CSV Dataset**
```json
{
  "user_id": "user_99",
  "dataset": "monthly_sales",
  "query": "SELECT product, SUM(revenue) FROM TABLE GROUP BY product",
  "file_type": "csv"
}
```

**Example 2: Querying a Parquet Dataset (Optimized)**
```json
{
  "user_id": "user_99",
  "dataset": "sensor_logs",
  "query": "SELECT timestamp, temperature FROM TABLE WHERE temperature > 100",
  "file_type": "parquet"
}
```

---

## 3. Use Case: Chat with My Data
The "Chat with My Data" button provides an entry point for users to interact with their dataset using standard SQL queries. 

### Implementation Strategy
1.  **Entry Point**: The "Chat" button redirects the user to the **Interactive Query Tool**.
2.  **User Input**: The user writes and executes SQL queries directly against the dataset.
3.  **UI Feedback**: Results are returned in a tabular format (JSON) and displayed in the chat/results window.

**Workflow Example:**
1. User clicks "Chat with my Data" on a specific dataset.
2. The UI opens a SQL editor pre-validated for that dataset.
3. The user executes: `SELECT * FROM TABLE ORDER BY date DESC LIMIT 10`.
4. The service returns the most recent 10 rows.

---

## 4. Advanced SQL Patterns
Since DuckDB is SQL-compliant, you can use advanced analytical functions:

### Time-Based Aggregation
```sql
SELECT 
    date_trunc('month', sale_date) as month, 
    SUM(amount) as total_sales 
FROM TABLE 
GROUP BY 1 
ORDER BY 1
```

### Complex Filtering & Subqueries
```sql
SELECT * FROM TABLE 
WHERE category IN ('Electronics', 'Home') 
  AND price > (SELECT AVG(price) FROM TABLE)
```

### Handling Missing Data
```sql
SELECT 
    COALESCE(column_name, 'Unknown') as cleaned_col,
    COUNT(*) 
FROM TABLE 
GROUP BY 1
```

---

## 5. Robust Integration (FastAPI Boilerplate)

Here is a more detailed example including Pydantic models for validation:

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Any
from app.services.query_service import run_query_service

router = APIRouter()

class QueryPayload(BaseModel):
    user_id: str
    dataset: str
    query: str
    file_type: Optional[str] = "csv"

class QueryResponse(BaseModel):
    status: str
    row_count: int
    data: List[dict]
    message: Optional[str] = None

@router.post("/execute-sql", response_model=QueryResponse)
async def execute_user_sql(payload: QueryPayload):
    # The run_query_service function handles DuckDB connection and S3 auth
    result = run_query_service(payload.dict())
    
    if result["status"] == "error":
        raise HTTPException(
            status_code=400, 
            detail={
                "error": "SQL_EXECUTION_FAILED",
                "message": result["message"]
            }
        )
        
    return result
```

---

## 6. Error Handling
The service returns a dictionary:
*   **Success**: `{"status": "success", "row_count": N, "data": [...]}`
*   **Error**: `{"status": "error", "message": "Detailed error description"}`

Common errors include:
*   Missing `TABLE` keyword.
*   Schema mismatches (e.g., querying a column that doesn't exist).
*   Permission issues with S3 credentials.
