# Phase 1: GitChat Application

## Overview
GitChat is an application that ingests GitHub repositories and allows users to ask questions about the codebase using Retrieval-Augmented Generation (RAG). Phase 1 focuses on the core backend pipeline: from URL ingestion to a basic workable chat interface.

## Detailed Design: Repo Ingestion Flow

### Objective
Convert GitHub URL → Clean, structured repository data ready for parsing.

### Ingestion Pipeline
1. **User URL**
   ↓
2. **URL Validation**
   ↓
3. **Fetch Repo Metadata (GitHub API)**
   ↓
4. **Size Check & File Count Check**
   ↓
5. **Shallow Clone (`--depth 1`)**
   ↓
6. **Sanitize Directory**
   ↓
7. **Extract File Tree**
   ↓
8. **Language Detection**
   ↓
9. **Important File Detection**
   ↓
10. **Store Repo Metadata in DB**

### Step-by-Step Design

#### 1. URL Validation
Ensure valid GitHub format.
- **Extract:**
  - `owner`
  - `repo name`
- **Reject if:**
  - Not public (Phase 1)
  - Invalid URL
  - Repo too large

#### 2. Metadata Fetch (Before Cloning)
Use GitHub API to fetch:
- `default branch`
- `size`
- `number of files` (approx)
- `language`
- *If repo size > threshold (e.g., 5MB source), reject.*

#### 3. Clone Strategy
```bash
git clone --depth 1 --single-branch
```
- **Store in:** `/repos/{sha256(repo_url)}`

#### 4. Folder Sanitization
- **Remove:**
  - `.git`
  - `__pycache__`
  - `venv`
  - `node_modules`
  - `dist`
  - `build`
- **Ignore files:**
  - \> 1MB
  - Binary extensions

#### 5. Extract File Tree
**Output structure:**
```json
{
  "total_files": 123,
  "python_files": 78,
  "directories": ["..."],
  "important_files": ["README.md", "requirements.txt", "main.py"]
}
```

#### 6. Store Repository Record
**Status transitions:**
`created` → `cloned` → `parsed` → `embedded` → `ready`

## Detailed Design: Chunk Schema
We are doing function-level chunking. One function = one chunk.

### Chunk JSON Structure
```json
{
  "chunk_id": "uuid",
  "repo_id": "repo_hash",
  "file_path": "app/services/user_service.py",
  "symbol_name": "create_user",
  "symbol_type": "function",
  "start_line": 24,
  "end_line": 68,
  "language": "python",
  "code": "def create_user(...): ...",
  "summary": "Creates new user and stores in database",
  "embedding_vector_id": "vector_uuid",
  "keywords": ["user", "database", "create", "insert"]
}
```

### Important Fields Explained
| Field | Why Important |
|---|---|
| repo_id | Multi-repo support |
| file_path | Citation |
| start_line | Exact referencing |
| end_line | Bounding correctness |
| symbol_name | Better retrieval |
| summary | File-level embedding optional |
| language | For filtering |

### Additional Improvement (Optional but Powerful)
Add keyword index (e.g., `"keywords": ["user", "database", "create", "insert"]`). Extracted automatically to help hybrid retrieval.

## Progress Tracker

### 1. Repository Ingestion Pipeline (`ingest.py`) - **[COMPLETED]**
- **Objective:** Convert a GitHub URL into clean, structured repository data ready for parsing.
- **Features Implemented:**
  - **URL Validation:** Validates GitHub URLs and extracts owner/repo names.
  - **Metadata Fetching:** Uses the GitHub API to check repository size and visibility (restricts to public repos <= 5MB).
  - **Cloning:** Performs a shallow clone (`--depth 1`) to minimize download time and storage.
  - **Sanitization:** Removes unnecessary directories (e.g., `.git`, `node_modules`, `venv`, `__pycache__`) and ignores binary/large files to keep only meaningful source code.
  - **Tree Extraction:** Extracts metadata about the file structure, identifying total files, language-specific files, and important configuration files (`README.md`, `requirements.txt`, etc.).
  - **Status Logging:** Output tracking at each step (`[Status] created`, `[Status] cloning`, `[Status] parsed`).

### 2. File Parsing & Chunking (`chunker.py`) - **[COMPLETED]**
- **Objective:** Read the text content of the sanitized files and break them down into smaller, semantic chunks.
- **Features Implemented:**
  - Integrated `chunk_repository` directly into the ingestion script.
  - Developed AST-based parsing for `.py` files to systematically split code block by block (maintaining `function_name`, `start_line` and `end_line` mapping).
  - Implemented secondary fallback character-limit chunking for non-Python text files.
  - Stored resulting chunks in SQLite `repos.db` so they are fully prepared for vectorization.
- **Optimizations (Phase 2.5):**
  - **Deduplication**: Hashes the code to ensure we don't index duplicate blocks.
  - **AST Context**: Replaced raw string chunks with enriched context: prepends the top-of-file imports and records the `parent_class` for nested methods.
  - **Noise Reduction**: Completely discards functions `< 5 lines` and ignores `tests` directories during ingestion. This drastically improved quality on `pallets/click` (reducing ~1800 chunks to 782 high-value blocks).

### 3. Embedding Generation - **[COMPLETED]**
- **Date:** 2026-03-04
- **Objective:** Convert the text chunks into vector representations using an LLM embedding model.
- **Features Implemented:**
  - Integrated with the **Google Gemini API** (`models/gemini-embedding-001`).
  - Created `embedding_worker.py` as a continuously running background script.
  - Pulls pending batches asynchronously from the Supabase SQL database to respect free-tier API rate limits.

### 4. Vector Database Storage - **[COMPLETED]**
- **Date:** 2026-03-04
- **Objective:** Store the embeddings and chunk metadata in a database for fast similarity search.
- **Features Implemented:**
  - Initialized a **Pinecone Serverless Index** (`gitchat`) with a dimension of `3072` (matching Gemini).
  - Designed the storage schema to logically isolate vectors using Pinecone namespaces (`repo_id`).
  - Seamlessly updates `embedding_status` to `"indexed"` in Supabase after successful upserts.

### 5. Chat & Retrieval Interface (Phase 2 & 3) - **[COMPLETED]**
- **Date:** 2026-03-04
- **Objective:** Create an interface and HTTP API to ask questions against the ingested repository with extreme precision.
- **Features Implemented:**
  - **Hybrid Reranking:** Queries Pinecone for initial cosine similarity but re-ranks results locally against SQLite. Formula: `Pinecone (70%) + Keyword Overlap (25%) + Symbol Exact Match (10%) + File Importance (5%)`.
  - **Source Citations:** Appends strict tracking for the exact `file_path`, `start_line`, and `end_line` that the LLM used for its answer.
  - **Confidence Score & Failures:** Calculates an algorithmic Confidence ratio out of 1.0 based on initial retrieval scores. Automatically returns an explicit warning if the retrieved context score drops < 0.35.
  - **Retrieval Logging:** Silently commits a JSON record of every query, including top `chunk_ids` and scores, to `logs.json` for observability/auto-evaluation. 
  - **FastAPI HTTP Web Server:** Re-architected scripts into callable services. Hosted them behind endpoints `POST /repos/ingest`, `GET /repos/{repo_id}/status`, and `POST /chat` using FastAPI (`main.py`) to transition exactly into Web Product grade. 

### 6. Web Application UI & Repo Summary (Phase 4) - **[COMPLETED]**
- **Date:** 2026-03-04
- **Objective:** Build a Next.js front-end interface and integrate an automated repository summarization payload.
- **Features Implemented:**
  - **Automated Repo Summary:** Hooked Gemini 2.5 Flash into the Python ingestion pipeline queue to automatically analyze the `README.md` file. It mathematically calculates a concise technical summary and immediately saves it into the Supabase database.
  - **Next.js React Frontend:** Scaffolded a fast React frontend using Tailwind CSS components mapped to three robust pages:
    - **Initialization:** An input portal to post GitHub URLs out to the backend API (`page.tsx`).
    - **Progress Screen:** Live Web Poller that visually tracks ingestion chunking speeds and transition states (`repos/[repo_id]/status/page.tsx`).
    - **Chat Interface:** A highly styled chat interface highlighting the LLM conversational texts, displaying the exact source filename links, calculating a confidence progress bar, and broadcasting the Repo Summary context on the very top of the interface (`repos/[repo_id]/chat/page.tsx`).
  - **Cross-Origin Configuration:** Integrated `fastapi.middleware.cors` natively into the Py backend to securely allow frontend localhost browser proxying.

---
*This document will be updated continuously as we progress through the development steps.*
