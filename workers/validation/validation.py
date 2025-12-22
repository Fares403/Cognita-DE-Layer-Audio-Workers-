
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

    input_key = 'validated/meeting1.wav'
    output_key = 'extracted/meeting1.wav'
    local_file = '/tmp/meeting1_validated.wav'
    local_out = '/tmp/meeting1_extracted.wav'

    print(f"[Validation] Downloading {input_key} from bucket {minio_bucket}...")
    try:
        s3.download_file(minio_bucket, input_key, local_file)
        print(f"[Validation] File downloaded: {local_file}")
    except Exception as e:
        print(f"[Validation] ERROR: Could not download {input_key}: {e}")
        return

    # Real validation: use ffprobe to check duration, sample rate, channels, format
    import subprocess
    import json
    ffprobe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,format_name:stream=sample_rate,channels",
        "-of", "json",
        local_file
    ]
    print(f"[Validation] Running ffprobe: {' '.join(ffprobe_cmd)}")
    try:
        result = subprocess.check_output(ffprobe_cmd)
        info = json.loads(result)
        fmt = info.get("format", {})
        streams = info.get("streams", [])
        if streams:
            stream = streams[0]
            sample_rate = int(stream.get("sample_rate", 0))
            channels = int(stream.get("channels", 0))
        else:
            sample_rate = 0
            channels = 0
        duration = float(fmt.get("duration", 0))
        format_name = fmt.get("format_name", "")
        print(f"[Validation] duration={duration}s, sample_rate={sample_rate}, channels={channels}, format={format_name}")
        if not (30 <= duration <= 4*3600):
            print(f"[Validation] ERROR: Duration out of bounds (must be 30s-4h)")
            sys.exit(1)
        if sample_rate != 16000:
            print(f"[Validation] ERROR: Sample rate must be 16000 Hz")
            sys.exit(1)
        if channels != 1:
            print(f"[Validation] ERROR: Must be mono audio (1 channel)")
            sys.exit(1)
        if "wav" not in format_name:
            print(f"[Validation] ERROR: Must be WAV format")
            sys.exit(1)
        print(f"[Validation] File is valid. Proceeding to next stage.")
        # For demo, just copy file
        with open(local_file, 'rb') as fsrc, open(local_out, 'wb') as fdst:
            fdst.write(fsrc.read())
        print(f"[Validation] Uploading to {output_key}...")
        s3.upload_file(local_out, minio_bucket, output_key)
        print(f"[Validation] Done. Output: {output_key}")
    except Exception as e:
        print(f"[Validation] ERROR: ffprobe failed or file invalid: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()