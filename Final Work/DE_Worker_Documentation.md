# Data Engineering Layer: Worker & System Documentation
## Cognita Meeting Intelligence Platform

This document provides a detailed technical specification of the Data Engineering (DE) Layer, covering worker responsibilities, the processing controller logic, and the database schemas that drive the pipeline.

---

## 1. Worker Specifications

The DE Layer consists of seven specialized workers, each performing a discrete step in the audio preparation pipeline.

### 1.1 Ingest Worker
*   **Trigger:** `meeting.uploaded.v1` Kafka event.
*   **Responsibilities:**
    *   **Pipeline Entry:** Acts as the formal entry point for the DE layer.
    *   **S3 Validation:** Verifies that the raw file exists at the provided S3 path.
    *   **Metadata Initialization:** Creates the initial record in `processing_metadata` with `current_stage = 'INGESTED'`.
*   **Outcome:** Emits `meeting.ingested.v1`.

### 1.2 Preprocessing Worker
*   **Trigger:** `meeting.ingested.v1` Kafka event.
*   **Responsibilities:**
    *   **Audio Cleaning:** Applies filters to remove noise and artifacts.
    *   **High-Pass Filter:** Removes low-frequency rumble (typically < 80Hz).
    *   **Low-Pass Filter:** Removes high-frequency hiss (typically > 16kHz).
    *   **Noise Reduction:** Applies spectral subtraction or gating to reduce background noise.
*   **Outcome:** Saves cleaned audio to `/processed/{id}/preprocessed.wav`.

### 1.3 Validation Worker
*   **Trigger:** Internal pipeline transition (post-preprocessing).
*   **Responsibilities:**
    *   **Playability Check:** Ensures the file header is valid and can be decoded.
    *   **Duration Constraints:** Enforces a minimum of **30 seconds** and a maximum of **3 hours**.
    *   **Channel Audit:** Validates if the file is Mono or Stereo (both accepted for input).
    *   **Sample Rate/Format:** Checks if the container is compatible (MP3, WAV, M4A, etc.).
*   **Outcome:** Updates `processing_metadata.current_stage = 'VALIDATED'`.

### 1.4 Audio Extractor
*   **Trigger:** Validation Success.
*   **Responsibilities:**
    *   **Transcoding:** Decodes input to a canonical format.
    *   **Format:** Standardizes to **PCM WAV**.
    *   **Bit Depth:** Forces **16-bit** (signed-integer).
    *   **Sample Rate:** Resamples to **16 kHz** (optimal for Batch STT).
    *   **Downmixing:** Converts multi-channel audio to **Mono**.
*   **Outcome:** Saves to `/processed/{id}/audio.wav`; emits `audio.extracted.v1`.

### 1.5 Audio Normalizer
*   **Trigger:** `audio.extracted.v1` Kafka event.
*   **Responsibilities:**
    *   **Silence Trimming:** Removes leading and trailing silence.
    *   **Volume Normalization:** Adjusts loudness to a target level (e.g., -23 LUFS) to ensure consistent transcription.
    *   **Re-Verification:** Performs a final duration check post-trimming to ensure the "content" still meets the 30s minimum.
*   **Outcome:** Saves to `/processed/{id}/normalized.wav`; emits `audio.normalized.v1`.

### 1.6 Audio Chunker
*   **Trigger:** `audio.normalized.v1` Kafka event.
*   **Responsibilities:**
    *   **Segmentation:** Splits the meeting into **15-minute chunks**.
    *   **Context Preservation:** Adds a **20-second overlap** between chunks to prevent word clipping at boundaries.
    *   **Parallel Readiness:** Pre-creates `processed_files` records for all chunks.
    *   **Storage:** Uploads chunks to `/processed/{id}/chunks/chunk_{i}.wav`.
*   **Outcome:** Emits `audio.chunked.v1` for **each** chunk produced.

---

## 2. Processing Controller (The Supervisor)

The **Processing Controller** is a stateless service that ensures the system recovers from transient failures (worker crashes, timeouts).

### 2.1 Responsibilities
1.  **Stale Job Detection:** Periodically scans `processing_metadata` for meetings stuck in `PROCESSING` for > 10 minutes.
2.  **Retry Coordination:** Increments the `retry_count` and re-emits the Kafka event for the failed stage.
3.  **Chunk Recovery:** If the Chunker fails mid-process, the Controller identifies which chunks are still in `PENDING` state and re-triggers only the missing work.
4.  **Dead Letter Logic:** After 3 failed retries, marks the meeting as `FAILED` and halts processing.

---

## 3. Database Schemas

The system uses two primary tables in **PostgreSQL** to manage state.

### 3.1 Table: `processing_metadata`
Tracks the global state of a meeting recording.

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `meeting_id` | UUID (PK) | Unique identifier for the meeting. |
| `current_stage` | ENUM | INGESTED, VALIDATED, EXTRACTED, NORMALIZED, CHUNKED, COMPLETED, FAILED. |
| `status` | ENUM | PENDING, PROCESSING, COMPLETED, FAILED. |
| `s3_raw_path` | TEXT | Path to the original uploaded file. |
| `last_chunk_id` | INT | The last successfully processed chunk index. |
| `retry_count` | INT | Number of retry attempts made by the Controller. |
| `last_error` | TEXT | Error message from the last failed worker. |
| `created_at` | TIMESTAMP | Time of initial upload. |
| `updated_at` | TIMESTAMP | Last heartbeat or stage transition. |

### 3.2 Table: `processed_files`
Tracks the status of individual audio segments (chunks).

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `chunk_id` | UUID (PK) | Unique identifier for the segment. |
| `meeting_id` | UUID (FK) | Reference to `processing_metadata.meeting_id`. |
| `index` | INT | The order of the chunk (0, 1, 2...). |
| `s3_chunk_path` | TEXT | Path to the `.wav` chunk in S3. |
| `duration_sec` | FLOAT | Actual duration of the chunk audio. |
| `status` | ENUM | PENDING, PROCESSING, COMPLETED, FAILED. |
| `worker_id` | TEXT | ID of the worker instance that processed the chunk. |
| `updated_at` | TIMESTAMP | Last status update. |

---

## 4. Idempotency Layer (Redis)

Redis is used to prevent duplicate processing if a Kafka event is delivered twice.

*   **Key Format:** `lock:{meeting_id}:{stage}`
*   **TTL:** 1 hour.
*   **Logic:** A worker must acquire a "Processing Lock" before starting. If the lock exists, the worker skips the task (idempotent skip).
---

## 5. S3 Object Storage Schema

S3 acts as the durable blob storage for all audio artifacts. The directory structure is organized by `meeting_id` to ensure isolation and easy cleanup.

| Artifact Type | S3 Key (Path) | Producer | Description |
| :--- | :--- | :--- | :--- |
| **Raw Upload** | `/raw/{meeting_id}/upload.{ext}` | Meeting Service | Original file uploaded by the user (MP4, MP3, etc.). |
| **Preprocessed** | `/processed/{meeting_id}/preprocessed.wav` | Preprocessing Worker | Audio after noise reduction and spectral filtering. |
| **Canonical WAV** | `/processed/{meeting_id}/audio.wav` | Audio Extractor | Standardized 16kHz, 16-bit, Mono PCM WAV. |
| **Normalized** | `/processed/{meeting_id}/normalized.wav` | Audio Normalizer | Silence-trimmed and loudness-corrected audio. |
| **Audio Chunks** | `/processed/{meeting_id}/chunks/chunk_{i}.wav` | Audio Chunker | 15-minute segments with 20s overlap for AI STT. |

### 5.1 Retention Policy
*   **Raw Storage:** Retained for 7 days (for debugging/replay).
*   **Processed Artifacts:** Retained for 30 days or until final AI aggregation is complete.
*   **Chunks:** Deleted immediately after successful STT/Diarization to save space.

---

## 6. End-to-End Execution Scenario: "The 70-Minute Marketing Sync"

This scenario traces a real-world meeting through the DE layer to illustrate state transitions and artifact generation.

### 6.1 The Input
*   **File:** `marketing_weekly.mp4` (70 minutes long).
*   **Size:** 450 MB.
*   **Meeting ID:** `meet_abcd_1234`.

### 6.2 Step-by-Step Flow

| Step | Worker | Action | Key Outcome |
| :--- | :--- | :--- | :--- |
| **0** | **Meeting Service** | Receives upload; stores to S3. | `s3://raw/meet_abcd_1234/upload.mp4` |
| **1** | **Ingest Worker** | Validates S3 path; creates DB record. | `current_stage: INGESTED` |
| **2** | **Preprocessing** | Runs spectral noise reduction & high-pass. | `s3://.../preprocessed.wav` (Cleaned) |
| **3** | **Validation** | Checks duration (4200s); verifies playability. | Case: Valid (within 30s-3h range) |
| **4** | **Extractor** | Decodes to 16kHz, 16-bit, Mono WAV. | `s3://.../audio.wav` (Canonical) |
| **5** | **Normalizer** | Trims 15s of entrance silence; LUFS to -23. | `s3://.../normalized.wav` (Standardized) |
| **6** | **Chunker** | Splits into 5 segments (15m each, 20s overlap). | 5 records in `processed_files` |

### 6.3 Final State (Post-DE)

**Database (`processing_metadata`):**
*   `status`: COMPLETED
*   `current_stage`: CHUNKED
*   `last_chunk_id`: 4

**Storage (`chunks/` Partition):**
*   `chunk_0.wav` (00:00 - 15:00)
*   `chunk_1.wav` (14:40 - 29:40) — *20s overlap*
*   `chunk_2.wav` (29:20 - 44:20)
*   `chunk_3.wav` (44:00 - 59:00)
*   `chunk_4.wav` (58:40 - 70:00) — *Final segment*

**Next Trigger:** The pipeline emits 5 separate `audio.chunked.v1` events, allowing the AI layer to begin transcribing all 5 segments in parallel.

