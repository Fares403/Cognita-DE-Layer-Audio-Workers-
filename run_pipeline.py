#!/usr/bin/env python3
import os
import sys
import subprocess
import shlex
import boto3
from botocore.client import Config
import tempfile
import pathlib

# Orchestrator: creates bucket, converts mp3 to wav, uploads, runs workers sequentially.
# Usage: python run_pipeline.py [path/to/file.mp3]

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin123")
BUCKET = os.environ.get("MINIO_BUCKET", "raw-audio-meetings")

# Worker commands (relative to this file)
ROOT = pathlib.Path(__file__).parent
INGEST = [sys.executable, str(ROOT / "workers" / "ingest" / "ingest.py")]
PREPROCESS = [sys.executable, str(ROOT / "workers" / "preprocessing" / "preprocessing.py")]
AUDIO_NORMALIZER = [sys.executable, str(ROOT / "workers" / "audio_normalizer" / "audio_normalizer.py")]
AUDIO_CHUNKER = [sys.executable, str(ROOT / "workers" / "audio_chunker" / "audio_chunker.py")]
VALIDATE = [sys.executable, str(ROOT / "workers" / "validation" / "validation.py")]
AUDIO_EXTRACT = [sys.executable, str(ROOT / "workers" / "audio_extractor" / "audio_extractor.py")]


def check_ffmpeg():
    try:
        subprocess.check_output(["ffmpeg", "-version"])  # must be in PATH
        return True
    except Exception:
        return False


def ensure_bucket(s3, bucket):
    existing = s3.list_buckets()
    for b in existing.get("Buckets", []):
        if b.get("Name") == bucket:
            print(f"Bucket '{bucket}' already exists")
            return
    print(f"Creating bucket '{bucket}'")
    s3.create_bucket(Bucket=bucket)


def convert_mp3_to_wav(src_mp3_path, out_wav_path):
    # Use ffmpeg commandline for deterministic conversion
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src_mp3_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        str(out_wav_path),
    ]
    print("Converting MP3 -> WAV:", " ".join(shlex.quote(c) for c in cmd))
    subprocess.check_call(cmd)


def upload_file(s3, bucket, key, local_path):
    print(f"Uploading {local_path} to s3://{bucket}/{key}")
    s3.upload_file(str(local_path), bucket, key)


def run_worker(cmd, env=None):
    env_vars = os.environ.copy()
    if env:
        env_vars.update(env)
    print(f"Running worker: {' '.join(cmd)}")
    subprocess.check_call(cmd, env=env_vars)


def main():
    # discover mp3
    if len(sys.argv) > 1:
        src_mp3 = pathlib.Path(sys.argv[1])
    else:
        # fallback to example in raw_audio_example
        example_dir = ROOT / "raw_audio_example"
        files = list(example_dir.glob("*.mp3"))
        if not files:
            print("No mp3 provided and no example mp3 found in raw_audio_example/")
            sys.exit(1)
        src_mp3 = files[0]

    if not src_mp3.exists():
        print(f"MP3 file not found: {src_mp3}")
        sys.exit(1)

    if not check_ffmpeg():
        print("ffmpeg not found in PATH. Please install ffmpeg to convert audio.")
        sys.exit(1)

    session = boto3.session.Session()
    s3 = session.client(
        's3',
        endpoint_url=f'http://{MINIO_ENDPOINT}:9000',
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )

    ensure_bucket(s3, BUCKET)

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = pathlib.Path(tmpdir) / "meeting1.wav"
        # convert
        convert_mp3_to_wav(src_mp3, wav_path)

        # upload to raw/meeting1.wav
        upload_file(s3, BUCKET, "raw/meeting1.wav", wav_path)

    # environment for workers
    worker_env = {
        "MINIO_ENDPOINT": MINIO_ENDPOINT,
        "MINIO_ACCESS_KEY": MINIO_ACCESS_KEY,
        "MINIO_SECRET_KEY": MINIO_SECRET_KEY,
        "MINIO_BUCKET": BUCKET,
    }

    # Run ingest -> preprocessing -> validation -> extractor -> normalizer -> chunker
    try:
        run_worker(INGEST, env=worker_env)
        run_worker(PREPROCESS, env=worker_env)
        run_worker(VALIDATE, env=worker_env)
        run_worker(AUDIO_EXTRACT, env=worker_env)
        run_worker(AUDIO_NORMALIZER, env=worker_env)
        run_worker(AUDIO_CHUNKER, env=worker_env)
    except subprocess.CalledProcessError as e:
        print(f"Worker failed with exit code {e.returncode}")
        sys.exit(1)

    print("Pipeline finished. Final processed chunks should be at:")
    print(f"s3://{BUCKET}/chunks/meeting1/chunk_XXX.wav")


if __name__ == "__main__":
    main()
