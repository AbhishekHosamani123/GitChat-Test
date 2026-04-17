from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add the parent directory to the path so we can import the scripts as services
sys.path.append(str(Path(__file__).resolve().parent.parent))

from ingest import validate_github_url, fetch_repo_metadata, clone_repo, sanitize_repository, extract_file_tree
from chunker import chunk_repository
from chat import generate_chat_answer

import hashlib
from supabase import create_client

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="GitChat API", description="Phase 3 Web Backend for GitChat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=False, # Must be False if allow_origins is "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "GitChat API is running"}

# Models
class IngestRequest(BaseModel):
    repo_url: str

class ChatRequest(BaseModel):
    repo_id: str
    question: str

# Helper to get supabase client
def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    return create_client(url, key)

# Background Task for Ingestion
def generate_repo_summary(clone_path: Path) -> str:
    readme_text = ""
    for file in os.listdir(clone_path):
        if file.lower() == "readme.md":
            readme_path = clone_path / file
            try:
                with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
                    readme_text = f.read()[:5000] # Limit to 5000 chars
            except:
                pass
            break
            
    if not readme_text:
        return "No explicit README found. A codebase-level summary is not available for this repository."
        
    try:
        from google import genai
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        prompt = f"Summarize this repository in 2-3 sentences based on its README. Focus on the core purpose and tech stack:\n\n{readme_text}"
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        print(f"Summary generation failed: {e}")
        return "Summary generation failed."

def process_ingestion(repo_url: str, sha_name: str, owner: str, repo: str, metadata: dict):
    try:
        supabase = get_supabase()
        REPOS_DIR = Path("./repos")
        clone_path = REPOS_DIR / sha_name
        
        # 1. Clone
        clone_repo(repo_url, clone_path)
        
        # 2. Sanitize
        sanitize_repository(clone_path)
        
        # 3. Extract Tree
        structure = extract_file_tree(clone_path)
        
        # 4. Chunk
        chunks = chunk_repository(clone_path, sha_name)
        
        # 5. Generate Repo Summary
        summary = generate_repo_summary(clone_path)
        
        # 6. Update final DB status
        supabase.table("repositories").update({
            "total_files": structure['total_files'],
            "repo_summary": summary
        }).eq("repo_id", sha_name).execute()
        
    except Exception as e:
        print(f"Background ingestion failed for {repo_url}: {e}")

@app.post("/repos/add")
async def ingest_repo(request: IngestRequest, background_tasks: BackgroundTasks):
    try:
        owner, repo = validate_github_url(request.repo_url)
        metadata = fetch_repo_metadata(owner, repo)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    sha_name = hashlib.sha256(request.repo_url.encode()).hexdigest()
    
    supabase = get_supabase()
    
    # Check if we already processed this repository
    try:
        existing = supabase.table("repositories").select("total_files").eq("repo_id", sha_name).execute()
        if existing.data and existing.data[0].get("total_files", 0) > 0:
            print(f"Repository {request.repo_url} already exists in DB. Skipping re-ingestion.")
            return {
                "repo_id": sha_name,
                "status": "indexing"
            }
    except Exception as e:
        print(f"Cache check failed: {e}")
    
    # Save initial state to DB
    repo_data = {
        "repo_id": sha_name,
        "repo_url": request.repo_url,
        "name": repo,
        "owner": owner,
        "language": metadata['language'],
        "size_kb": metadata['size_kb'],
        "default_branch": metadata['default_branch']
    }
    supabase.table("repositories").upsert(repo_data).execute()
    
    # Fire off background task only if not already chunked
    background_tasks.add_task(process_ingestion, request.repo_url, sha_name, owner, repo, metadata)
    
    return {
        "repo_id": sha_name,
        "status": "indexing"
    }

@app.get("/repos/{repo_id}/status")
async def get_repo_status(repo_id: str):
    supabase = get_supabase()
    
    # Get repo info
    repo_res = supabase.table("repositories").select("*").eq("repo_id", repo_id).execute()
    if not repo_res.data:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    repo_info = repo_res.data[0]
    
    # Count chunks
    # Note: Supabase Python client doesn't have a clean count() yet without fetching data, 
    # but for this MVP we will fetch the ID list to count.
    chunks_res = supabase.table("chunks").select("embedding_status").eq("repo_id", repo_id).execute()
    
    total_chunks = len(chunks_res.data)
    indexed_chunks = sum(1 for c in chunks_res.data if c.get("embedding_status") == "indexed")
    pending_chunks = total_chunks - indexed_chunks
    
    # Determine overall status
    status = "completed"
    if total_chunks == 0:
        status = "parsing"
    elif pending_chunks > 0:
        status = "embedding"
        
    return {
        "repo_id": repo_id,
        "status": status,
        "files_processed": repo_info.get("total_files", 0),
        "chunks_total": total_chunks,
        "chunks_indexed": indexed_chunks,
        "chunks_pending": pending_chunks,
        "repo_summary": repo_info.get("repo_summary", "")
    }

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        # Call the refactored chat function
        answer, sources, confidence = generate_chat_answer(request.repo_id, request.question)
        return {
            "answer": answer,
            "sources": sources,
            "confidence": confidence
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
