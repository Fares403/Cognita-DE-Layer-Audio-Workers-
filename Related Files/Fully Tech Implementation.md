# Data Engineering Layer – Complete Documentation
## Cognita Meeting Platform

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Microservices Architecture](#microservices-architecture)
4. [System Components](#system-components)
5. [Worker Specifications](#worker-specifications)
6. [Data Storage & Metadata](#data-storage--metadata)
7. [Failure Handling & Recovery](#failure-handling--recovery)
8. [Implementation Examples](#implementation-examples)
9. [Monitoring & Observability](#monitoring--observability)
10. [Deployment & Operations](#deployment--operations)

---

## Executive Summary

The **Data Engineering (DE) Layer** is the foundation of the Cognita Meeting Platform. Its primary responsibility is to:

- **Ingest** raw meeting audio files from users
- **Validate** audio quality and format compliance
- **Normalize** audio to a standard format (16kHz, mono, 16-bit WAV)
- **Chunk** normalized audio into ≤15-minute segments for AI processing
- **Track** processing state to enable retry and recovery
- **Ensure** idempotent processing with deterministic replay capabilities

**Output:** Clean, chunked, metadata-rich audio ready for downstream AI layers (Speech-to-Text, Speaker Diarization, Summarization, Action Extraction, RAG).

**Key Characteristics:**
- Stateless, horizontally scalable workers
- Event-driven architecture via Kafka
- Metadata-driven orchestration via PostgreSQL
- Deterministic replay and fault tolerance
- Production-ready with minimal operational complexity

---

## Architecture Overview

### High-Level Flow

```
User Upload
    ↓
[Meeting Service] → Kafka: meeting.uploaded.v1
    ↓
[Ingest Worker] → Kafka: meeting.ingested.v1
    ↓
[Preprocessing] → [Validation] → [Audio Extractor] → [Normalizer] → [Chunker]
    ↓
S3 Storage + PostgreSQL Metadata
    ↓
Kafka: audio.chunked.v1 → AI Layers (STT, Diarization, Summarization)
    ↓
Processing Controller: Retry • Replay • Recovery (via Redis & Kafka)
```

### Core Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Object Storage** | S3 / MinIO | Store raw, normalized, and chunked audio |
| **Metadata Database** | PostgreSQL | Track processing state, chunks, retries |
| **Idempotency Cache** | Redis | Prevent duplicate processing during retries |
| **Event Transport** | Kafka | Decouple workers, enable event replay |
| **Containerization** | Docker + Docker Compose | Ensure reproducibility and local development |
| **Monitoring** | Prometheus + Grafana | Real-time observability and metrics |

---

## Microservices Architecture

### Service Decomposition

The Data Engineering Layer is designed as a **microservices architecture** where each worker operates as an independent, stateless service. This approach provides:

- **Independent Scaling:** Each worker can be scaled based on its specific load patterns
- **Technology Flexibility:** Different workers can use different programming languages or frameworks
- **Fault Isolation:** Failure in one worker doesn't cascade to others
- **Deployment Independence:** Services can be deployed, updated, and rolled back independently
- **Team Autonomy:** Different teams can own and maintain different services

### Service Boundaries

Each worker is a separate microservice with:

- **Dedicated Container:** Each worker runs in its own Docker container
- **Independent Database Access:** All services share PostgreSQL and Redis but with proper isolation
- **Event-Driven Communication:** Services communicate only through Kafka events
- **Health Checks:** Each service exposes `/health` endpoints for monitoring
- **Configuration Management:** Environment variables for service-specific settings

### Service Registry & Discovery

While not implemented in MVP, the architecture supports:

- **Service Mesh (Istio/Linkerd):** For advanced routing, load balancing, and observability
- **API Gateway:** For external service communication
- **Service Discovery:** Kubernetes DNS or Consul for dynamic service location

### Inter-Service Communication

**Synchronous Communication:**
- Workers query shared databases (PostgreSQL, Redis) for metadata
- Subscription Service provides feature flags
- Org Service validates assignees for action items

**Asynchronous Communication:**
- All processing triggers use Kafka events
- Workers emit events after successful processing
- Replay Controller monitors and re-emits events

### Data Consistency

**Eventual Consistency Model:**
- Workers update databases immediately after processing
- Event emission happens after database commits
- Replay ensures consistency on failures

**Transactional Boundaries:**
- Each worker's processing is atomic within its database transactions
- Cross-service consistency maintained through event-driven architecture

### Deployment Strategy

**Container Orchestration:**
- Kubernetes for production deployment
- Docker Compose for local development
- Helm charts for configuration management

**Scaling Patterns:**
- Horizontal Pod Autoscaling based on Kafka queue depth
- Vertical scaling for CPU-intensive workers (Audio Extractor)
- Spot instances for cost optimization

### Monitoring & Observability

**Service-Level Metrics:**
- Request/response rates per service
- Error rates and latency percentiles
- Resource utilization (CPU, memory, disk)

**Distributed Tracing:**
- Jaeger or Zipkin for request tracing across services
- Correlation IDs for tracking processing pipelines

### Security Considerations

**Service-to-Service Authentication:**
- Mutual TLS (mTLS) between services
- JWT tokens for API calls
- API keys for external integrations

**Network Security:**
- Service mesh encryption
- Network policies restricting communication
- Zero-trust architecture

### Migration Path

**From Monolith to Microservices:**
1. **Phase 1 (Current):** All workers as separate containers but shared codebase
2. **Phase 2:** Separate repositories and CI/CD pipelines per service
3. **Phase 3:** Independent deployment schedules and team ownership

This microservices approach ensures the Data Engineering Layer can evolve independently while maintaining compatibility with the broader AI-powered Meeting Intelligence Platform.

---

## System Components

### High-Level Flow

```
User Upload
    ↓
[Meeting Service] → Kafka: meeting.uploaded.v1
    ↓
[Ingest Worker] → Kafka: meeting.ingested.v1
    ↓
[Preprocessing] → [Validation] → [Audio Extractor] → [Normalizer] → [Chunker]
    ↓
S3 Storage + PostgreSQL Metadata
    ↓
Kafka: audio.chunked.v1 → AI Layers (STT, Diarization, Summarization)
    ↓
Processing Controller: Retry • Replay • Recovery (via Redis & Kafka)
```

### Core Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Object Storage** | S3 / MinIO | Store raw, normalized, and chunked audio |
| **Metadata Database** | PostgreSQL | Track processing state, chunks, retries |
| **Idempotency Cache** | Redis | Prevent duplicate processing during retries |
| **Event Transport** | Kafka | Decouple workers, enable event replay |
| **Containerization** | Docker + Docker Compose | Ensure reproducibility and local development |
| **Monitoring** | Prometheus + Grafana | Real-time observability and metrics |

---

## System Components

### 0. Input & Control Services

**Meeting Service**
- Responsible for receiving audio uploads and initiating DE pipeline
- Initiates: `meeting.uploaded.v1` event
- Receives: `meeting.processed.v1` event to mark meeting as PROCESSED
- Updates: Meeting status to PROCESSED in application database

**Subscription Service**
- Controls feature flags for optional AI enrichment workers
- Feature flags: `SUM` (Summarization), `ACT` (Action Detection), `RAG` (RAG Pipeline)
- Consumed by: Summarization, Action Detection, and RAG workers to determine if processing is enabled
- Integration: Query subscription tier for meeting's org, apply feature gate

**Org Service**
- Validates organization metadata and team assignments
- Consumed by: Action Detection Worker
- Validates assignees exist in organization before storing action items
- Returns: Org members list, team hierarchies for action assignment

### 1. S3 / MinIO (Object Storage)

**Responsibility:** Durable, scalable storage for all audio artifacts

| Path | Producer | Consumer | Purpose |
|------|----------|----------|---------|
| `/raw/{meeting_id}/upload.mp4` | User Upload | Preprocessing | Original uploaded file |
| `/processed/{meeting_id}/audio.wav` | Audio Extractor | Audio Normalizer | Standardized WAV |
| `/processed/{meeting_id}/normalized.wav` | Audio Normalizer | Audio Chunker | Normalized, silence-trimmed audio |
| `/processed/{meeting_id}/chunks/{chunk_id}.wav` | Audio Chunker | STT Worker | Individual audio chunks |

### 2. PostgreSQL (Metadata & State)

Two main tables drive the entire pipeline:

#### Table: `processed_files`
Tracks chunk-level processing status

```sql
CREATE TABLE processed_files (
  meeting_id TEXT NOT NULL,
  chunk_id INT NOT NULL,
  s3_path TEXT,
  duration_seconds INT,
  status TEXT CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
  worker_id TEXT,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now(),
  PRIMARY KEY(meeting_id, chunk_id)
);
```

#### Table: `processing_metadata`
Tracks overall meeting progress and stage completion

```sql
CREATE TABLE processing_metadata (
  meeting_id TEXT PRIMARY KEY,
  current_stage TEXT CHECK (current_stage IN ('INGESTED', 'VALIDATED', 'EXTRACTED', 'NORMALIZED', 'CHUNKED', 'COMPLETED')),
  last_chunk_id INT DEFAULT 0,
  retry_count INT DEFAULT 0,
  last_error TEXT,
  updated_at TIMESTAMP DEFAULT now()
);
```

### 3. Redis (Idempotency & Retry Coordination)

**Purpose:** Ultra-fast duplicate prevention and stage-level idempotency

```
Key Format: {meeting_id}:{stage}:{resource_hash}
TTL: 24 hours
Values: Simple presence check (SET if not exists)
```

**Usage Pattern:**
```python
idempotency_key = f"{meeting_id}:preprocess:{source_etag}"
if redis.setnx(idempotency_key, "1"):
    # Process the stage
else:
    # Skip (already processed)
```

### 4. Kafka (Event Transport)

**Purpose:** Decouple workers, enable asynchronous processing and replay

| Topic | Producer | Consumer | Payload |
|-------|----------|----------|---------|
| `meeting.uploaded.v1` | Meeting Service | Ingest Worker | `{meeting_id, s3_path, timestamp}` |
| `meeting.ingested.v1` | Ingest Worker | Preprocessing Worker | `{meeting_id, s3_path}` |
| `audio.extracted.v1` | Audio Extractor | Audio Normalizer | `{meeting_id, s3_path}` |
| `audio.normalized.v1` | Audio Normalizer | Audio Chunker | `{meeting_id, s3_path, duration}` |
| `audio.chunked.v1` | Audio Chunker | STT Worker | `{meeting_id, chunk_id, s3_path, start_time}` |
| `transcript.segments.v1` | STT Worker | Diarization Worker | `{meeting_id, chunk_id, segments}` |
| `transcript.diarized.v1` | Diarization Worker | Transcript Enrichment | `{meeting_id, transcript, speakers}` |
| `meeting.processed.v1` | Transcript Enrichment / Summarization | Meeting Service | `{meeting_id, status, summary_s3_path, actions, topics}` |

**Key Principles:** 
- Kafka carries references and metadata only, not large binary data
- Each stage emits an event AFTER successful database commits
- Processing Controller uses Kafka for event replay on failures
- All consumers must implement idempotency (via Redis keys)

---

## Worker Specifications

### Worker 1: Ingest Worker

**What it does:** Validates upload event, creates initial processing metadata record, triggers preprocessing pipeline.

**Input:** Kafka message `meeting.uploaded.v1` from Meeting Service

**Output:** Processing metadata record + emit `meeting.ingested.v1` event

**Workflow:**

1. **Receive Event:** Kafka message `meeting.uploaded.v1` with `meeting_id`, `s3_path`, `timestamp`
2. **Validate Payload:** Check meeting_id, uploader, timestamp, s3_path are present
3. **Check Idempotency:** Redis key `{meeting_id}:ingest:{source_etag}` (prevent duplicate ingestion)
4. **Create DB Record:** Insert into `processing_metadata` table with `current_stage = "INGESTED"`
5. **Update Database:** Set initial metadata (meeting_id, retry_count=0, last_error=null)
6. **Emit Event:** Produce Kafka event `meeting.ingested.v1` after DB commit
7. **Log:** Record ingestion event with tracing

**Tools Used:**
- Kafka consumer
- PostgreSQL
- Redis for idempotency
- Structured logging

**Idempotency:**
- DB unique constraint on `meeting_id`
- Redis guard prevents duplicate processing
- Safe to replay

**Failure Handling:**
- DB connection errors → worker exits, pod restart triggers replay
- Invalid payload → mark FAILED and emit error event
- Kafka produce failures → transaction rollback

---

### Worker 2: Preprocessing Worker

**What it does:** Cleans raw audio by removing noise, filtering artifacts, and preparing for standardization.

**Input:** Kafka message `meeting.ingested.v1` with S3 path to raw audio

**Output:** Cleaned audio → S3: `/processed/{meeting_id}/preprocessed.wav`

**Workflow:**

1. **Receive Event:** Kafka message `meeting.ingested.v1` with `meeting_id` and S3 path
2. **Check Idempotency:** Acquire Redis key `{meeting_id}:preprocess:{source_etag}`
   - If exists → skip (already processed)
   - If new → proceed
3. **Download:** Stream audio from S3 to `/tmp/{meeting_id}_raw.wav`
4. **Process:** Run ffmpeg/sox filters
   - Remove DC offset
   - Apply high-pass filter (80 Hz) to remove rumble
   - Apply low-pass filter (16kHz)
   - Reduce volume slightly to avoid clipping
5. **Upload:** Save cleaned audio to S3: `/processed/{meeting_id}/preprocessed.wav`
6. **Update Database:** Mark stage progress in `processing_metadata.current_stage`
7. **Emit Event:** Flow continues to next worker (Validation) via pipeline orchestration
8. **Clean Up:** Delete Redis key, clean `/tmp` files

**Tools Used:**
- `ffmpeg` / `sox` – Audio processing
- `boto3` – S3 client
- `redis-py` – Redis client
- `psycopg2` – PostgreSQL connection
- `confluent-kafka-python` – Kafka consumer

**CLI Proof (ffmpeg command):**
```bash
ffmpeg -i input.mp3 \
  -af "highpass=f=80,lowpass=f=16000,volume=-1dB" \
  -ar 16000 -ac 1 \
  /tmp/preprocessed.wav
```

**Idempotency:**
- Redis guard prevents duplicate processing
- If preprocessing fails and retries → same input produces same output
- No side effects on retry

**Failure Handling:**
- Transient errors (S3 timeout) → exponential backoff retry
- Permanent errors (invalid audio) → mark `processing_metadata.status = FAILED`
- Max retries exceeded → alert operators

**Metrics to Track:**
- `preprocessing_duration_seconds` (histogram)
- `preprocessing_failures_total` (counter)
- `preprocessing_retries_total` (counter)

---

### Worker 3: Validation Worker

**What it does:** Ensures audio meets quality requirements (duration, sample rate, format).

**Input:** Preprocessed audio from S3 at `/processed/{meeting_id}/preprocessed.wav`

**Output:** Validation result + metadata update + trigger Audio Extractor

**Workflow:**

1. **Receive Event:** Triggered by Preprocessing completion
2. **Check Idempotency:** Redis key `{meeting_id}:validate:{path_hash}`
3. **Probe Audio:** Use `ffprobe` to extract metadata
   ```bash
   ffprobe -v error -show_entries format=duration,sample_rate,channels -of json input.wav
   ```
4. **Validate Constraints:**
   - Duration: 30 seconds ≤ D ≤ 4 hours
   - Sample rate: ≥8kHz (preferably 16kHz or higher)
   - Channels: Mono or stereo acceptable
   - Codec: PCM WAV preferred
5. **Update Database:**
   - If valid → update `processing_metadata.current_stage = "VALIDATED"`
   - If invalid → mark `processing_metadata.status = FAILED` with reason
6. **Emit Result:** Trigger Audio Extractor on success
7. **Log:** Structured JSON logs with validation details

**Tools Used:**
- `ffprobe` – Audio metadata extraction
- `ffmpeg-python` wrapper
- PostgreSQL for state
- Redis for idempotency

**CLI Proof:**
```bash
ffprobe -v error \
  -show_entries format=duration,sample_rate,channels \
  -of json \
  input.wav
```

**Example Output:**
```json
{
  "format": {
    "duration": "3600.5",
    "sample_rate": "16000",
    "channels": 1
  }
}
```

**Idempotency:**
- Validation is deterministic (same audio → same result)
- Redis ensures only one validation attempt per file
- Safe to replay

**Failure Handling:**
- Invalid duration → log and mark FAILED (non-retriable)
- Missing metadata → attempt recovery or fail gracefully
- ffprobe failures (corrupted file) → mark FAILED + alert

---

### Worker 4: Audio Extractor

**What it does:** Decodes any audio format/codec into a standardized 16kHz, mono, 16-bit PCM WAV.

**Input:** Validated preprocessed audio from S3

**Output:** Standardized WAV file in S3 at `/processed/{meeting_id}/audio.wav` + emit `audio.extracted.v1`

**Workflow:**

1. **Receive Event:** Validation success trigger
2. **Check Idempotency:** Redis key `{meeting_id}:extract:{sha256(source)}`
3. **Download:** Stream file from S3 to `/tmp/{meeting_id}_preprocessed.wav`
4. **Decode:** Run ffmpeg to standardize format
   ```bash
   ffmpeg -i /tmp/{meeting_id}_preprocessed.wav \
     -ac 1 \
     -ar 16000 \
     -sample_fmt s16 \
     /tmp/audio.wav
   ```
5. **Verify:** Quick check that output WAV is valid (duration > 0, valid format)
6. **Upload:** S3 → `/processed/{meeting_id}/audio.wav`
7. **Update Database:**
   - Update `processing_metadata.current_stage = "EXTRACTED"`
8. **Emit Event:** `audio.extracted.v1` Kafka message
9. **Cleanup:** Remove `/tmp` files, delete Redis key

**Tools Used:**
- `ffmpeg` – Audio decoding/transcoding
- `boto3` – S3 operations
- `subprocess` – Execute ffmpeg
- PostgreSQL + Redis as above
- Kafka producer

**CLI Proof:**
```bash
ffmpeg -i input.wav \
  -ac 1 \
  -ar 16000 \
  -sample_fmt s16 \
  -loglevel error \
  /tmp/audio.wav
```

**Idempotency:**
- SHA256 of source file ensures same input → same hash → idempotent key
- Same output WAV on retry (deterministic ffmpeg)
- Safe to replay

**Failure Handling:**
- ffmpeg codec errors → mark FAILED (often non-retriable)
- S3 upload timeouts → retry with exponential backoff
- Disk space issues → fail and alert

---

### Worker 5: Audio Normalizer

**What it does:** Trims leading/trailing silence, normalizes volume to standard level (EBU R128 -23 LUFS).

**Input:** Extracted WAV from S3 at `/processed/{meeting_id}/audio.wav`

**Output:** Normalized WAV in S3 at `/processed/{meeting_id}/normalized.wav` + emit `audio.normalized.v1`

**Workflow:**

1. **Receive Event:** `audio.extracted.v1` Kafka message
2. **Check Idempotency:** Redis key `{meeting_id}:normalize:{audio_sha}`
3. **Download:** Stream audio from S3 to `/tmp/audio.wav`
4. **Trim Silence:** Use sox to remove leading/trailing silence
   ```bash
   sox audio.wav normalized_trimmed.wav \
     silence 1 0.1 1% \
     reverse \
     silence 1 0.1 1% \
     reverse
   ```
5. **Normalize Volume:** Use ffmpeg + ebur128 to normalize loudness
   ```bash
   ffmpeg -i normalized_trimmed.wav \
     -af "ebur128=loudness_range=True" \
     normalized.wav
   ```
   Or simpler alternative:
   ```bash
   ffmpeg -i normalized_trimmed.wav \
     -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
     normalized.wav
   ```
6. **Verify:** Check output duration > 5 seconds (sanity check)
7. **Upload:** S3 → `/processed/{meeting_id}/normalized.wav`
8. **Update Database:** `processing_metadata.current_stage = "NORMALIZED"`
9. **Emit Event:** `audio.normalized.v1` Kafka message
10. **Cleanup:** Remove temp files

**Tools Used:**
- `sox` – Silence trimming
- `ffmpeg` + `ebur128` – Loudness normalization
- S3, Redis, PostgreSQL
- Kafka producer

**CLI Proof:**
```bash
# Trim silence
sox audio.wav trimmed.wav silence 1 0.1 1% reverse silence 1 0.1 1% reverse

# Normalize loudness
ffmpeg -i trimmed.wav \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
  normalized.wav
```

**Idempotency:**
- Input SHA determines idempotency
- Silence trimming + normalization are deterministic
- Safe to replay

**Failure Handling:**
- Audio too short after trimming → mark FAILED
- ffmpeg/sox not installed → container health check fails
- S3 operations → retry logic

---

### Worker 6: Audio Chunker

**What it does:** Splits normalized audio into ≤15-minute chunks with 10-30 second overlap for context continuity. Pre-creates database records before chunking to support crash recovery.

**Input:** `audio.normalized.v1` Kafka message with S3 path and total duration

**Output:** Individual chunk files in S3 at `/processed/{meeting_id}/chunks/chunk_{i}.wav` + `processed_files` metadata rows + emit `audio.chunked.v1`

**Workflow:**

1. **Receive Event:** `audio.normalized.v1` with S3 path and total duration
2. **Calculate Chunks:**
   ```
   chunk_length = 15 minutes (900 seconds)
   overlap = 20 seconds
   chunk_step = chunk_length - overlap = 880 seconds
   total_chunks = ceil(total_duration / chunk_step)
   ```
3. **Pre-create Database Rows:**
   ```sql
   FOR i IN 0..total_chunks-1:
     INSERT INTO processed_files 
     (meeting_id, chunk_id, status, created_at, updated_at)
     VALUES (?, i, 'PENDING', now(), now())
   ```
   (Single transaction for atomicity)

4. **For Each Chunk (i = 0 to total_chunks-1):**
   
   a. **Check Idempotency:** Redis key `{meeting_id}:chunk:{i}`
   
   b. **Claim Chunk:** `SELECT ... FOR UPDATE` on `processed_files` where `chunk_id = i` and `status = 'PENDING'`
   
   c. **Update Status:** Set `status = 'PROCESSING'`, `worker_id = ${worker_instance}`
   
   d. **Calculate Time Bounds:**
      ```
      start_time = i * chunk_step
      end_time = min(start_time + chunk_length, total_duration)
      duration = end_time - start_time
      ```
   
   e. **Extract Chunk:** ffmpeg
      ```bash
      ffmpeg -ss {start_time} -t {duration} \
        -i normalized.wav \
        -c:a pcm_s16le \
        chunk_{i}.wav
      ```
   
   f. **Upload:** S3 → `/processed/{meeting_id}/chunks/chunk_{i}.wav`
   
   g. **Update Database:**
      ```sql
      UPDATE processed_files 
      SET status = 'COMPLETED', 
          s3_path = 'path/to/chunk_{i}.wav',
          duration_seconds = duration,
          worker_id = ?,
          updated_at = now()
      WHERE meeting_id = ? AND chunk_id = ?
      ```
   
   h. **Update Metadata:**
      ```sql
      UPDATE processing_metadata 
      SET last_chunk_id = i
      WHERE meeting_id = ?
      ```
   
   i. **Emit Event:** Kafka `audio.chunked.v1` per chunk
      ```json
      {
        "meeting_id": "meet_123",
        "chunk_id": 5,
        "s3_path": "/processed/meet_123/chunks/chunk_5.wav",
        "start_time_seconds": 4400,
        "duration_seconds": 900,
        "total_chunks": 10
      }
      ```
   
   j. **Delete Redis Key:** Mark chunk complete

5. **On Completion:** Update `processing_metadata.current_stage = "CHUNKED"`

6. **Cleanup:** Remove `/tmp` files

**Tools Used:**
- `ffmpeg` – Chunk extraction
- PostgreSQL + `SELECT FOR UPDATE` – Atomic chunk claiming
- Redis – Per-chunk idempotency
- Kafka producer – Event emission
- `boto3` – S3 upload

**CLI Proof:**
```bash
# Extract chunk 0: 0s to 900s (15 min)
ffmpeg -ss 0 -t 900 \
  -i normalized.wav \
  -c:a pcm_s16le \
  chunk_0.wav

# Extract chunk 1: 880s to 900s duration (overlap: 20s with chunk 0)
ffmpeg -ss 880 -t 900 \
  -i normalized.wav \
  -c:a pcm_s16le \
  chunk_1.wav
```

**Example Scenario:**
- Meeting duration: 1 hour 10 minutes (4200 seconds)
- Chunk length: 15 min (900 sec), overlap: 20 sec
- Chunk step: 880 sec
- Total chunks: ceil(4200 / 880) = 5

| Chunk | Start (s) | Duration (s) | End (s) |
|-------|-----------|--------------|---------|
| 0 | 0 | 900 | 900 |
| 1 | 880 | 900 | 1780 |
| 2 | 1760 | 900 | 2660 |
| 3 | 2640 | 900 | 3540 |
| 4 | 3520 | 680 | 4200 |

**Idempotency:**
- Per-chunk Redis key ensures each chunk processed exactly once
- Pre-created `processed_files` rows ensure crash safety
- If worker crashes mid-loop → on restart, `processing_metadata.last_chunk_id` tells replay controller which chunks remain
- SELECT FOR UPDATE prevents race conditions with retry

**Failure Handling:**
- Worker crashes at chunk 3 → restart resumes chunk 4+
- ffmpeg fails on specific chunk → mark that chunk FAILED, continue if allowed
- S3 upload timeout → retry chunk upload
- Kafka emit fails → chunk marked PROCESSING, Replay Controller detects stale entries

---

### Worker 7: Processing Metadata Manager

**What it does:** Central source of truth for pipeline progress. Provides atomic operations for stage advancement and retry coordination.

**Responsibilities:**
1. Track `processing_metadata` table (current stage, last chunk, retry count)
2. Provide API for workers to claim/update stages atomically
3. Enable Replay Controller to detect stale or failed stages

**Key Operations:**

**Advance Stage (Atomic):**
```python
def advance_stage(meeting_id, new_stage):
    with db.transaction():
        metadata = db.query("""
            SELECT * FROM processing_metadata 
            WHERE meeting_id = %s 
            FOR UPDATE
        """, meeting_id)
        db.execute("""
            UPDATE processing_metadata 
            SET current_stage = %s, updated_at = now()
            WHERE meeting_id = %s
        """, new_stage, meeting_id)
```

**Increment Retry:**
```python
def increment_retry(meeting_id, error_msg):
    with db.transaction():
        db.execute("""
            UPDATE processing_metadata 
            SET retry_count = retry_count + 1, 
                last_error = %s,
                updated_at = now()
            WHERE meeting_id = %s
        """, error_msg, meeting_id)
```

**Read Progress:**
```python
def get_progress(meeting_id):
    return db.query("""
        SELECT current_stage, last_chunk_id, retry_count 
        FROM processing_metadata 
        WHERE meeting_id = %s
    """, meeting_id)
```

**Tools:**
- PostgreSQL with transactions
- Structured logging

---





**What it does:** Central source of truth for pipeline progress. Provides atomic operations for stage advancement and retry coordination.

**Responsibilities:**
1. Track `processing_metadata` table (current stage, last chunk, retry count)
2. Provide API for workers to claim/update stages atomically
3. Enable Replay Controller to detect stale or failed stages

**Key Operations:**

**Advance Stage (Atomic):**
```python
def advance_stage(meeting_id, new_stage):
    with db.transaction():
        metadata = db.query("""
            SELECT * FROM processing_metadata 
            WHERE meeting_id = %s 
            FOR UPDATE
        """, meeting_id)
        
        if metadata.current_stage == expected_stage:
            db.execute("""
                UPDATE processing_metadata 
                SET current_stage = %s, 
                    updated_at = now(),
                    retry_count = 0
                WHERE meeting_id = %s
            """, new_stage, meeting_id)
            return True
        else:
            return False  # Stage already advanced by another worker
```

**Increment Retry:**
```python
def increment_retry(meeting_id, error_msg):
    with db.transaction():
        db.execute("""
            UPDATE processing_metadata 
            SET retry_count = retry_count + 1,
                last_error = %s,
                updated_at = now()
            WHERE meeting_id = %s
        """, error_msg, meeting_id)
```

**Read Progress:**
```python
def get_progress(meeting_id):
    return db.query("""
        SELECT current_stage, last_chunk_id, retry_count 
        FROM processing_metadata 
        WHERE meeting_id = %s
    """, meeting_id)
```

**Tools:**
- PostgreSQL with transactions
- Structured logging

---

### Worker 8: Processing Controller (Retry · Replay · Recovery)

**What it does:** Monitors stuck or failed stages and automatically resumes from the last successful checkpoint. Detects stale workers and triggers automatic replay.

**Workflow:**

1. **Periodic Scan (every 5 minutes):**
   ```sql
   SELECT meeting_id, current_stage, last_chunk_id, retry_count
   FROM processing_metadata
   WHERE updated_at < now() - interval '5 minutes'
     AND retry_count < 3
     AND current_stage != 'COMPLETED'
   ```

2. **Stale Worker Detection:**
   - If `processed_files.status = 'PROCESSING'` and `updated_at > 30 minutes ago`
   - → Worker crashed, mark chunk as `FAILED` and trigger replay

3. **For Each Stuck Meeting:**
   
   a. **Determine Resume Point:**
      - If `current_stage = "CHUNKED"` and `last_chunk_id = 3` → resume chunk 4+
      - Else → restart the current stage from beginning
   
   b. **Acquire Replay Guard:** Redis key `{meeting_id}:replay:{stage}:{attempt}`
      - Prevents duplicate replays
   
   c. **Re-emit Events:** 
      - For CHUNKED stage: emit `audio.chunked.v1` for chunks `last_chunk_id+1` onward
      - For other stages: re-emit the stage trigger event to Kafka
   
   d. **Increment Retry:** Update `processing_metadata.retry_count += 1`
   
   e. **Check Threshold:** If `retry_count >= MAX_RETRIES (3)` → mark FAILED and emit alert
   
   f. **Log & Alert:**
      - Log: "Replaying {meeting_id} stage={stage} attempt={retry_count}"
      - If retries exceed threshold → alert operators with detailed error context

**Tools:**
- PostgreSQL for queries and state management
- Redis for replay guards
- Kafka producer for event re-emission
- Scheduler (cron or APScheduler)
- Structured logging + alerting system

**Example Scenario:**
```
1. Audio chunker fails at chunk 5 (out of 10)
   processing_metadata shows: current_stage=CHUNKED, last_chunk_id=4, retry_count=0

2. Replay Controller (5 min later):
   - Acquires Redis key: {meeting_id}:replay:CHUNKED:1
   - Re-emits Kafka audio.chunked.v1 events for chunks 5-9
   - Updates processing_metadata: retry_count=1
   - STT Worker consumes events, processes chunks 5-9
   - Downstream workers proceed normally

3. If chunk 7 also fails:
   - processing_metadata: current_stage=CHUNKED, last_chunk_id=6, retry_count=1
   - Next scan (5 min later): Re-emit chunks 7-9
   - retry_count=2
   - If fails again: retry_count=3, then alert and mark FAILED
```

---

## Data Storage & Metadata

### PostgreSQL Schema

```sql
-- Track chunk-level processing
CREATE TABLE processed_files (
  meeting_id TEXT NOT NULL,
  chunk_id INT NOT NULL,
  s3_path TEXT,
  duration_seconds INT,
  status TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
  worker_id TEXT,
  error_message TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  updated_at TIMESTAMP NOT NULL DEFAULT now(),
  PRIMARY KEY(meeting_id, chunk_id),
  INDEX idx_status (status),
  INDEX idx_updated (updated_at)
);

-- Track overall meeting progress and retries
CREATE TABLE processing_metadata (
  meeting_id TEXT PRIMARY KEY,
  current_stage TEXT NOT NULL DEFAULT 'INGESTED'
    CHECK (current_stage IN ('INGESTED', 'VALIDATED', 'EXTRACTED', 'NORMALIZED', 'CHUNKED', 'COMPLETED')),
  last_chunk_id INT NOT NULL DEFAULT 0,
  retry_count INT NOT NULL DEFAULT 0,
  last_error TEXT,
  updated_at TIMESTAMP NOT NULL DEFAULT now(),
  INDEX idx_stage (current_stage),
  INDEX idx_updated (updated_at)
);

-- Create initial metadata row on upload
INSERT INTO processing_metadata (meeting_id, current_stage)
VALUES (?, 'INGESTED');
```

### Data Flow Example

**Meeting Upload (Ingest):**
```
User → Meeting Service (HTTP POST)
→ Kafka: meeting.uploaded.v1
→ Ingest Worker
→ PostgreSQL: INSERT processing_metadata (current_stage='INGESTED')
→ Kafka: meeting.ingested.v1
```

**Preprocessing Stage:**
```
Kafka: meeting.ingested.v1
→ Preprocessing Worker (Redis idempotency check)
→ S3: upload /processed/{meeting_id}/preprocessed.wav
→ PostgreSQL: UPDATE processing_metadata (current_stage='VALIDATED')
→ Validation Worker (ffprobe)
→ Audio Extractor (ffmpeg decode)
```

**Audio Extraction & Normalization:**
```
Audio Extractor
→ S3: upload /processed/{meeting_id}/audio.wav
→ Kafka: audio.extracted.v1
→ Audio Normalizer (sox + ffmpeg)
→ S3: upload /processed/{meeting_id}/normalized.wav
→ Kafka: audio.normalized.v1
```

**Chunking & AI Handoff:**
```
Kafka: audio.normalized.v1
→ Audio Chunker (pre-creates processed_files rows)
→ FOR i in 0..N: ffmpeg chunk, S3 upload, processed_files UPDATE
→ PostgreSQL: UPDATE processing_metadata (current_stage='CHUNKED', last_chunk_id=i)
→ Kafka: audio.chunked.v1 (per chunk)
→ STT Worker consumes chunks
→ Kafka: transcript.segments.v1
→ Diarization Worker
→ Kafka: transcript.diarized.v1
→ Transcript Enrichment
→ Subscription Service: feature flag checks (SUM, ACT, RAG)
→ Summarization, Action Detection (validate via Org Service), Topic Extraction workers (if enabled)
→ Kafka: meeting.processed.v1
→ Meeting Service: update meeting status to PROCESSED
```

**Replay on Failure:**
```
Replay Controller (periodic scan every 5 min)
→ SELECT WHERE updated_at < now() - 5min AND retry_count < 3
→ Redis: acquire replay guard {meeting_id}:replay:{stage}:{attempt}
→ Kafka: re-emit events for remaining chunks or stage
→ PostgreSQL: increment retry_count
→ If retry_count >= 3: alert operators, mark FAILED
```

---

## Failure Handling & Recovery

### Failure Scenarios & Recovery

| Scenario | Root Cause | Detection | Recovery |
|----------|-----------|-----------|----------|
| **Worker Crash Mid-Stage** | Pod failure / OOM | Worker doesn't heartbeat (stale `updated_at`) | Replay Controller detects, re-emits stage events, resumes from `last_chunk_id` |
| **S3 Upload Timeout** | Network / S3 overload | ffmpeg succeeds but upload hangs | Exponential backoff retry (3 attempts), then fail |
| **Duplicate Kafka Event** | Broker rebalance / retries | Same event processed twice | Redis idempotency key prevents duplicate processing |
| **ffmpeg Crash on Chunk 5** | Corrupted audio segment | Worker logs + updates `processed_files.status=FAILED` | Replay Controller resumes from chunk 6 |
| **Database Connection Lost** | Network issue | Worker can't update `processed_metadata` | Transaction rollback, worker exits, pod restarts, Replay Controller retriggers |
| **Chunk Count Exceeds Expected** | Audio file changed during processing | Chunker finishes but count is wrong | Validation stage detects, marks FAILED, next replay rechecks |
| **Feature Flag Disabled** | Subscription tier downgrade | Subscription Service returns feature_enabled=false | Enrichment worker skips (STT workers still process chunks) |
| **Org Service Unavailable** | Service outage | Action Detection Worker can't validate assignees | Mark FAILED, emit alert, Replay Controller retries after timeout |
| **Processing Metadata Lost** | PostgreSQL corruption | Worker can't read current_stage | Fallback to Redis last known state, rescan chunks in S3 |

### Retry Strategy

**Exponential Backoff Example:**
```
Attempt 1: immediate
Attempt 2: 2 seconds
Attempt 3: 4 seconds
Attempt 4: 8 seconds
...
Max retries: 3
Max backoff: 60 seconds
```

**Non-Retriable Errors (mark FAILED immediately):**
- Invalid audio format (not decodable by ffmpeg)
- Meeting duration out of bounds (< 30 sec or > 4 hours)
- Corrupted S3 object (MD5 mismatch)
- Missing meeting_id or required metadata

**Retriable Errors (with backoff):**
- Network timeouts (S3, Kafka, DB)
- Transient ffmpeg failures
- Disk space temporarily full
- Kafka broker temporarily unavailable

---

## Implementation Examples

### Example 1: Preprocessing Worker (Python)

```python
# filepath: workers/preprocessing_worker.py

import os
import logging
import hashlib
import subprocess
from datetime import datetime, timedelta

import boto3
import redis
import psycopg2
from kafka import KafkaConsumer, KafkaProducer
import json

# Configuration
S3_BUCKET = os.getenv('S3_BUCKET', 'cognita-audio')
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
DB_CONN = os.getenv('DATABASE_URL')
KAFKA_BROKERS = os.getenv('KAFKA_BROKERS', 'localhost:9092').split(',')

# Clients
s3_client = boto3.client('s3')
redis_client = redis.from_url(REDIS_URL, decode_responses=True)
db_conn = psycopg2.connect(DB_CONN)
kafka_consumer = KafkaConsumer('meeting.uploaded.v1', bootstrap_servers=KAFKA_BROKERS)
kafka_producer = KafkaProducer(bootstrap_servers=KAFKA_BROKERS)

logger = logging.getLogger(__name__)

def preprocess_audio(meeting_id, s3_path):
    """
    Preprocess raw audio: noise reduction, filtering, normalization.
    """
    
    # 1. Check idempotency
    source_etag = s3_client.head_object(Bucket=S3_BUCKET, Key=s3_path)['ETag']
    idempotency_key = f"{meeting_id}:preprocess:{source_etag}"
    
    if not redis_client.setnx(idempotency_key, "1"):
        logger.info(f"Skipping preprocessing for {meeting_id} (already processed)")
        return
    
    redis_client.expire(idempotency_key, 24 * 3600)
    
    try:
        # 2. Download from S3
        local_input = f"/tmp/{meeting_id}_raw.wav"
        logger.info(f"Downloading {s3_path} to {local_input}")
        s3_client.download_file(S3_BUCKET, s3_path, local_input)
        
        # 3. Preprocess with ffmpeg
        local_output = f"/tmp/{meeting_id}_preprocessed.wav"
        cmd = [
            'ffmpeg', '-i', local_input,
            '-af', 'highpass=f=80,lowpass=f=16000,volume=-1dB',
            '-ar', '16000', '-ac', '1',
            '-loglevel', 'error',
            local_output
        ]
        logger.info(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True, timeout=3600)
        
        # 4. Upload to S3
        s3_output_path = f"/temp/{meeting_id}/preprocessed.wav"
        logger.info(f"Uploading to {s3_output_path}")
        s3_client.upload_file(local_output, S3_BUCKET, s3_output_path)
        
        # 5. Update database
        cursor = db_conn.cursor()
        cursor.execute("""
            UPDATE processing_metadata 
            SET current_stage = %s, updated_at = now()
            WHERE meeting_id = %s
        """, ('VALIDATED', meeting_id))
        db_conn.commit()
        logger.info(f"Updated metadata for {meeting_id}")
        
        # 6. Cleanup
        os.remove(local_input)
        os.remove(local_output)
        logger.info(f"Preprocessing complete for {meeting_id}")
        
    except Exception as e:
        logger.error(f"Preprocessing failed for {meeting_id}: {e}")
        cursor = db_conn.cursor()
        cursor.execute("""
            UPDATE processing_metadata 
            SET retry_count = retry_count + 1, last_error = %s, updated_at = now()
            WHERE meeting_id = %s
        """, (str(e), meeting_id))
        db_conn.commit()
        raise

def main():
    """
    Main worker loop: consume Kafka events and preprocess.
    """
    logger.info("Starting Preprocessing Worker")
    
    for message in kafka_consumer:
        try:
            event = json.loads(message.value.decode('utf-8'))
            meeting_id = event['meeting_id']
            s3_path = event['s3_path']
            
            logger.info(f"Processing {meeting_id}")
            preprocess_audio(meeting_id, s3_path)
            
        except Exception as e:
            logger.error(f"Worker error: {e}")

if __name__ == '__main__':
    main()
```

### Example 2: Audio Chunker (Python)

```python
# filepath: workers/audio_chunker.py

import math
import subprocess
import json
import os

import boto3
import redis
import psycopg2
from kafka import KafkaConsumer, KafkaProducer

S3_BUCKET = os.getenv('S3_BUCKET', 'cognita-audio')
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
DB_CONN = os.getenv('DATABASE_URL')
KAFKA_BROKERS = os.getenv('KAFKA_BROKERS', 'localhost:9092').split(',')

CHUNK_LENGTH_SEC = 900  # 15 minutes
OVERLAP_SEC = 20

s3_client = boto3.client('s3')
redis_client = redis.from_url(REDIS_URL, decode_responses=True)
db_conn = psycopg2.connect(DB_CONN)
kafka_consumer = KafkaConsumer('audio.normalized.v1', bootstrap_servers=KAFKA_BROKERS)
kafka_producer = KafkaProducer(bootstrap_servers=KAFKA_BROKERS)

def get_audio_duration(s3_path):
    """Get duration in seconds using ffprobe."""
    local_file = f"/tmp/temp_{s3_path.split('/')[-1]}"
    s3_client.download_file(S3_BUCKET, s3_path, local_file)
    
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'json',
        local_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    duration = json.loads(result.stdout)['format']['duration']
    os.remove(local_file)
    return float(duration)

def create_chunks(meeting_id, s3_path, total_duration):
    """
    Pre-create chunk database rows and extract chunks from S3 audio.
    """
    chunk_step = CHUNK_LENGTH_SEC - OVERLAP_SEC
    total_chunks = math.ceil(total_duration / chunk_step)
    
    # Pre-create database rows
    cursor = db_conn.cursor()
    for i in range(total_chunks):
        cursor.execute("""
            INSERT INTO processed_files 
            (meeting_id, chunk_id, status, created_at, updated_at)
            VALUES (%s, %s, 'PENDING', now(), now())
        """, (meeting_id, i))
    db_conn.commit()
    print(f"Pre-created {total_chunks} chunk rows for {meeting_id}")
    
    # Download normalized audio
    local_input = f"/tmp/{meeting_id}_normalized.wav"
    s3_client.download_file(S3_BUCKET, s3_path, local_input)
    
    # Extract each chunk
    for i in range(total_chunks):
        idempotency_key = f"{meeting_id}:chunk:{i}"
        if not redis_client.setnx(idempotency_key, "1"):
            print(f"Skipping chunk {i} (already processed)")
            continue
        
        redis_client.expire(idempotency_key, 24 * 3600)
        
        # Claim chunk
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT 1 FROM processed_files 
            WHERE meeting_id = %s AND chunk_id = %s AND status = 'PENDING'
            FOR UPDATE
        """, (meeting_id, i))
        
        if not cursor.fetchone():
            print(f"Chunk {i} already processing or complete")
            continue
        
        # Update status
        cursor.execute("""
            UPDATE processed_files 
            SET status = 'PROCESSING', updated_at = now()
            WHERE meeting_id = %s AND chunk_id = %s
        """, (meeting_id, i))
        db_conn.commit()
        
        try:
            # Calculate time bounds
            start_time = i * chunk_step
            duration = min(CHUNK_LENGTH_SEC, total_duration - start_time)
            
            # Extract chunk
            local_output = f"/tmp/chunk_{i}.wav"
            cmd = [
                'ffmpeg', '-ss', str(start_time),
                '-t', str(duration),
                '-i', local_input,
                '-c:a', 'pcm_s16le',
                '-loglevel', 'error',
                local_output
            ]
            subprocess.run(cmd, check=True, timeout=3600)
            
            # Upload to S3
            s3_chunk_path = f"/processed/{meeting_id}/chunks/chunk_{i}.wav"
            s3_client.upload_file(local_output, S3_BUCKET, s3_chunk_path)
            
            # Update database
            cursor.execute("""
                UPDATE processed_files 
                SET status = 'COMPLETED', 
                    s3_path = %s,
                    duration_seconds = %s,
                    updated_at = now()
                WHERE meeting_id = %s AND chunk_id = %s
            """, (s3_chunk_path, int(duration), meeting_id, i))
            
            cursor.execute("""
                UPDATE processing_metadata 
                SET last_chunk_id = %s
                WHERE meeting_id = %s
            """, (i, meeting_id))
            db_conn.commit()
            
            # Emit Kafka event
            event = {
                'meeting_id': meeting_id,
                'chunk_id': i,
                's3_path': s3_chunk_path,
                'start_time_seconds': int(start_time),
                'duration_seconds': int(duration)
            }
            kafka_producer.send('audio.chunked.v1', json.dumps(event).encode())
            
            # Cleanup
            os.remove(local_output)
            
            print(f"Chunk {i} complete: {duration}s")
            
        except Exception as e:
            print(f"Chunk {i} failed: {e}")
            cursor.execute("""
                UPDATE processed_files 
                SET status = 'FAILED', error_message = %s, updated_at = now()
                WHERE meeting_id = %s AND chunk_id = %s
            """, (str(e), meeting_id, i))
            db_conn.commit()
            raise
    
    os.remove(local_input)
    
    cursor.execute("""
        UPDATE processing_metadata 
        SET current_stage = 'CHUNKED'
        WHERE meeting_id = %s
    """, (meeting_id,))
    db_conn.commit()
    print(f"Chunking complete for {meeting_id}")

def main():
    print("Starting Audio Chunker Worker")
    for message in kafka_consumer:
        try:
            event = json.loads(message.value.decode('utf-8'))
            meeting_id = event['meeting_id']
            s3_path = event['s3_path']
            
            print(f"Chunking {meeting_id}")
            duration = get_audio_duration(s3_path)
            create_chunks(meeting_id, s3_path, duration)
            
        except Exception as e:
            print(f"Worker error: {e}")

if __name__ == '__main__':
    main()
```

---

## Monitoring & Observability

### Key Metrics (Prometheus)

```python
from prometheus_client import Counter, Histogram, start_http_server

# Per-worker metrics
preprocessing_attempts = Counter(
    'preprocessing_attempts_total',
    'Total preprocessing attempts',
    ['status']  # success, failure, retry
)

preprocessing_duration = Histogram(
    'preprocessing_duration_seconds',
    'Preprocessing duration',
    buckets=[30, 60, 300, 600, 1800]
)

# Pipeline-level metrics
meetings_processed = Counter(
    'meetings_processed_total',
    'Total meetings processed',
    ['stage']  # VALIDATED, EXTRACTED, CHUNKED, COMPLETED
)

chunks_processed = Counter(
    'chunks_processed_total',
    'Total chunks processed',
    ['status']  # success, failure
)

# Retry metrics
retries_triggered = Counter(
    'retries_triggered_total',
    'Replay controller retries',
    ['stage']
)
```

### Structured Logging Example

```python
import json
import logging

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'meeting_id': getattr(record, 'meeting_id', None),
            'chunk_id': getattr(record, 'chunk_id', None),
            'stage': getattr(record, 'stage', None),
            'worker_id': os.getenv('HOSTNAME'),
        }
        return json.dumps(log_obj)

logger.info("Chunk processing complete", extra={
    'meeting_id': 'meet_123',
    'chunk_id': 5,
    'stage': 'CHUNKED'
})
```

### Health Check Endpoint

```python
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/health')
def health():
    checks = {
        'redis': check_redis(),
        'postgres': check_postgres(),
        's3': check_s3(),
        'kafka': check_kafka(),
    }
    
    all_healthy = all(checks.values())
    status = 200 if all_healthy else 503
    
    return jsonify({'status': 'healthy' if all_healthy else 'degraded', 'checks': checks}), status
```

---

## Deployment & Operations

### Docker Compose (MVP Stack)

```yaml
# filepath: docker-compose.yml

version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: cognita
      POSTGRES_USER: dev
      POSTGRES_PASSWORD: dev
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./sql/schema.sql:/docker-entrypoint-initdb.d/schema.sql

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  minio:
    image: minio/minio:latest
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data

  kafka:
    image: confluentinc/cp-kafka:7.4.0
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    ports:
      - "9092:9092"
    depends_on:
      - zookeeper

  zookeeper:
    image: confluentinc/cp-zookeeper:7.4.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  preprocessing_worker:
    build:
      context: .
      dockerfile: workers/Dockerfile
      args:
        WORKER: preprocessing
    environment:
      DATABASE_URL: postgresql://dev:dev@postgres:5432/cognita
      REDIS_URL: redis://redis:6379
      S3_BUCKET: cognita-audio
      AWS_ACCESS_KEY_ID: minioadmin
      AWS_SECRET_ACCESS_KEY: minioadmin
      S3_ENDPOINT_URL: http://minio:9000
      KAFKA_BROKERS: kafka:29092
    depends_on:
      - postgres
      - redis
      - minio
      - kafka
    volumes:
      - /tmp:/tmp

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    depends_on:
      - prometheus

volumes:
  postgres_data:
  minio_data:
```

### Kubernetes Deployment (Production)

```yaml
# filepath: k8s/preprocessing-worker.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: preprocessing-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: preprocessing-worker
  template:
    metadata:
      labels:
        app: preprocessing-worker
    spec:
      containers:
      - name: preprocessing
        image: cognita/preprocessing-worker:1.0.0
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: cognita-secrets
              key: database_url
        - name: REDIS_URL
          value: redis://redis-cluster:6379
        - name: KAFKA_BROKERS
          value: kafka-cluster:9092
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          periodSeconds: 5
```

### Runbook Example

**Task: Manually Replay Stuck Meeting**

```bash
# 1. Check meeting progress
psql cognita -c "SELECT * FROM processing_metadata WHERE meeting_id = 'meet_123';"

# Output:
#  meeting_id | current_stage | last_chunk_id | retry_count |       updated_at
# -----------+---------+-------+-------+---------------------
#  meet_123   | CHUNKED       | 4             | 2           | 2024-01-15 10:00:00

# 2. Check chunk statuses
psql cognita -c "SELECT chunk_id, status, updated_at FROM processed_files WHERE meeting_id = 'meet_123' ORDER BY chunk_id;"

# 3. Manually trigger replay
redis-cli DEL "meet_123:replay:CHUNKED:3"  # Clear replay guard
# (Next Replay Controller scan will re-trigger)

# OR manually emit Kafka event for chunks 5+:
kafka-produce --topic audio.chunked.v1 <<< '{
  "meeting_id": "meet_123",
  "chunk_id": 5,
  "s3_path": "/processed/meet_123/chunks/chunk_5.wav",
  "start_time_seconds": 4400,
  "duration_seconds": 900
}'

# 4. Monitor progress
watch -n 5 'psql cognita -c "SELECT * FROM processing_metadata WHERE meeting_id = '\''meet_123'\'\';"'
```

---

## Appendix: Quick Reference

### Chunk Calculation Formula

```
chunk_length = 15 minutes (900 seconds)
overlap = 20 seconds
chunk_step = chunk_length - overlap = 880 seconds

For a 1-hour meeting (3600 seconds):
  total_chunks = ceil(3600 / 880) = 5 chunks

Chunk boundaries:
  Chunk 0: 0s to 900s
  Chunk 1: 880s to 1780s (overlap: 880-900)
  Chunk 2: 1760s to 2660s (overlap: 1760-1780)
  Chunk 3: 2640s to 3540s (overlap: 2640-2660)
  Chunk 4: 3520s to 3600s (partial, 80s duration)
```

### ffmpeg Command Reference

```bash
# Preprocess (denoise, filter)
ffmpeg -i input.mp3 \
  -af "highpass=f=80,lowpass=f=16000,volume=-1dB" \
  -ar 16000 -ac 1 \
  output.wav

# Validate with ffprobe
ffprobe -v error -show_entries format=duration,sample_rate,channels \
  -of json input.wav

# Extract (standardize format)
ffmpeg -i input.mp4 -ac 1 -ar 16000 -sample_fmt s16 output.wav

# Trim silence
sox input.wav output.wav silence 1 0.1 1% reverse silence 1 0.1 1% reverse

# Normalize loudness
ffmpeg -i input.wav \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
  output.wav

# Extract chunk
ffmpeg -ss 880 -t 900 -i input.wav -c:a pcm_s16le chunk.wav
```

### PostgreSQL Queries

```sql
-- Overall pipeline progress
SELECT meeting_id, current_stage, last_chunk_id, retry_count, updated_at
FROM processing_metadata
WHERE updated_at > now() - interval '1 hour'
ORDER BY updated_at DESC;

-- Chunks for a meeting
SELECT chunk_id, status, s3_path, duration_seconds, updated_at
FROM processed_files
WHERE meeting_id = 'meet_123'
ORDER BY chunk_id;

-- Stuck meetings (not updated in 5 minutes)
SELECT meeting_id, current_stage, retry_count, updated_at
FROM processing_metadata
WHERE updated_at < now() - interval '5 minutes'
  AND retry_count < 3
  AND current_stage != 'COMPLETED';

-- Failed chunks
SELECT meeting_id, chunk_id, error_message, updated_at
FROM processed_files
WHERE status = 'FAILED'
  AND updated_at > now() - interval '1 hour';
```

---

## Conclusion

The **Data Engineering Layer** is the critical foundation for Cognita's meeting intelligence pipeline. It provides:

 **Reliability:** Deterministic replay, idempotency, fault tolerance  
 **Scalability:** Stateless workers, horizontal scaling  
 **Observability:** Complete audit trail, structured logging, metrics  
 **Simplicity:** Minimal moving parts, clear data flow  

This documentation provides everything needed to understand, implement, deploy, and operate the DE Layer for your grad project.

---

**Document Version:** 1.0  
**Last Updated:** Dec 2025  
**Status:** Production-Ready for MVP
----
**Created By:** Fares Ashraf (Data Engineer)