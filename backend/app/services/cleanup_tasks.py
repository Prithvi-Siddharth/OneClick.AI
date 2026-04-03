import os
import sys
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

# Add the project root to sys.path to allow running as a standalone script
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.db import SessionLocal
from app.models import TemporaryDataset
from app.services.s3_operations import s3_delete_object

def cleanup_expired_temp_data(hours_threshold: int = 6):
    """
    Search for temporary datasets older than the threshold and delete them from S3 and the DB.
    """
    db: Session = SessionLocal()
    try:
        # 1. Calculate the expiration threshold
        threshold_time = datetime.utcnow() - timedelta(hours=hours_threshold)
        
        # 2. Find expired records in the 'temp' table
        expired_datasets = db.query(TemporaryDataset).filter(
            TemporaryDataset.upload_date < threshold_time
        ).all()
        
        if not expired_datasets:
            print(f"[{datetime.utcnow()}] No expired datasets found (Threshold: {hours_threshold}h).")
            return

        print(f"[{datetime.utcnow()}] Found {len(expired_datasets)} expired datasets. Starting cleanup...")

        deleted_count = 0
        for dataset in expired_datasets:
            try:
                # 3. Delete from S3 first
                print(f"  - Deleting S3 file: {dataset.s3_key} from bucket: {dataset.s3_bucket}")
                s3_delete_object(dataset.s3_bucket, dataset.s3_key)
                
                # 4. Delete the database record
                db.delete(dataset)
                deleted_count += 1
            except Exception as e:
                print(f"  - [ERROR] Failed to clean up dataset ID {dataset.id}: {str(e)}")
                continue

        # 5. Final commit to database
        db.commit()
        print(f"[{datetime.utcnow()}] Cleanup complete. Successfully removed {deleted_count} datasets.")
        
    except Exception as e:
        print(f"[{datetime.utcnow()}] Critical error during cleanup: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # You can pass the number of hours as an argument if needed, default is 24.
    hours = 24
    if len(sys.argv) > 1:
        try:
            hours = int(sys.argv[1])
        except ValueError:
            print("Invalid hours argument. Using default: 24")
            
    cleanup_expired_temp_data(hours)
