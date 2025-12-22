
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

    input_key = 'preprocessed/meeting1.wav'
    output_key = 'validated/meeting1.wav'
    local_file = '/tmp/meeting1.wav'
    local_out = '/tmp/meeting1_validated.wav'

    print(f"[Preprocessing] Downloading {input_key} from bucket {minio_bucket}...")
    try:
        s3.download_file(minio_bucket, input_key, local_file)
        print(f"[Preprocessing] File downloaded: {local_file}")
    except Exception as e:
        print(f"[Preprocessing] ERROR: Could not download {input_key}: {e}")
        sys.exit(1)

    # Real preprocessing: clean/filter audio using ffmpeg
    # ffmpeg -i input.mp3 -af "highpass=f=80,lowpass=f=16000,volume=-1dB" -ar 16000 -ac 1 output.wav
    import subprocess
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", local_file,
        "-af", "highpass=f=80,lowpass=f=16000,volume=-1dB",
        "-ar", "16000", "-ac", "1",
        local_out
    ]
    print(f"[Preprocessing] Running ffmpeg: {' '.join(ffmpeg_cmd)}")
    try:
        subprocess.check_call(ffmpeg_cmd)
        print(f"[Preprocessing] Preprocessing done. Output: {local_out}")
    except Exception as e:
        print(f"[Preprocessing] ERROR: ffmpeg failed: {e}")
        sys.exit(1)

    print(f"[Preprocessing] Uploading to {output_key}...")
    s3.upload_file(local_out, minio_bucket, output_key)
    print(f"[Preprocessing] Done. Output: {output_key}")

if __name__ == "__main__":
    main()