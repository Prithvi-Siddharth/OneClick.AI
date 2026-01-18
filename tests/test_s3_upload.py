import os
import io
from app.services.data_processing import process_and_save_dataset
from app.db import SessionLocal
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_manual_upload():
    print("Starting manual S3 upload test...")
    
    # Check credentials
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        print("ERROR: S3_BUCKET_NAME is not set in .env")
        return

    print(f"Target Bucket: {bucket}")
    
    # Create a dummy CSV file in memory
    csv_content = "col1,col2,col3\n1,2,3\n4,5,6"
    file_obj = io.BytesIO(csv_content.encode('utf-8'))
    
    # Mock parameters
    user_id = 999  # Test user
    filename = "test_data.csv"
    
    db = SessionLocal()
    try:
        dataset = process_and_save_dataset(
            db=db,
            user_id=user_id,
            file_obj=file_obj,
            filename=filename,
            bucket_name=bucket
        )
        print("--------------------------------------------------")
        print("SUCCESS!")
        print(f"Dataset ID: {dataset.id}")
        print(f"S3 Key:     {dataset.s3_key}")
        print(f"Row Count:  {dataset.row_count}")
        print(f"Schema:     {dataset.feature_schema}")
        print("--------------------------------------------------")
    except Exception as e:
        print("--------------------------------------------------")
        print("FAILED!")
        print(f"Error: {e}")
        print("--------------------------------------------------")
    finally:
        db.close()

if __name__ == "__main__":
    test_manual_upload()
