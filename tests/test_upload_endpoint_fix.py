import sys
from unittest.mock import MagicMock

# Mock boto3 and pandas to avoid import errors in environment where they might be missing
sys.modules["boto3"] = MagicMock()
sys.modules["pandas"] = MagicMock()

from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
import os

client = TestClient(app)

@patch("app.main.get_current_user_id")
@patch("app.main.get_db")
@patch("app.main.process_and_save_dataset")
@patch("app.main.os.getenv")
def test_upload_dataset_appends_extension(mock_getenv, mock_process, mock_get_db, mock_get_user_id):
    # Mock environment variables
    mock_getenv.return_value = "test-bucket"
    
    # Mock user authentication
    mock_get_user_id.return_value = 123
    mock_db = MagicMock()
    mock_get_db.return_value = iter([mock_db])
    
    # Mock User query
    mock_user = MagicMock()
    mock_user.user_id = 123
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    # Mock S3/Service call
    mock_process.return_value = MagicMock()

    # Form data
    files = {'dataset_file': ('test.csv', b'content', 'text/csv')}
    data = {
        'datasetFilename': 'my_cool_dataset', # No extension provided by user
        'datasetDescription': 'Test description'
    }

    # Perform request
    response = client.post("/upload_dataset", data=data, files=files, follow_redirects=False)

    # Match 200 OK for JSON
    assert response.status_code == 200
    assert response.json()["message"] == "Upload successful"

    # Verify that process_and_save_dataset was called with the filename having extension
    mock_process.assert_called_once()
    call_args = mock_process.call_args[1]
    
    print(f"Called with filename: {call_args.get('filename')}")
    assert call_args['filename'] == 'my_cool_dataset.csv'

@patch("app.main.get_current_user_id")
@patch("app.main.get_db")
@patch("app.main.process_and_save_dataset")
@patch("app.main.os.getenv")
def test_upload_dataset_keeps_existing_extension(mock_getenv, mock_process, mock_get_db, mock_get_user_id):
    # Mock environment variables
    mock_getenv.return_value = "test-bucket"
    
    # Mock user authentication
    mock_get_user_id.return_value = 123
    mock_db = MagicMock()
    mock_get_db.return_value = iter([mock_db])
    
    # Mock User query
    mock_user = MagicMock()
    mock_user.user_id = 123
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    # Mock S3/Service call
    mock_process.return_value = MagicMock()

    # Form data
    files = {'dataset_file': ('test.csv', b'content', 'text/csv')}
    data = {
        'datasetFilename': 'already_has_ext.csv', # Extension ALREADY provided
        'datasetDescription': 'Test description'
    }

    # Perform request
    response = client.post("/upload_dataset", data=data, files=files, follow_redirects=False)

    # Match 200 OK for JSON
    assert response.status_code == 200

    # Verify that extension is NOT duplicated
    mock_process.assert_called_once()
    call_args = mock_process.call_args[1]
    
    print(f"Called with filename: {call_args.get('filename')}")
    assert call_args['filename'] == 'already_has_ext.csv'
