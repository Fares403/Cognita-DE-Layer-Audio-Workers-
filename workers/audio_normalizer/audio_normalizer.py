import os
import boto3
from botocore.client import Config
import subprocess
import sys
import tempfile
import json

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

    input_key = 'extracted/meeting1.wav'
    output_key = 'normalized/meeting1.wav'
    local_file = '/tmp/meeting1_extracted.wav'
    local_out = '/tmp/meeting1_normalized.wav'

    print(f"[AudioNormalizer] Downloading {input_key} from bucket {minio_bucket}...")
    try:
        s3.download_file(minio_bucket, input_key, local_file)
        print(f"[AudioNormalizer] File downloaded: {local_file}")
    except Exception as e:
        print(f"[AudioNormalizer] ERROR: Could not download {input_key}: {e}")
        sys.exit(1)

    # Audio normalization: remove silence using ffmpeg silenceremove filter
    # This removes silence at the beginning, end, and in the middle of audio
    # Parameters: 
    # - stop_periods=-1: scan whole file
    # - stop_duration=0.5: require 0.5s of silence to remove
    # - stop_threshold=-35dB: threshold for silence detection
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", local_file,
        "-af", "silenceremove=stop_periods=-1:stop_duration=0.5:stop_threshold=-35dB:start_periods=1:start_duration=0.5:start_threshold=-35dB",
        "-ar", "16000", "-ac", "1",
        local_out
    ]
    
    print(f"[AudioNormalizer] Running silence removal: {' '.join(ffmpeg_cmd)}")
    try:
        subprocess.check_call(ffmpeg_cmd)
        print(f"[AudioNormalizer] Silence removal completed. Output: {local_out}")
    except Exception as e:
        print(f"[AudioNormalizer] ERROR: ffmpeg silence removal failed: {e}")
        sys.exit(1)

    print(f"[AudioNormalizer] Uploading to {output_key}...")
    s3.upload_file(local_out, minio_bucket, output_key)
    print(f"[AudioNormalizer] Done. Output: {output_key}")

if __name__ == "__main__":
    main()
