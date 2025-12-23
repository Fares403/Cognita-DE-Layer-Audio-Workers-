
import os
import boto3
from botocore.client import Config
import shutil
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

    input_key = 'validated/meeting1.wav'
    output_key = 'extracted/meeting1.wav'
    local_file = '/tmp/meeting1_validated.wav'
    local_out = '/tmp/meeting1_extracted.wav'

    print(f"[AudioExtractor] Downloading {input_key} from bucket {minio_bucket}...")
    try:
        s3.download_file(minio_bucket, input_key, local_file)
        print(f"[AudioExtractor] File downloaded: {local_file}")
    except Exception as e:
        print(f"[AudioExtractor] ERROR: Could not download {input_key}: {e}")
        sys.exit(1)

    # Real extraction: convert to 16kHz, mono, 16-bit WAV using ffmpeg
    import subprocess
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", local_file,
        "-ac", "1", "-ar", "16000", "-sample_fmt", "s16",
        local_out
    ]
    print(f"[AudioExtractor] Running ffmpeg: {' '.join(ffmpeg_cmd)}")
    try:
        subprocess.check_call(ffmpeg_cmd)
        print(f"[AudioExtractor] Extraction done. Output: {local_out}")
    except Exception as e:
        print(f"[AudioExtractor] ERROR: ffmpeg failed: {e}")
        sys.exit(1)

    print(f"[AudioExtractor] Uploading to {output_key}...")
    s3.upload_file(local_out, minio_bucket, output_key)
    print(f"[AudioExtractor] Done. Output: {output_key}")

if __name__ == "__main__":
    main()