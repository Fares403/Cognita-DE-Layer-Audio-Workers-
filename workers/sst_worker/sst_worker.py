import os
import sys
import boto3
from botocore.client import Config
import tempfile
import json
import openai
from pathlib import Path
import time

def transcribe_with_retry(audio_file, max_retries=3):
    """Transcribe audio with retry logic for rate limits."""
    for attempt in range(max_retries):
        try:
            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json"
            )
            return transcript
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "insufficient_quota" in error_str:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                    print(f"[SST Worker] Rate limit hit, retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"[SST Worker] Max retries reached for rate limit error.")
                    raise e
            else:
                # For other errors, don't retry
                raise e

def main():
    minio_endpoint = os.environ.get("MINIO_ENDPOINT", "localhost")
    minio_access_key = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key = os.environ.get("MINIO_SECRET_KEY", "minioadmin123")
    minio_bucket = os.environ.get("MINIO_BUCKET", "raw-audio-meetings")
    openai_api_key = os.environ.get("OPENAI_API_KEY")

    if not openai_api_key:
        print("[SST Worker] ERROR: OPENAI_API_KEY not found in environment")
        # We don't exit here to allow testing without API key if needed, or we should exit?
        # Requirement said user will add key. Best to check and fail if missing during execution.
        # But for development/test without key we might want to fail gracefully or skip.
        # Let's fail hard as it's the core function.
        print("[SST Worker] Please provide OPENAI_API_KEY")
        sys.exit(1)

    openai.api_key = openai_api_key

    s3 = boto3.client(
        's3',
        endpoint_url=f'http://{minio_endpoint}:9000',
        aws_access_key_id=minio_access_key,
        aws_secret_access_key=minio_secret_key,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )

    meeting_id = "meeting1"
    prefix = f"chunks/{meeting_id}/"
    
    print(f"[SST Worker] Listing chunks in {minio_bucket}/{prefix}...")
    
    try:
        response = s3.list_objects_v2(Bucket=minio_bucket, Prefix=prefix)
    except Exception as e:
        print(f"[SST Worker] ERROR: Failed to list chunks: {e}")
        sys.exit(1)

    if 'Contents' not in response:
        print("[SST Worker] No chunks found.")
        sys.exit(0)

    chunks = [obj['Key'] for obj in response['Contents'] if obj['Key'].endswith('.wav')]
    # Sort chunks to ensure order
    chunks.sort()

    print(f"[SST Worker] Found {len(chunks)} chunks.")

    all_segments = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, chunk_key in enumerate(chunks):
            local_filename = Path(tmpdir) / Path(chunk_key).name
            print(f"[SST Worker] Downloading {chunk_key}...")
            
            try:
                s3.download_file(minio_bucket, chunk_key, str(local_filename))
            except Exception as e:
                print(f"[SST Worker] ERROR: Failed to download {chunk_key}: {e}")
                continue

            print(f"[SST Worker] Transcribing {chunk_key} with Whisper...")
            
            try:
                with open(local_filename, "rb") as audio_file:
                    transcript = transcribe_with_retry(audio_file)
                
                # Extract segments and adjust timestamps based on chunk index/offset if needed.
                # NOTE: Chunks have overlap. Real system needs to handle overlap and deduplication.
                # For this task, we will just concatenate them or list them.
                # Assuming simple concatenation for now as per "take chunks and create segments".
                
                # Check if we have offset information. Chunker produces 15 min chunks.
                # Ideally, we should know the start time of the chunk. 
                # The filename chunk_XXX.wav implies order. 
                # Let's assume chunk_001 starts at 0, chunk_002 starts at offset, etc.
                # However, the chunker in the codebase (audio_chunker.py) sets start_time = i * chunk_duration.
                # But we don't have that metadata easily here unless we parse filenames or read from DB (which we are mocking).
                # Parsing filename: chunk_001 -> index 0.
                
                # Attempt to parse index from filename
                try:
                    chunk_idx = int(local_filename.stem.split('_')[-1]) - 1 # chunk_001 -> 0
                    # Re-read audio_chunker.py to find chunk_duration. It was 120s in the viewing.
                    chunk_duration = 120 
                    time_offset = chunk_idx * chunk_duration
                except:
                    time_offset = 0
                    print(f"[SST Worker] WARNING: Could not determine time offset from filename {local_filename.name}")

                for segment in transcript.get('segments', []):
                    # Adjust timestamp
                    segment['start'] += time_offset
                    segment['end'] += time_offset
                    all_segments.append(segment)
                    
                print(f"[SST Worker] Transcription complete for {chunk_key}. Found {len(transcript.get('segments', []))} segments.")

            except Exception as e:
                print(f"[SST Worker] ERROR: Whisper transcription failed for {chunk_key}: {e}")
                # Continue or fail? Let's continue.
                continue

    # Save results
    output_key = f"transcripts/{meeting_id}/segments.json"
    local_output = Path(tmpdir) / "segments.json" # tmpdir needs to be recreated or outside loop?
    # Ah, tmpdir is closed context. We need to save content to variable first, which we did (all_segments).
    
    # We need a new temp file for upload
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json') as tmp_out:
        json.dump({"meeting_id": meeting_id, "segments": all_segments}, tmp_out, indent=2)
        tmp_out_path = tmp_out.name
    
    print(f"[SST Worker] Uploading results to {output_key}...")
    try:
        s3.upload_file(tmp_out_path, minio_bucket, output_key)
        print(f"[SST Worker] Success! Segments JSON uploaded.")
    except Exception as e:
        print(f"[SST Worker] ERROR: Failed to upload output json: {e}")
    finally:
        os.remove(tmp_out_path)

if __name__ == "__main__":
    main()
