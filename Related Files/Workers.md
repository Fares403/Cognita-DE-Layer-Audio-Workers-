# **Data Engineering Layer Documentation – Cognita Meeting Platform**

---

## **1. Introduction**

The **Data Engineering (DE) Layer** in the Cognita Meeting Platform is the **foundation for audio ingestion, standardization, and preparation for AI-powered meeting intelligence**. It ensures:

* **Data Integrity** – all audio and metadata is validated and tracked.
* **Fault-Tolerance** – retries and failure handling at chunk and stage levels.
* **Scalability** – supports high-volume meetings with stateless workers.
* **Observability & Reprocessing** – complete audit trail for monitoring, debugging, and recovery.

**Purpose:** Convert raw meeting audio into **clean, normalized, chunked, metadata-rich formats** suitable for downstream AI layers like STT, Speaker Diarization, Summarization, Action Detection, and RAG (Retrieval-Augmented Generation).

---

## **2. Architecture Overview**

### **2.1 Core Components**

| Component                            | Type                  | Responsibilities                                                               |
| ------------------------------------ | --------------------- | ------------------------------------------------------------------------------ |
| **Preprocessing Worker**             | DE Worker             | Noise reduction, filtering, audio enhancement                                  |
| **Validation Worker**                | DE Worker             | Audio format check, duration validation, metadata verification                 |
| **Audio Extractor**                  | DE Worker             | Converts raw audio into standardized 16kHz WAV format                          |
| **Audio Normalizer**                 | DE Worker             | Trims silence, normalizes volume levels                                        |
| **Audio Chunker**                    | DE Worker             | Splits audio into ≤15 min overlapping chunks for context continuity            |
| **Processing Metadata Manager**      | Database & Controller | Tracks last processed stage, chunk, retry counts                               |
| **Redis Idempotency Layer**          | Cache                 | Prevents duplicate processing during retries                                   |
| **Replay / Reprocessing Controller** | Service               | Orchestrates retries and resumes failed stages from last successful checkpoint |

### **2.2 Tools & Technologies**

| Layer / Purpose                    | Tool / Technology                | Rationale                                                               |
| ---------------------------------- | -------------------------------- | ----------------------------------------------------------------------- |
| Storage / Binaries                 | S3 / MinIO                       | Durable, scalable object storage for raw, normalized, and chunked audio |
| Metadata / State                   | PostgreSQL                       | Tracks chunk processing, stage progress, retries, and audit logs        |
| Idempotency / Fast State           | Redis                            | Ensures stage-level idempotency, fast coordination, retry guards        |
| Event Transport / Async Processing | Kafka                            | Decouples workers, allows replayable event-driven processing            |
| Semantic / AI Vector Storage       | pgvector / PostgreSQL            | Stores embeddings for retrieval-augmented generation (RAG)              |
| Containerization / Deployment      | Docker / Docker Compose          | Ensures reproducibility, simplified deployment of workers and services  |
| Monitoring / Logging               | Prometheus + Grafana / ELK stack | Stage-level logging, real-time observability                            |

---

## **3. Data Pipeline Workflow**

### **3.1 Stage 1 – Preprocessing Worker**

**Input:** Raw meeting audio (any format)

**Operations:**

1. Noise reduction and background artifact removal
2. High-pass / low-pass filtering
3. Standardization of sample rate if required

**Output:** Cleaned audio → Validation Worker

**Failure & Retry:**

* Retries handled per meeting chunk via Redis
* Alerts if retries exceed threshold
* Metadata records stage attempt count for audit

**Idempotency:** Redis ensures no double processing

---

### **3.2 Stage 2 – Validation Worker**

**Checks:**

* Duration within configured bounds
* Compatible audio format for extraction
* Required metadata present (meeting ID, timestamp)

**Output:** Validated audio → Audio Extractor

**Failure Handling:**

* Invalid files flagged
* Retries attempted per chunk

**Example Scenario:**

* Audio duration = 2h30min → exceeds maximum 2h limit
  → Chunked, partial processing allowed, remainder marked for reprocessing

---

### **3.3 Stage 3 – Audio Extractor**

**Purpose:** Convert raw or compressed audio into **16kHz WAV** format

**Output:**

* S3: `/processed/{meeting_id}/audio.wav`
* PostgreSQL metadata updated (`processed_files` table)

**Failure Handling:**

* Partial extraction triggers chunk-level retry
* Logs partial successes in metadata

**Example:**

* A 45-minute recording split into 3 chunks → chunk 2 extraction fails → reprocessing controller retries only chunk 2

---

### **3.4 Stage 4 – Audio Normalizer**

**Purpose:** Volume normalization, silence trimming, format enforcement

**Output:** S3: `/processed/{meeting_id}/normalized.wav`

**Failure Handling:**

* Retry on S3 upload failures
* Redis ensures duplicate events ignored

---

### **3.5 Stage 5 – Audio Chunker**

**Purpose:** Split normalized audio into **≤15 min chunks** with 10–30 sec overlap

**Outputs:**

* S3: `/processed/{meeting_id}/chunks/{chunk_id}.wav`
* PostgreSQL `processed_files` metadata

**Failure Handling & Replay:**

* Chunking fails mid-meeting → last successfully processed chunk tracked in `processing_metadata`
* Reprocessing controller resumes from next chunk
* Overlaps improve STT transcription quality

**Example Scenario:**

* Meeting = 1h10min → 5 chunks
* Chunk 3 fails → metadata tracks last chunk = 2 → replay resumes chunk 3 → downstream STT consumes successfully

---

### **3.6 Stage 6 – Processing Metadata Manager**

Tracks **stage-level progress, last chunk processed, retry counts**.

**Fields Tracked:**

* `meeting_id`
* `current_stage`
* `last_chunk_id`
* `retry_count`
* `updated_at`

**Purpose:**

* Enables **replay/resume**
* Central audit trail for all DE operations
* Provides real-time pipeline observability

**Consumers:** Replay Controller, Dashboard, DE workers

---

### **3.7 Stage 7 – Replay / Reprocessing Controller**

**Purpose:** Acts as **orchestrator for retries and recovery**

* Monitors `processing_metadata` table
* Resumes failed stages from last successful chunk
* Uses Redis to enforce **idempotency**
* Can trigger **full meeting replay** or stage-level replay

**Example Scenario:**

1. Audio chunker fails on chunk 5 → metadata shows last chunk = 4
2. Controller re-emits chunking event starting from chunk 5
3. Downstream stages consume successfully without reprocessing previous chunks
4. Kafka topics ensure events are replayable if lost

---

## **4. Failure & Recovery Scenarios**

| Scenario                  | Worker / Stage                   | Recovery Mechanism                                             |
| ------------------------- | -------------------------------- | -------------------------------------------------------------- |
| Worker crash mid-stage    | Any DE Worker                    | Redis + `processing_metadata` resume from last processed chunk |
| S3 upload fails           | Extractor / Normalizer / Chunker | Retry upload, metadata tracks temporary path                   |
| Duplicate Kafka event     | Any DE Worker                    | Redis prevents duplicate processing                            |
| Partial chunk processing  | Chunker                          | Resume from next chunk using metadata                          |
| Kafka message lost        | DE → AI workers                  | Replay events based on metadata, idempotent consumption        |
| Exceeding retry threshold | Any stage                        | Alert system for manual intervention                           |

---

## **5. Metadata & Storage Overview**

| Storage Layer                    | Purpose                                    | Notes                                        |
| -------------------------------- | ------------------------------------------ | -------------------------------------------- |
| S3 / MinIO                       | Binary files, normalized audio, chunks     | Immutable storage for all large artifacts    |
| PostgreSQL `processed_files`     | Chunk-level tracking, completion detection | Used for AI consumption and pipeline control |
| PostgreSQL `processing_metadata` | Stage-level progress, retries, last chunk  | Enables replay & recovery                    |
| Redis                            | Idempotency, fast retry guards             | Short TTL cache                              |
| Kafka                            | Event transport for async processing       | Decouples DE and AI layers                   |
| pgvector                         | RAG embeddings                             | Read by retrieval API                        |

---

## **6. Pipeline Example – End-to-End**

1. Meeting uploaded → triggers `meeting.uploaded.v1`
2. Preprocessing cleans audio → Validation verifies format/duration
3. Audio Extractor standardizes WAV → stores in S3
4. Audio Normalizer trims silence → stores normalized audio
5. Audio Chunker splits audio → stores chunks in S3, updates `processed_files`
6. STT Worker consumes chunks → writes transcript segments
7. Processing Metadata Manager updates last processed chunk & stage
8. Reprocessing Controller resumes failed chunks automatically
9. Downstream AI Enrichment consumes successfully processed chunks

---

## **7. Key Features & Best Practices**

* **Idempotency:** Redis prevents duplicate processing
* **Metadata-driven orchestration:** Stage completion & retries tracked in PostgreSQL
* **Chunk-based processing:** Isolates failures, supports distributed AI processing
* **Replay & Resume:** Failed stages resume from last successful chunk
* **Observability:** Stage-level logging, dashboard monitoring
* **Scalability:** Stateless workers, horizontally scalable
* **Extensibility:** Easily add new preprocessing steps or formats without breaking downstream AI

---

## **8. Conclusion**

The DE Layer is **critical for reliable AI-driven meeting intelligence**:

* **Data integrity** ensured via validation and metadata orchestration
* **Fault-tolerance** via retries, chunk-level isolation, Redis idempotency
* **Scalability** with stateless workers and distributed processing
* **Observability & Reprocessing** enable real-time monitoring, debugging, and automatic recovery