# Cognita Meeting Audio Data Engineering Pipeline

This project implements a full audio processing pipeline for meeting recordings, using MinIO for object storage and Python worker scripts for each stage. It follows the architecture and steps described in the technical documentation.

## Prerequisites

- **Docker** (for MinIO)
- **ffmpeg** and **ffprobe** (must be installed and on your PATH)
- **Python 3.8+**
- Python packages: `boto3`, `botocore`, etc. Install with:
  ```bash
  pip install -r shared/requirements.txt
  ```

## Setup

1. **Start MinIO locally:**
   ```bash
   docker-compose up -d minio
   ```
   This will start MinIO on `localhost:9000` (console at `localhost:9001`).

2. **Set environment variables:**
   These are set automatically by the orchestrator and workers, but you can export them for manual runs:
   ```bash
   set MINIO_ENDPOINT=localhost
   set MINIO_ACCESS_KEY=minioadmin
   set MINIO_SECRET_KEY=minioadmin123
   set MINIO_BUCKET=raw_meeting
   ```

3. **Install ffmpeg/ffprobe:**
   - Windows: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH.
   - Linux/macOS: Use your package manager (`apt install ffmpeg`, `brew install ffmpeg`).

## Running the Pipeline

1. **Place your MP3 file in `raw_audio_example/`** (or use the provided example).

2. **Run the orchestrator:**
   ```bash
   python run_pipeline.py
   # Or specify your own mp3 file:
   python run_pipeline.py raw_audio_example/yourfile.mp3
   ```

This will:
- Create the MinIO bucket (if missing)
- Convert the MP3 to WAV (16kHz mono, s16)
- Upload to `raw/meeting1.wav` in MinIO
- Run each worker in sequence:
  - **Ingest:** Handoff to next stage
  - **Preprocessing:** Clean/filter audio (highpass, lowpass, volume adjust)
  - **Validation:** Check duration, sample rate, channels, format
  - **Audio Extractor:** Standardize format (16kHz, mono, 16-bit WAV)
- Final output: `audio_extracted/meeting1.wav` in your MinIO bucket

## Inspecting Results

- Access MinIO at [http://localhost:9000](http://localhost:9000) (login: minioadmin/minioadmin123)
- Download and listen to the processed audio files

### Downloading the Extracted Audio

After running the pipeline, the final extracted audio is stored at `s3://raw-audio-meetings/audio_extracted/meeting1.wav`.

To download it locally:

1. **Using MinIO Console:**
   - Go to [http://localhost:9000](http://localhost:9000)
   - Login with `minioadmin` / `minioadmin123`
   - Navigate to the `raw-audio-meetings` bucket
   - Go to the `audio_extracted/` folder
   - Download `meeting1.wav`

2. **Using MinIO Client (mc):**
   - Install MinIO Client: `wget https://dl.min.io/client/mc/release/linux-amd64/mc && chmod +x mc`
   - Configure: `mc alias set local http://localhost:9000 minioadmin minioadmin123`
   - Download: `mc cp local/raw-audio-meetings/audio_extracted/meeting1.wav ./meeting1_extracted.wav`

3. **Using Python (boto3):**
   ```python
   import boto3
   from botocore.client import Config

   s3 = boto3.client(
       's3',
       endpoint_url='http://localhost:9000',
       aws_access_key_id='minioadmin',
       aws_secret_access_key='minioadmin123',
       config=Config(signature_version='s3v4'),
       region_name='us-east-1'
   )
   s3.download_file('raw-audio-meetings', 'audio_extracted/meeting1.wav', 'meeting1_extracted.wav')
   ```

### Playing the Audio with MPlayer

Once downloaded, play the extracted audio using MPlayer:

```bash
mplayer meeting1_extracted.wav
```

- Ensure MPlayer is installed: `sudo apt install mplayer` (on Ubuntu/Debian) or equivalent for your OS.
- For additional options, e.g., to check audio info: `mplayer -identify meeting1_extracted.wav`

## Troubleshooting

- If a worker fails, check the console output for error messages (e.g., ffmpeg/ffprobe not found, invalid audio format)
- Ensure Docker and MinIO are running
- Ensure ffmpeg/ffprobe are installed and on PATH

## Extending the Pipeline

- To add more stages (e.g., normalization, chunking), create new worker scripts and update the orchestrator.
- Replace demo logic in workers with advanced audio processing as needed.

## License

MIT
