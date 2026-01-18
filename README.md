# OneClick.AI

OneClick.AI is a **No-Code Machine Learning Platform** designed to democratize AI. It allows users to upload datasets, automatically preprocess them, and build robust machine learning models without writing a single line of code.

## 🚀 Features

*   **Robust Data Ingestion**:
    *   Secure file uploads to our data and model catelogs.
    *   Metadata tracking (row counts, schema, size)
    *   Support for **CSV**, **JSON**, and **Excel** formats.
    *   Memory-efficient processing for large datasets.
*   **Dataset Management**:
    *   View your uploaded files catalog.
    *   Preview file contents directly in the UI (via API).
*   **User Management**:
    *   Secure Registration & Login functionality with JWT authentication.
*   More features (preprocessing, auto-training) coming soon!

## 🛠️ Tech Stack

*   **Backend**: Python, FastAPI
*   **Database**: TiDB (SQLAlchemy ORM)
*   **Cloud Storage**: AWS S3 (boto3)
*   **Data Processing**: Pandas
*   **Authentication**: JWT
*   **Machine Learning**: Scikit-learn, tensorflow

## ⚡ Getting Started

Follow these instructions to run the project locally.

### Prerequisites

*   Python 3.9+
*   A TiDB cluster (or compatible MySQL database).
*   An AWS S3 bucket.

### 1. Installation

Clone the repository and install dependencies:

```bash
pip install -r requirements.txt
```

### 2. Environment Configuration

Create a `.env` file in the root directory with the following credentials:
```ini
# Database (TiDB)
DB_HOST=...
DB_PORT=4000
DB_USERNAME=...
DB_PASSWORD=...
DB_NAME=...
DB_SSL_CA=backend/certs/tidb-ca.pem

# AWS Storage
S3_BUCKET_NAME=your-bucket-name
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1
```

### 3. Run the Server

Navigate to the backend directory and start the Uvicorn server:

```bash
cd backend
uvicorn app.main:app --reload
```

The server will start at [http://127.0.0.1:8000](http://127.0.0.1:8000).

## 📖 API Documentation

Once the server is running, you can explore the interactive API documentation at:
*   **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
*   **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

## 📁 Project Structure

*   `backend/app/main.py`: Entry point of the API.
*   `backend/app/models.py`: Database models (User, Dataset, Experiment).
*   `backend/app/services/s3_operations.py`: Core logic for S3 uploads and reading.


## Development team

*   Viswanath Balla
*   Aditya Yarakaraju
*   Prithvi Siddharth Manepally