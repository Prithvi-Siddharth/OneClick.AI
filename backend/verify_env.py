import os
from dotenv import load_dotenv

# Path logic from main.py
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
print(f"Checking for .env at: {env_path}")
print(f"File exists: {os.path.exists(env_path)}")

# Load
load_dotenv(env_path)

# Check keys (masked)
access_key = os.getenv("AWS_ACCESS_KEY_ID")
secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
region = os.getenv("AWS_REGION")

print(f"AWS_ACCESS_KEY_ID: {'SET' if access_key else 'NOT SET'}")
print(f"AWS_SECRET_ACCESS_KEY: {'SET' if secret_key else 'NOT SET'}")
print(f"AWS_REGION: {region}")

if access_key:
    print(f"First 4 chars of Access Key: {access_key[:4]}")
