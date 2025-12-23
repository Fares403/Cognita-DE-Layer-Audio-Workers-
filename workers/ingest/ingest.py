
import os
import boto3
from botocore.client import Config
import sys

def main():
    minio_endpoint = os.environ.get("MINIO_ENDPOINT", "localhost")
    minio_access_key = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key = os.environ.get("MINIO_SECRET_KEY", "minioadmin123")
    minio_bucket = os.environ.get("MINIO_BUCKET", "raw-audio-meetings")

    s3 = boto3.client(
        's3',
        endpoint_url=f'http://{minio_endpoint}:9000',
        aws_access_key_id=minio_access_key,
        aws_secret_access_key=minio_secret_key,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )

    # For demo: expect a file 'raw/meeting1.wav' in the bucket
    input_key = 'raw/meeting1.wav'
    output_key = 'preprocessed/meeting1.wav'
    local_file = '/tmp/meeting1.wav'

    print(f"[Ingest] Downloading {input_key} from bucket {minio_bucket}...")
    try:
        s3.download_file(minio_bucket, input_key, local_file)
        print(f"[Ingest] File downloaded: {local_file}")
    except Exception as e:
        print(f"[Ingest] ERROR: Could not download {input_key}: {e}")
        sys.exit(1)

    # For ingest, just re-upload to next stage (simulate handoff)
    print(f"[Ingest] Uploading to {output_key}...")
    s3.upload_file(local_file, minio_bucket, output_key)
    print(f"[Ingest] Done. Output: {output_key}")

if __name__ == "__main__":
    main()