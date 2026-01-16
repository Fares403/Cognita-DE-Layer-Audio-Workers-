# AI Batch Processing Layer - Complete Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture Components](#architecture-components)
3. [Detailed Process Flow](#detailed-process-flow)
4. [Node Descriptions](#node-descriptions)
5. [Data Flow Patterns](#data-flow-patterns)
6. [Complete Workflow Example](#complete-workflow-example)

---

## Overview

### Purpose
The **AI Batch Processing Layer** is the authoritative intelligence system that processes meeting recordings to extract canonical insights, decisions, and knowledge. It operates **after** the DE Batch Processing Layer completes audio preparation.

### Key Principles
- **Truth from Source**: Always re-derives intelligence from raw audio, never trusts real-time or incremental outputs
- **Deterministic & Replayable**: Uses Temporal workflow orchestration for reliability
- **Context-Aware**: Leverages external knowledge and workspace context without compromising canonical accuracy
- **Authoritative Output**: Produces final, versioned, and auditable knowledge artifacts

### Relationship to DE Layer
```
DE Layer Output → AI Layer Input
├─ Processed Audio Chunks (S3)
├─ Audio Metadata (PostgreSQL)
└─ audio.chunked.v1 Event (Kafka)
```

---

## Architecture Components

### 1. Triggers & Raw Sources

#### **Meeting Ended Event**
- **Type**: Workflow Trigger
- **Source**: Meeting Service
- **Purpose**: Initiates the batch AI workflow when a meeting concludes
- **Payload**: Meeting ID, participant list, duration, workspace context

#### **Raw Audio (Recording Storage)**
- **Type**: Data Source (S3)
- **Content**: Full meeting audio file (processed by DE Layer)
- **Format**: 16kHz, Mono, 16-bit PCM WAV
- **Location**: `s3://processed-audio/{meeting_id}/normalized.wav`

---

### 2. Orchestration Layer

#### **Temporal Workflow Orchestrator**
- **Technology**: Temporal.io
- **Characteristics**:
  - Deterministic execution
  - Automatic retry logic
  - State persistence
  - Replay capability for debugging
  
- **Workflow Steps**:
  1. Validate meeting completion
  2. Trigger Batch STT
  3. Coordinate parallel processing
  4. Aggregate results
  5. Persist to knowledge base

- **Error Handling**:
  - Automatic retries with exponential backoff
  - Dead letter queue for failed workflows
  - Alerting on persistent failures

---

### 3. Read-Only Context & Hints

#### **Provisional Intelligence (Incremental AI)**
- **Source**: Real-time AI outputs from live meeting
- **Usage**: Optimization hints ONLY
- **Examples**:
  - Draft summaries
  - Preliminary action items
  - Speaker identification hints
  
- **Important**: Never treated as authoritative; batch AI re-derives all intelligence

#### **Knowledge Base (Read-Only)**
- **Type**: Vector Database + Relational Store
- **Content**:
  - Historical meeting summaries
  - Project documentation
  - Team member profiles
  - Previous decisions
  
- **Usage**: Provides contextual reference for summarization

#### **RAG / Search Engine (Read-Only)**
- **Type**: Retrieval-Augmented Generation System
- **Purpose**: Fetches relevant historical context
- **Query Examples**:
  - "Previous decisions about project timeline"
  - "Related meetings with same participants"
  - "Background on discussed topics"

#### **Workspace Context**
- **Type**: Configuration Database
- **Content**:
  - User roles and permissions
  - Team structure
  - Access policies
  - Custom summarization rules
  
- **Usage**: Drives role-aware view generation

---

### 4. Batch AI Engine (Core Processing)

#### **Batch STT Service**
- **Purpose**: High-accuracy transcription from raw audio
- **Technology**: Advanced speech-to-text models (e.g., Whisper Large V3, AssemblyAI)
- **Input**: Full meeting audio from S3
- **Output**: Raw batch transcript with:
  - Speaker diarization
  - Timestamps
  - Confidence scores
  - Word-level timing
  
- **Processing**:
  ```
  1. Load normalized audio chunks from S3
  2. Process each chunk with overlap handling
  3. Merge chunks with boundary smoothing
  4. Apply speaker diarization
  5. Generate unified transcript
  ```

#### **Transcript Corrector**
- **Purpose**: Accuracy normalization and error correction
- **Input**: Raw batch transcript
- **Output**: Canonical transcript
- **Operations**:
  - Grammar correction
  - Technical term normalization
  - Punctuation refinement
  - Filler word removal (optional)
  - Speaker label consistency
  
- **Example**:
  ```
  Raw: "um so we need to uh implement the api by friday"
  Canonical: "We need to implement the API by Friday."
  ```

#### **Canonical Summarization Engine**
- **Purpose**: Generate authoritative meeting summaries
- **Input**: 
  - Canonical transcript
  - Provisional hints (optional)
  - Knowledge base context
  - RAG historical context
  
- **Output**: Multi-level summaries
  - Executive summary (2-3 sentences)
  - Detailed summary (paragraphs)
  - Section-wise breakdown
  - Key discussion points
  
- **Processing Logic**:
  ```
  1. Segment transcript by topics
  2. Extract key points per segment
  3. Synthesize with historical context
  4. Generate hierarchical summaries
  5. Validate against canonical transcript
  ```

#### **Decision & Task Extractor**
- **Purpose**: Identify actionable decisions and tasks
- **Input**: Canonical transcript
- **Output**: Structured decisions and tasks
  
- **Decision Schema**:
  ```json
  {
    "decision_id": "uuid",
    "description": "Migrate to microservices architecture",
    "made_by": ["user_id_1", "user_id_2"],
    "timestamp": "2026-01-16T14:23:00Z",
    "rationale": "To improve scalability",
    "impact": "high",
    "related_tasks": ["task_id_1", "task_id_2"]
  }
  ```
  
- **Task Schema**:
  ```json
  {
    "task_id": "uuid",
    "title": "Design microservices architecture",
    "assigned_to": "user_id_1",
    "due_date": "2026-01-30",
    "priority": "high",
    "context": "Discussed in architecture review meeting"
  }
  ```

#### **KPI Extractor (Event-Only)**
- **Purpose**: Extract metrics and key performance indicators
- **Input**: Canonical transcript
- **Output**: KPI events (NOT stored facts)
- **Event Types**:
  - Meeting duration
  - Participant engagement scores
  - Decision velocity
  - Action item count
  - Topic coverage
  
- **Example Event**:
  ```json
  {
    "event_type": "meeting.kpi.extracted",
    "meeting_id": "meeting_123",
    "kpis": {
      "duration_minutes": 45,
      "participant_count": 5,
      "decisions_made": 3,
      "tasks_created": 7,
      "engagement_score": 0.85
    },
    "timestamp": "2026-01-16T15:00:00Z"
  }
  ```

#### **Role-Aware View Generator**
- **Purpose**: Create personalized views based on user roles
- **Input**:
  - Canonical summaries
  - Final decisions
  - Workspace context (roles & permissions)
  
- **Output**: Role-specific knowledge artifacts
- **Examples**:
  - **Manager View**: Executive summary, decisions, team tasks
  - **Developer View**: Technical details, assigned tasks, code references
  - **Stakeholder View**: High-level outcomes, budget impacts
  
- **Access Control**:
  - Filters sensitive information
  - Applies permission policies
  - Redacts confidential content

---

### 5. Final Persistent Outputs

#### **Knowledge Base (Authoritative Writes)**
- **Type**: Vector Database + Relational Store
- **Content Written**:
  - Canonical transcripts
  - Authoritative summaries
  - Decisions and tasks
  - Role-aware views
  
- **Characteristics**:
  - Versioned (immutable history)
  - Auditable (who, when, why)
  - Searchable (full-text + semantic)
  
- **Schema Example**:
  ```sql
  CREATE TABLE meeting_knowledge (
    id UUID PRIMARY KEY,
    meeting_id UUID NOT NULL,
    version INT NOT NULL,
    transcript TEXT NOT NULL,
    summary JSONB NOT NULL,
    decisions JSONB[],
    tasks JSONB[],
    created_at TIMESTAMP NOT NULL,
    created_by UUID NOT NULL
  );
  ```

#### **Analytics Event Bus**
- **Type**: Event Stream (Kafka)
- **Purpose**: Emit KPI events for analytics
- **Consumers**:
  - Analytics dashboards
  - Reporting services
  - ML training pipelines
  
- **Event Topics**:
  - `meeting.kpi.extracted.v1`
  - `meeting.insights.generated.v1`
  - `meeting.quality.assessed.v1`

---

## Detailed Process Flow

### Phase 1: Workflow Initiation
```
1. Meeting Service detects meeting end
2. Publishes "Meeting Ended Event"
3. Temporal Workflow Orchestrator receives event
4. Validates meeting completion status
5. Initiates Batch AI workflow
```

### Phase 2: Transcription
```
1. Temporal triggers Batch STT Service
2. STT loads full audio from S3 (DE Layer output)
3. Processes audio with high-accuracy model
4. Generates raw transcript with speaker labels
5. Outputs to Transcript Corrector
```

### Phase 3: Correction & Normalization
```
1. Transcript Corrector receives raw transcript
2. Applies grammar and punctuation fixes
3. Normalizes technical terms
4. Ensures speaker label consistency
5. Produces canonical transcript
6. Broadcasts to parallel processors
```

### Phase 4: Parallel Intelligence Extraction
```
┌─ Canonical Transcript ─┐
│                         │
├─→ Summarization Engine ─→ Multi-level summaries
├─→ Decision Extractor ───→ Decisions & tasks
└─→ KPI Extractor ────────→ Analytics events
```

**Summarization Engine**:
- Reads provisional hints (optional optimization)
- Queries Knowledge Base for context
- Queries RAG for historical relevance
- Generates hierarchical summaries
- Validates against canonical transcript

**Decision Extractor**:
- Identifies decision points in transcript
- Extracts action items
- Links decisions to tasks
- Assigns ownership

**KPI Extractor**:
- Calculates meeting metrics
- Generates analytics events
- Emits to Analytics Event Bus

### Phase 5: Role-Aware View Generation
```
1. Role-Aware View Generator receives:
   - Canonical summaries
   - Final decisions
2. Reads Workspace Context for roles
3. Generates personalized views per role
4. Applies access control filters
5. Outputs role-specific artifacts
```

### Phase 6: Persistence
```
1. Role-Aware Views → Knowledge Base (Write)
2. KPI Events → Analytics Event Bus
3. Temporal marks workflow complete
4. Notifications sent to participants
```

---

## Node Descriptions

### Input Nodes

| Node | Type | Description | Data Format |
|------|------|-------------|-------------|
| Meeting Ended Event | Trigger | Signals meeting completion | JSON event payload |
| Raw Audio | Storage | Full meeting recording | 16kHz Mono WAV |

### Context Nodes (Read-Only)

| Node | Type | Description | Usage |
|------|------|-------------|-------|
| Provisional Intelligence | Hint | RT AI outputs | Optimization only |
| Knowledge Base | Database | Historical knowledge | Contextual reference |
| RAG / Search Engine | Service | Semantic search | Historical context |
| Workspace Context | Config | Roles & policies | Access control |

### Processing Nodes

| Node | Type | Description | Output |
|------|------|-------------|--------|
| Temporal Orchestrator | Workflow | Coordinates execution | State transitions |
| Batch STT Service | AI Service | High-accuracy transcription | Raw transcript |
| Transcript Corrector | NLP Service | Accuracy normalization | Canonical transcript |
| Summarization Engine | AI Service | Multi-level summaries | Summary hierarchy |
| Decision Extractor | AI Service | Decision & task extraction | Structured decisions |
| KPI Extractor | Analytics | Metrics extraction | KPI events |
| Role-Aware View Generator | Transform | Personalized views | Role-specific artifacts |

### Output Nodes

| Node | Type | Description | Consumers |
|------|------|-------------|-----------|
| Knowledge Base | Database | Authoritative storage | Search, UI, APIs |
| Analytics Event Bus | Event Stream | KPI events | Dashboards, ML |

---

## Data Flow Patterns

### 1. Main Pipeline (Thick Lines)
```
BatchSTT ══> TxCorrector ══> Summarizer
                         ══> DecisionExtractor
                         ══> KPIExtractor
```
- **Thick arrows** indicate authoritative data flow
- Data is canonical and trusted
- No external influence on core pipeline

### 2. Context Injection (Dotted Lines)
```
ProvisionalHint -.-> Summarizer (optimization hints)
KnowledgeBase -.-> Summarizer (contextual reference)
RAG -.-> Summarizer (historical context)
WorkspaceCtx -.-> RoleAdapter (roles & permissions)
```
- **Dotted arrows** indicate contextual inputs
- Non-authoritative
- Used for enhancement, not truth

### 3. Output Flow (Solid Lines)
```
Summarizer ──> RoleAdapter ──> KnowledgeWrite
DecisionExtractor ──> RoleAdapter ──> KnowledgeWrite
KPIExtractor ──> AnalyticsBus
```
- Final outputs are persisted
- Versioned and auditable

---

## Complete Workflow Example

### Scenario
A 45-minute product planning meeting with 5 participants discussing Q1 roadmap.

### Step-by-Step Execution

#### **Step 1: Meeting Ends**
```
Time: 2026-01-16 15:00:00
Event: meeting.ended.v1
Payload: {
  "meeting_id": "mtg_abc123",
  "workspace_id": "ws_xyz789",
  "participants": ["user_1", "user_2", "user_3", "user_4", "user_5"],
  "duration_minutes": 45,
  "audio_s3_path": "s3://processed-audio/mtg_abc123/normalized.wav"
}
```

#### **Step 2: Temporal Workflow Starts**
```
Workflow ID: wf_mtg_abc123_batch_ai
Status: RUNNING
Step: Validate meeting completion
```

#### **Step 3: Batch STT Processing**
```
Input: s3://processed-audio/mtg_abc123/normalized.wav
Processing: 
  - Load audio (45 min, 16kHz, Mono)
  - Apply Whisper Large V3 model
  - Speaker diarization (5 speakers detected)
  - Generate timestamps

Output (Raw Transcript):
---
[00:00:12] Speaker_1: "Okay everyone, let's start with the Q1 roadmap review."
[00:01:45] Speaker_2: "I think we should prioritize the mobile app redesign."
[00:03:22] Speaker_3: "Agreed, but we also need to address the API performance issues."
...
[44:23] Speaker_1: "Great, so we've decided to move forward with the mobile redesign and API optimization. Tasks assigned. Meeting adjourned."
---
```

#### **Step 4: Transcript Correction**
```
Input: Raw transcript (above)
Processing:
  - Fix grammar and punctuation
  - Normalize technical terms ("API" → "API")
  - Remove filler words
  - Ensure speaker consistency

Output (Canonical Transcript):
---
[00:00:12] John (Product Manager): "Okay everyone, let's start with the Q1 roadmap review."
[00:01:45] Sarah (Designer): "I think we should prioritize the mobile app redesign."
[00:03:22] Mike (Backend Engineer): "Agreed, but we also need to address the API performance issues."
...
[44:23] John (Product Manager): "Great, so we've decided to move forward with the mobile redesign and API optimization. Tasks assigned. Meeting adjourned."
---
```

#### **Step 5: Parallel Processing**

##### **5a. Summarization Engine**
```
Input: Canonical transcript
Context Queries:
  - Knowledge Base: "Previous Q1 planning meetings"
  - RAG: "Mobile app redesign discussions"
  - Provisional Hint: "Draft summary from RT AI"

Processing:
  1. Segment transcript by topics:
     - Mobile app redesign (15 min)
     - API performance (20 min)
     - Resource allocation (10 min)
  
  2. Extract key points per segment
  3. Synthesize with historical context
  4. Generate summaries

Output:
{
  "executive_summary": "Team decided to prioritize mobile app redesign and API optimization for Q1. Resources allocated, timeline set for 8-week delivery.",
  
  "detailed_summary": "The team reviewed Q1 priorities and agreed on two main initiatives: (1) Mobile app redesign to improve user experience, targeting a March 15 launch. (2) API performance optimization to reduce latency by 40%. Sarah will lead design, Mike will handle backend work. Budget approved at $50K.",
  
  "section_summaries": [
    {
      "topic": "Mobile App Redesign",
      "duration_minutes": 15,
      "key_points": [
        "Current app has poor UX ratings (2.3/5)",
        "Redesign will focus on navigation and visual appeal",
        "Target launch: March 15, 2026"
      ]
    },
    {
      "topic": "API Performance",
      "duration_minutes": 20,
      "key_points": [
        "Current latency: 800ms average",
        "Goal: Reduce to 480ms (40% improvement)",
        "Will implement caching and query optimization"
      ]
    }
  ]
}
```

##### **5b. Decision & Task Extractor**
```
Input: Canonical transcript

Output:
{
  "decisions": [
    {
      "decision_id": "dec_001",
      "description": "Prioritize mobile app redesign for Q1",
      "made_by": ["user_1", "user_2", "user_3"],
      "timestamp": "2026-01-16T14:23:00Z",
      "rationale": "Low user satisfaction (2.3/5 rating)",
      "impact": "high"
    },
    {
      "decision_id": "dec_002",
      "description": "Allocate $50K budget for Q1 initiatives",
      "made_by": ["user_1"],
      "timestamp": "2026-01-16T14:35:00Z",
      "rationale": "Required for design and development resources",
      "impact": "medium"
    }
  ],
  
  "tasks": [
    {
      "task_id": "task_001",
      "title": "Create mobile app wireframes",
      "assigned_to": "user_2",
      "due_date": "2026-01-30",
      "priority": "high",
      "context": "Part of mobile redesign initiative"
    },
    {
      "task_id": "task_002",
      "title": "Implement API caching layer",
      "assigned_to": "user_3",
      "due_date": "2026-02-15",
      "priority": "high",
      "context": "To reduce API latency by 40%"
    }
  ]
}
```

##### **5c. KPI Extractor**
```
Input: Canonical transcript

Output (Analytics Event):
{
  "event_type": "meeting.kpi.extracted",
  "meeting_id": "mtg_abc123",
  "timestamp": "2026-01-16T15:05:00Z",
  "kpis": {
    "duration_minutes": 45,
    "participant_count": 5,
    "decisions_made": 2,
    "tasks_created": 7,
    "engagement_score": 0.85,
    "topics_discussed": 3,
    "budget_allocated": 50000,
    "speaking_time_distribution": {
      "user_1": 0.30,
      "user_2": 0.25,
      "user_3": 0.20,
      "user_4": 0.15,
      "user_5": 0.10
    }
  }
}

→ Emitted to Analytics Event Bus
```

#### **Step 6: Role-Aware View Generation**
```
Input:
  - Summaries (from Summarization Engine)
  - Decisions & Tasks (from Decision Extractor)
  - Workspace Context (roles & permissions)

Processing:
  1. Identify participant roles:
     - user_1: Product Manager
     - user_2: Designer
     - user_3: Backend Engineer
     - user_4: Frontend Engineer
     - user_5: Stakeholder
  
  2. Generate role-specific views

Output:

--- Manager View (user_1) ---
{
  "summary": "Executive summary + detailed summary",
  "decisions": [All decisions],
  "team_tasks": [All tasks with assignments],
  "budget": "$50K allocated",
  "next_steps": "Review wireframes by Jan 30"
}

--- Designer View (user_2) ---
{
  "summary": "Design-focused summary",
  "my_tasks": [
    "Create mobile app wireframes (Due: Jan 30)"
  ],
  "design_decisions": [
    "Focus on navigation and visual appeal"
  ],
  "resources": "Design budget: $15K"
}

--- Engineer View (user_3) ---
{
  "summary": "Technical summary",
  "my_tasks": [
    "Implement API caching layer (Due: Feb 15)"
  ],
  "technical_decisions": [
    "API latency target: 480ms (40% reduction)"
  ],
  "specifications": "Caching + query optimization"
}

--- Stakeholder View (user_5) ---
{
  "summary": "Executive summary only",
  "key_outcomes": [
    "Mobile redesign: March 15 launch",
    "API optimization: 40% faster"
  ],
  "budget": "$50K",
  "risks": "Timeline dependent on resource availability"
}
```

#### **Step 7: Persistence**
```
Knowledge Base Write:
  - Canonical transcript → meeting_transcripts table
  - Summaries → meeting_summaries table
  - Decisions → decisions table
  - Tasks → tasks table
  - Role views → user_meeting_views table

Analytics Event Bus:
  - KPI event → meeting.kpi.extracted.v1 topic

Temporal Workflow:
  - Status: COMPLETED
  - Duration: 8 minutes
  - All steps successful
```

#### **Step 8: Notifications**
```
Participants receive:
  - Email: "Meeting summary ready"
  - In-app notification
  - Link to personalized view

Example (user_2 - Designer):
  "Your Q1 Planning Meeting summary is ready. You have 1 new task: Create mobile app wireframes (Due: Jan 30)"
```

---

## Key Differences from DE Layer

| Aspect | DE Layer | AI Layer |
|--------|----------|----------|
| **Input** | Raw uploaded audio | Processed audio chunks |
| **Focus** | Audio quality & preparation | Intelligence extraction |
| **Output** | Clean audio chunks | Knowledge artifacts |
| **Processing** | Signal processing (FFT, normalization) | NLP & AI models |
| **Orchestration** | Event-driven (Kafka) | Workflow-driven (Temporal) |
| **Idempotency** | Redis guards | Temporal replay |
| **Failure Handling** | Retry workers | Workflow retry |

---

## Summary

The AI Batch Processing Layer transforms processed audio into authoritative knowledge through:

1. **High-accuracy transcription** (Batch STT)
2. **Canonical correction** (Transcript Corrector)
3. **Intelligent extraction** (Summarization, Decisions, KPIs)
4. **Role-aware personalization** (View Generator)
5. **Persistent storage** (Knowledge Base)

All processing is:
- ✅ Deterministic and replayable
- ✅ Context-aware but source-authoritative
- ✅ Versioned and auditable
- ✅ Role-based and secure

The layer ensures that **truth is always derived from raw audio**, never from provisional or incremental outputs, making it the **single source of truth** for meeting intelligence.
