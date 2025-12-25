# Data Engineering Layer — Final Documentation (Cognita Meeting Platform)

Purpose
- Convert raw meeting audio → canonical, normalized, chunked artifacts + metadata ready for AI layers (STT, Diarization, Summarization, RAG).
- Provide deterministic replay, idempotency, and fault tolerance with minimal complexity.

Scope
- DE workers: Ingest Worker, Preprocessing Worker, Validation Worker, Audio Extractor, Audio Normalizer, Audio Chunker.
- Controllers & managers: Processing Controller (Retry, Replay, Recovery), Processing Metadata Manager.
- Storage & infra: S3/MinIO, PostgreSQL (+pgvector), Redis, Kafka, Docker, Prometheus/Grafana, ELK.

Contents
1. Overview (quick)
2. Per-worker spec (steps, tools, idempotency, retries, proof-of-implementation)
3. Metadata & storage schema (essential SQL)
4. Failure/Retry & Replay rules
5. Observability & Deliverables
6. Minimal worker pattern + useful CLI snippets

1 — Overview (concise)
- Event-driven pipeline: Meeting Service → meeting.uploaded.v1 → DE workers via Kafka.
- Workers are stateless; state tracked in PostgreSQL and short-lived Redis keys for idempotency.
- Files live in S3; Kafka messages carry references & metadata only.

2 — Per-worker specification

A. Ingest Worker (entrypoint)
- Purpose: validate upload event, create initial processing_metadata row, emit meeting.ingested.v1.
- Input: HTTP upload callback / S3 notification.
- Steps:
  1. Validate event payload (meeting_id, uploader, timestamp, s3_path).
  2. Insert processing_metadata row (current_stage = "INGESTED", retry_count=0) in DB (transactional).
  3. Emit Kafka meeting.ingested.v1 after DB commit.
- Tools: Web API (Flask/Express), Kafka producer, Postgres.
- Idempotency: DB unique constraint on meeting_id; Redis optional guard for duplicate webhook.
- Proof: ensure DB insert completes before Kafka produce.

B. Preprocessing Worker
- Purpose: lightweight denoise, DC-offset removal, sample rate quick normalization (if cheap).
- Input: S3 reference to raw file.
- Steps:
  1. Acquire Redis idempotency key: key = "{meeting_id}:preprocess:{source_etag}".
  2. Download S3 object to /tmp.
  3. Run ffmpeg/sox/RNNoise transforms.
  4. Upload cleaned temp to S3: /processed/{meeting_id}/preprocessed.wav.
  5. Emit audio.extracted.v1 after updating processing_metadata.
- Tools: ffmpeg, sox, RNNoise (optional), boto3/minio client, Redis, Kafka.
- Retry: exponential backoff; increment processing_metadata.retry_count.
- Metrics: preprocessing_duration_seconds, preprocessing_failures_total.
- CLI proof:
  - ffmpeg -i input -af "highpass=f=80, lowpass=f=16000, volume=-1dB" -ar 16000 -ac 1 /tmp/preprocessed.wav

C. Validation Worker
- Purpose: assert audio meets bounds and required metadata.
- Input: preprocessed S3 path.
- Steps:
  1. Redis guard: "{meeting_id}:validate:{s3_path_hash}".
  2. ffprobe to extract duration, sample rate, channels.
  3. Validate duration ∈ [min,max], sample rate, channel count, and metadata presence.
  4. On pass: emit audio.extracted.v1 after updating DB to next stage.
  5. On fail: mark processed_files/processing_metadata as FAILED and emit error event.
- Tools: ffprobe/ffmpeg, Kafka, Postgres, Redis.
- Proof:
  - ffprobe -v error -show_entries format=duration,sample_rate -of json input.wav

D. Audio Extractor
- Purpose: decode any container/codec → canonical 16kHz, mono, 16-bit PCM WAV.
- Input: validated S3 file.
- Steps:
  1. Acquire idempotency key: "{meeting_id}:extract:{sha256(src)}".
  2. Download, decode with ffmpeg to /tmp/audio.wav.
  3. Upload canonical file to S3: /processed/{meeting_id}/audio.wav.
  4. Update processed_files/processing_metadata and emit audio.extracted.v1.
- Tools: ffmpeg, tempfile, S3 client, Kafka, Postgres.
- CLI proof:
  - ffmpeg -i input.mp4 -ac 1 -ar 16000 -sample_fmt s16 /tmp/audio.wav

E. Audio Normalizer
- Purpose: trim long silence, normalize loudness (RMS/EBU), enforce format.
- Input: /processed/{meeting_id}/audio.wav
- Steps:
  1. Redis guard: "{meeting_id}:normalize:{audio_sha}".
  2. Run silence trimming (sox/ffmpeg) + ebur128 normalization or replaygain.
  3. Upload /processed/{meeting_id}/normalized.wav.
  4. Emit audio.normalized.v1 and update DB.
- Tools: sox, ffmpeg, libebur128, S3.
- CLI proof:
  - sox audio.wav normalized.wav silence 1 0.1 1% reverse silence 1 0.1 1% reverse
  - or ffmpeg -i audio.wav -af "silenceremove=stop_periods=-1:stop_threshold=0.01" normalized.wav

F. Audio Chunker
- Purpose: split normalized audio into ≤15 min chunks with 10–30s overlap; create processed_files rows before generation.
- Input: normalized.wav
- Steps:
  1. Compute duration = D. chunk_len = min(15min, configured). overlap = 10–30s.
  2. Calculate chunk_count = ceil(D / (chunk_len - overlap)).
  3. Pre-create DB rows in processed_files for each chunk with status = PENDING (transactional).
  4. For i in range(chunk_count):
     - Acquire Redis per-chunk key: "{meeting_id}:chunk:{i}".
     - Set processed_files.status = PROCESSING (SELECT FOR UPDATE).
     - Run ffmpeg -ss {start} -t {chunk_len} -i normalized.wav chunk_{i}.wav
     - Upload to S3: /processed/{meeting_id}/chunks/{chunk_id}.wav
     - Update processed_files.status = COMPLETED and set worker_id, duration.
     - Update processing_metadata.last_chunk_id = i.
     - Emit audio.chunked.v1 with chunk metadata.
  5. If interrupted mid-loop, replay resumes from processing_metadata.last_chunk_id + 1.
- Tools: ffmpeg, Postgres, Redis, S3, Kafka.
- CLI proof:
  - ffmpeg -ss {start_seconds} -t {chunk_len_seconds} -i normalized.wav chunk_{i}.wav
- Idempotency: DB unique constraint processed_files(meeting_id, chunk_id) + Redis guard.

G. Processing Metadata Manager (DB + API)
- Purpose: single source of truth for meeting pipeline progress and retries.
- Responsibilities:
  - Schema: processing_metadata(meeting_id PK, current_stage, last_chunk_id, retry_count, last_error, updated_at).
  - Provide atomic claim semantics: SELECT ... FOR UPDATE when advancing stage.
  - Expose small API for workers to claim/release stage or read progress.
- Best practice: always update DB before emitting Kafka; emit only after commit.

H. Processing Controller (Retry · Replay · Recovery)
- Purpose: detect stuck meetings, handle transient failures, and resume failed stages from last checkpoint.
- Responsibilities:
  - Monitor processing_metadata for stalled or failed stages.
  - Detect processing_metadata.status = PROCESSING entries with stale updated_at (heartbeat missing).
  - Trigger automatic replay/retry for idempotent failures.
  - Manual requeue capability for operators via CLI/API.
- Behavior:
  - Periodic scan: SELECT meeting_id WHERE updated_at < now()-threshold AND retry_count < MAX_RETRIES AND current_stage != COMPLETED.
  - For chunked failures: re-enqueue chunk events starting at last_chunk_id+1.
  - Use Redis replay guard: "{meeting_id}:replay:{stage}:{attempt}".
  - Increment processing_metadata.retry_count for each replay attempt; alert on threshold breach (MAX_RETRIES = 3).
  - Emit failure events (e.g., meeting.processing.failed) for non-retriable errors.
- Tools: scheduler job, Kafka producer/consumer, Postgres, Redis, alerting system.

3 — Metadata & storage (essential SQL snippets)

A. processed_files (chunk-level)
```sql
CREATE TABLE processed_files (
  meeting_id TEXT NOT NULL,
  chunk_id INT NOT NULL,
  s3_path TEXT,
  duration_seconds INT,
  status TEXT NOT NULL, -- PENDING, PROCESSING, COMPLETED, FAILED
  worker_id TEXT,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now(),
  PRIMARY KEY(meeting_id, chunk_id)
);
```

B. processing_metadata (stage-level)
```sql
CREATE TABLE processing_metadata (
  meeting_id TEXT PRIMARY KEY,
  current_stage TEXT,
  last_chunk_id INT DEFAULT 0,
  retry_count INT DEFAULT 0,
  last_error TEXT,
  updated_at TIMESTAMP DEFAULT now()
);
```

4 — Failure, Retry & Replay rules (concise)
- Idempotency: Redis keys per stage/resource + DB uniqueness.
- Retry policy:
  - Worker-level retriable errors → exponential backoff; update processing_metadata.retry_count.
  - Non-retriable → mark FAILED and notify (alerting).
- Replay:
  - Replay Controller triggers re-enqueue events for remaining work.
  - For chunked stages, it resumes starting from last_chunk_id+1.
- Crash handling:
  - Workers must write status=PROCESSING then periodically heartbeat; Replay Controller detects stale PROCESSING entries and reclaims.

5 — Observability & Deliverables
- Metrics (Prometheus):
  - per worker: attempts_total, failures_total, duration_seconds (histogram).
  - pipeline: meetings_processed_total, chunks_processed_total.
- Logs: structured (json) with fields: meeting_id, chunk_id, stage, worker_id, trace_id.
- Tracing: add trace_id to Kafka headers.
- Deliverables per worker:
  - Dockerfile + health endpoint (/health).
  - Unit tests for boundary conditions (duration limits, chunk math).
  - Integration test simulating S3 input and Kafka events.
  - Runbook: manual requeue steps, where to view retry counts, how to trigger replay.

6 — Minimal worker pattern (Python pseudocode)
```python
# Example: worker pattern (simplified)
# filepath: workers/templates/worker_template.py
# ...existing code...
import hashlib, time
from kafka import KafkaConsumer, KafkaProducer
import boto3, redis, psycopg2, subprocess

REDIS_KEY = f"{meeting_id}:{stage}:{hashlib.sha256(resource.encode()).hexdigest()}"

if redis.setnx(REDIS_KEY, 1):
    redis.expire(REDIS_KEY, 24*3600)
else:
    return  # idempotent skip

# claim DB row (SELECT FOR UPDATE) -> update status=PROCESSING
# download from S3
# run local processing (ffmpeg/sox)
# upload to S3
# update DB status=COMPLETED / set last_chunk_id
# produce Kafka event (after DB commit)
# redis.delete(REDIS_KEY)
# ...existing code...
```

7 — Useful commands & formulas
- Chunk count: chunk_count = ceil(total_seconds / (chunk_len_seconds - overlap_seconds))
- ffmpeg decode to canonical WAV:
  - ffmpeg -i input -ac 1 -ar 16000 -sample_fmt s16 /tmp/audio.wav
- ffmpeg chunk:
  - ffmpeg -ss {start} -t {duration} -i normalized.wav /tmp/chunk_{i}.wav
- sox silence trim:
  - sox in.wav out.wav silence 1 0.1 1% reverse silence 1 0.1 1% reverse

8 — Best practices (short)
- Emit events only after DB commit.
- Pre-create processed_files rows before chunk generation.
- Use DB transactions + SELECT FOR UPDATE for stage claims.
- Keep Redis TTL short; treat Redis as hint (DB is source of truth).
- Keep workers stateless and idempotent.

9 — Minimal acceptance criteria for graduation project
- End-to-end demo: upload an audio file → pipeline produces chunks and transcripts.
- Reproducible local stack: docker-compose with MinIO, Postgres, Redis, Kafka, one worker.
- Tests: unit tests for validation & chunking logic; integration test for end-to-end flow.
- Documentation: this file + runbook for replay actions.

References / Tools (summary)
- ffmpeg, sox, RNNoise (optional)
- S3 / MinIO, Postgres (+pgvector), Redis, Kafka
- Docker, Docker Compose, Prometheus/Grafana, ELK

This document is intentionally focused and actionable: each worker has explicit steps, tools, idempotency keys, minimal proofs (CLI/pseudo-code) and the required DB schema to support replay and completion detection. Use it as the final deliverable for your grad project DE layer.