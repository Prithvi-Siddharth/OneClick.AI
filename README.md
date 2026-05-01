# <div align="center"> <i class="fas fa-project-diagram"></i> OneClick.AI </div>

<div align="center">
  <strong>Rapid No-Code Machine Learning Experimentation Platform</strong>
</div>

<div align="center">

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Storage: AWS S3](https://img.shields.io/badge/Storage-AWS_S3-232F3E?logo=amazons3&logoColor=white)](https://aws.amazon.com/s3/)
[![Database: TiDB](https://img.shields.io/badge/Database-TiDB-F15A24?logo=mysql&logoColor=white)](https://en.pingcap.com/tidb/)

</div>

---

## Project Overview

OneClick.AI is a powerful **no-code Machine Learning platform** designed for data scientists and MLOps teams to accelerate the bridge between raw data and production-ready models. By automating the "messy" parts of the ML lifecycle—data cleaning, feature engineering, and model selection—we allow you to focus on high-level strategy and results.

> **Our Mission:** To democratize advanced machine learning by providing a seamless, one-click interface for data ingestion, exploration, training, and deployment.

---

## 🚀 Key Features

### 📁 Advanced Data Catalog
*   **Hierarchical Management**: Organize your datasets into nested folders for better project governance.
*   **Centralized S3 Storage**: All data is securely stored in AWS S3 and tracked via TiDB for extreme scalability.
*   **Multi-format Support**: Native ingestion for **CSV**, **JSON**, and **Excel** files.
*   **In-Browser Preview**: Instantly view metadata (rows, size, schema) and sample data without downloading files.

### 📊 Interactive EDA & SQL Panel
*   **SQL Workbench**: Run DuckDB-powered SQL queries directly against your CSV/S3 data using the `data` alias.
*   **Dynamic Visualizations**: Generate Plotly-based histograms, scatter plots, and box plots with a single click.
*   **Auto-EDA Statistics**: Instant statistical summaries (Mean, Median, Std Dev, Variance) for numerical attributes.

### 🧠 Intelligent AutoML Pipeline
*   **Smart Preprocessing**: Handle missing values, encoding for categorical variables, and advanced feature engineering with just a few clicks.
*   **Algorithm Arena**: Train multiple state-of-the-art algorithms simultaneously (including Decision Tree, SVM, K-Nearest Neighbors).
*   **Target Selection UI**: intuitive interface to select your target variable and define the ML task (Classification/Regression).

### 🚀 One-Click Deployment (Upcoming)
*   **Instant REST Endpoints**: Deploy your best-performing models to a production-ready API with one click.
*   **Testing Playground**: Built-in specialized UI to test model predictions with manual inputs before full deployment.
*   **Performance Metrics**: Track R², RMSE, Accuracy, F1-Score, and more in detailed model report cards.

### 💬 Collaboration Tools
*   **Built-in AI Assistant**: An integrated LLM-powered chatbot to help you navigate data science concepts and platform features.
*   **Sticky Note System**: Save reminders, observations, and experimental hypotheses directly on your dashboard.

---

## 🛠️ Technology Stack

### Backend
*   **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (High-performance, asynchronous REST API)
*   **Database**: [TiDB](https://en.pingcap.com/tidb/) (Distributed SQL for massive scalability)
*   **ORM**: [SQLAlchemy](https://www.sqlalchemy.org/)
*   **Computation**: [Pandas](https://pandas.pydata.org/), [DuckDB](https://duckdb.org/), [NumPy](https://numpy.org/)
*   **Machine Learning**: [Scikit-learn](https://scikit-learn.org/)
### Frontend
*   **Structure**: HTML5, Semantic UI logic.
*   **Styling**: Vanilla CSS (Modern design with Dark Mode support).
*   **Templating**: [Jinja2](https://jinja.palletsprojects.com/)
*   **Charts**: [Plotly.js](https://plotly.com/javascript/)
*   **Icons**: [Font Awesome 6](https://fontawesome.com/)

### Infrastructure
*   **Storage**: [AWS S3](https://aws.amazon.com/s3/) (Cloud object storage)
*   **Authentication**: JWT (JSON Web Tokens) with secure cookie-based persistence.

---

## ⚡ Getting Started

### Prerequisites
*   Python 3.10 or higher.
*   An active AWS S3 bucket and credentials (IAM access keys).
*   A TiDB Cloud account (or a local MySQL cluster).

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/Prithvi-Siddharth/OneClick.AI.git
cd OneClick.AI

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

Create a `.env` file in the project root with the following structure:

```env
# TiDB / Database Credentials
DB_HOST=your-tidb-host
DB_PORT=4000
DB_USERNAME=your-username
DB_PASSWORD=your-password
DB_NAME=OneClickAI
DB_SSL_CA=backend/certs/tidb-ca.pem

# AWS Infrastructure
S3_BUCKET_NAME=your-ml-bucket
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_REGION=us-east-1

# Security
JWT_SECRET_KEY=your-very-long-secret-key
```

### 3. Running the Platform

```bash
cd backend
uvicorn app.main:app --reload
```

*   **Platform UI**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
*   **API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🧹 Maintenance Tasks

### Automatic Storage Optimization
To keep S3 costs low, a background task is available to prune expired temporary datasets.

```bash
# Manually trigger cleanup
cd backend
python -m app.services.cleanup_tasks
```

---

## 📁 Project Structure

```text
OneClick.AI/
├── backend/
│   ├── app/
│   │   ├── routers/       # API Route controllers
│   │   ├── services/      # Core ML/S3 logic
│   │   ├── templates/     # UI Templates (Jinja2)
│   │   ├── static/        # CSS/JS Assets
│   │   ├── models.py      # Database Schema
│   │   └── db.py          # Database Config
│   └── certs/             # SSL Certificates
├── tests/                 # Automated test suite
└── requirements.txt       # Project dependencies
```

---

## 👥 Development Team

*   **Viswanath Balla**
*   **Aditya Yarakaraju**
*   **Prithvi Siddharth Manepalli**

---

<div align="center">
  Built with ❤️ for the Machine Learning Community.
</div>
