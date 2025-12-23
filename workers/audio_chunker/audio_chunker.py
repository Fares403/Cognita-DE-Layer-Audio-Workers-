import os
import boto3
from botocore.client import Config
import subprocess
import sys
import tempfile
import json
import math
import pathlib

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

    input_key = 'normalized/meeting1.wav'
    local_file = '/tmp/meeting1_for_chunking.wav'

    print(f"[AudioChunker] Downloading {input_key} from bucket {minio_bucket}...")
    try:
        s3.download_file(minio_bucket, input_key, local_file)
        print(f"[AudioChunker] File downloaded: {local_file}")
    except Exception as e:
        print(f"[AudioChunker] ERROR: Could not download {input_key}: {e}")
        sys.exit(1)

    # Get audio duration using ffprobe
    ffprobe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        local_file
    ]
    
    print(f"[AudioChunker] Getting audio duration...")
    try:
        result = subprocess.check_output(ffprobe_cmd)
        info = json.loads(result)
        duration = float(info.get("format", {}).get("duration", 0))
        print(f"[AudioChunker] Audio duration: {duration:.2f} seconds")
    except Exception as e:
        print(f"[AudioChunker] ERROR: ffprobe failed to get duration: {e}")
        sys.exit(1)

    # Calculate chunk parameters
    chunk_duration = 120  # 2 minutes = 120 seconds
    num_chunks = math.ceil(duration / chunk_duration)
    
    print(f"[AudioChunker] Will create {num_chunks} chunks of {chunk_duration} seconds each")
    
    # Create chunks directory for temporary files
    with tempfile.TemporaryDirectory() as tmpdir:
        chunk_files = []
        
        # Create each chunk
        for i in range(num_chunks):
            start_time = i * chunk_duration
            
            # For the last chunk, use the remaining duration
            if i == num_chunks - 1:
                chunk_duration_actual = duration - start_time
            else:
                chunk_duration_actual = chunk_duration
            
            chunk_filename = f"chunk_{i+1:03d}.wav"
            chunk_path = pathlib.Path(tmpdir) / chunk_filename
            
            # Use ffmpeg to extract the specific time segment
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", local_file,
                "-ss", str(start_time),
                "-t", str(chunk_duration_actual),
                "-ac", "1", "-ar", "16000", "-sample_fmt", "s16",
                str(chunk_path)
            ]
            
            print(f"[AudioChunker] Creating chunk {i+1}/{num_chunks}: {start_time:.1f}s - {start_time + chunk_duration_actual:.1f}s")
            try:
                subprocess.check_call(ffmpeg_cmd)
                chunk_files.append(chunk_path)
                print(f"[AudioChunker] Chunk {i+1} created: {chunk_filename}")
            except Exception as e:
                print(f"[AudioChunker] ERROR: Failed to create chunk {i+1}: {e}")
                sys.exit(1)
        
        # Upload all chunks to MinIO
        for i, chunk_path in enumerate(chunk_files):
            chunk_key = f'chunks/meeting1/chunk_{i+1:03d}.wav'
            print(f"[AudioChunker] Uploading {chunk_path} to {chunk_key}...")
            try:
                s3.upload_file(str(chunk_path), minio_bucket, chunk_key)
                print(f"[AudioChunker] Uploaded chunk {i+1} to {chunk_key}")
            except Exception as e:
                print(f"[AudioChunker] ERROR: Failed to upload chunk {i+1}: {e}")
                sys.exit(1)
    
    print(f"[AudioChunker] Successfully created and uploaded {num_chunks} chunks")
    print(f"[AudioChunker] Chunks are available at: s3://{minio_bucket}/chunks/meeting1/chunk_XXX.wav")

if __name__ == "__main__":
    main()
