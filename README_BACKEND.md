# GitChat Backend Terminal Testing Guide

This guide explains how to test the GitChat backend directly from your terminal.

## Prerequisites

1.  **Environment Variables**: Ensure your `.env` file in the root directory contains the following:
    *   `GEMINI_API_KEY`: Your Google Gemini API key.
    *   `PINECONE_API_KEY`: Your Pinecone API key.
    *   `SUPABASE_URL`: Your Supabase project URL.
    *   `SUPABASE_ANON_KEY`: Your Supabase anonymous key.

2.  **Dependencies**: Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

## Step 1: Ingest a Repository

Use `ingest.py` to clone, sanitize, and chunk a GitHub repository.

```bash
python ingest.py https://github.com/owner/repo
```

This will:
- Validate the URL.
- Fetch metadata from GitHub.
- Clone the repository into the `repos/` directory.
- Sanitize the files (remove noise).
- Extract functions and classes into chunks.
- Store chunks in Supabase with `embedding_status = 'pending'`.

## Step 2: Generate Embeddings

Run the `embedding_worker.py` script to vectorize the chunks and upload them to Pinecone.

```bash
python embedding_worker.py
```

*Leave this running or run it until all chunks are processed.* You can see progress in the terminal.

## Step 3: Chat with the Codebase

Once embedding is complete, use `chat.py` to start an interactive terminal chat.

```bash
python chat.py <REPO_ID>
```

*Note: You can find the `<REPO_ID>` (a SHA256 hash) in the output of `ingest.py` or in your Supabase `repositories` table.*

## Optional: Run the API Server

If you want to test the FastAPI endpoints directly (e.g., using `curl` or Postman):

```bash
uvicorn backend.main:app --reload
```

Endpoints:
- `POST /repos/ingest`
- `GET /repos/{repo_id}/status`
- `POST /chat`
