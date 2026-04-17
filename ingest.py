import os
import re
import json
import hashlib
import shutil
import subprocess
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# =============================
# CONFIG
# =============================

MAX_REPO_SIZE_KB = 50000  # 50MB limit
MAX_FILE_SIZE_MB = 1
REPOS_DIR = Path("./repos")

def build_github_headers():
    headers = {
        "Accept": "application/vnd.github+json",
    }
    # Optional token avoids anonymous GitHub API rate limits on Render.
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    return headers

# =============================
# 1️⃣ URL VALIDATION
# =============================

def validate_github_url(url: str):
    cleaned_url = url.strip()
    pattern = r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$"
    match = re.match(pattern, cleaned_url)

    if not match:
        raise ValueError("Invalid GitHub URL")

    owner, repo = match.groups()
    return owner, repo


# =============================
# 2️⃣ FETCH METADATA
# =============================

def fetch_repo_metadata(owner, repo):
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    response = requests.get(api_url, headers=build_github_headers())

    if response.status_code == 404:
        raise Exception("Repository not found or is private.")

    if response.status_code == 403:
        try:
            payload = response.json()
            message = payload.get("message", "")
        except Exception:
            message = ""
        if "rate limit" in message.lower():
            raise Exception("GitHub API rate limit exceeded. Add GITHUB_TOKEN in backend env and retry.")
        raise Exception("GitHub API access forbidden. Check GitHub token permissions.")

    if response.status_code != 200:
        raise Exception(f"GitHub API request failed ({response.status_code}).")

    data = response.json()

    if data["private"]:
        raise Exception("Private repository not allowed in Phase 1.")

    if data["size"] > MAX_REPO_SIZE_KB:
        raise Exception("Repository exceeds size limit.")

    return {
        "default_branch": data["default_branch"],
        "size_kb": data["size"],
        "language": data["language"],
        "visibility": "public"
    }


# =============================
# 3️⃣ CLONE REPOSITORY
# =============================

import stat

def remove_readonly(func, path, excinfo):
    os.chmod(path, stat.S_IWRITE)
    func(path)

def safe_remove_directory(path):
    if path.exists():
        shutil.rmtree(path, onerror=remove_readonly)
    os.makedirs(path.parent, exist_ok=True)


def clone_repo(url, clone_path):
    safe_remove_directory(clone_path)

    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--single-branch", url, str(clone_path)],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise Exception(f"Git clone failed:\n{result.stderr}")


# =============================
# 4️⃣ SANITIZE DIRECTORY
# =============================

IGNORED_DIRS = {".git", "__pycache__", "node_modules", "venv", "dist", "build", "tests", "test", ".test", ".tests", ".github", ".vscode", ".idea"}
BINARY_EXTENSIONS = {".exe", ".dll", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".ico", ".svg", ".pdf", ".lock"}
IGNORED_EXTENSIONS = {".md", ".yaml", ".yml", ".json", ".xml", ".ini", ".cfg", ".conf", ".toml", ".txt"}
ALLOWED_CODE_EXTENSIONS = {".py", ".js", ".ts", ".java", ".go", ".c", ".cpp", ".h", ".hpp", ".rb", ".php", ".cs"}

def sanitize_repository(repo_path):
    for root, dirs, files in os.walk(repo_path):

        # Remove unwanted directories
        for d in list(dirs):
            if d.startswith(".") or d in IGNORED_DIRS:
                shutil.rmtree(Path(root) / d, onerror=remove_readonly)
                dirs.remove(d)

        # Remove large/binary/noise files
        for file in files:
            file_path = Path(root) / file
            
            # Remove hidden files (like .editorconfig, .gitignore)
            if file.startswith("."):
                file_path.unlink(missing_ok=True)
                continue

            # Remove binary and explicitly ignored extensions
            if file_path.suffix.lower() in BINARY_EXTENSIONS or file_path.suffix.lower() in IGNORED_EXTENSIONS:
                file_path.unlink(missing_ok=True)
                continue
                
            # If we decide to be strict about only keeping actual code files:
            # if file_path.suffix.lower() not in ALLOWED_CODE_EXTENSIONS:
            #     file_path.unlink(missing_ok=True)
            #     continue

            if file_path.stat().st_size > MAX_FILE_SIZE_MB * 1024 * 1024:
                file_path.unlink(missing_ok=True)


# =============================
# 5️⃣ EXTRACT FILE TREE
# =============================

def extract_file_tree(repo_path):
    total_files = 0
    python_files = 0
    directories = set()
    important_files = []

    for root, dirs, files in os.walk(repo_path):
        for d in dirs:
            directories.add(d)

        for file in files:
            total_files += 1
            if file.endswith(".py"):
                python_files += 1

            if file.lower() in ["readme.md", "requirements.txt", "main.py"]:
                important_files.append(file)

    return {
        "total_files": total_files,
        "python_files": python_files,
        "directories": list(directories),
        "important_files": important_files
    }


# =============================
# 6️⃣ MAIN INGESTION PIPELINE
# =============================

def ingest_repository(repo_url):

    print(f"\n--- Starting ingestion for: {repo_url} ---")

    # Status: created
    print("[Status] created")

    owner, repo = validate_github_url(repo_url)

    print("Fetching metadata...")
    metadata = fetch_repo_metadata(owner, repo)
    print("Metadata:", metadata)

    # Generate SHA256 folder
    sha_name = hashlib.sha256(repo_url.encode()).hexdigest()
    clone_path = REPOS_DIR / sha_name

    # Check if we should initialize the db first
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    supabase = create_client(url, key)
    
    # Save partial repo data to db immediately
    repo_data = {
        "repo_id": sha_name,
        "repo_url": repo_url,
        "name": repo,
        "owner": owner,
        "language": metadata['language'],
        "size_kb": metadata['size_kb'],
        "default_branch": metadata['default_branch']
    }
    
    try:
        supabase.table("repositories").upsert(repo_data).execute()
    except Exception as e:
        print(f"Failed to insert repository record: {e}")

    # Status: cloning
    print("[Status] cloning")
    clone_repo(repo_url, clone_path)

    print("Sanitizing...")
    sanitize_repository(clone_path)

    print("Extracting file tree...")
    structure = extract_file_tree(clone_path)

    # Status: chunking
    print("[Status] chunking")
    from chunker import chunk_repository
    chunks = chunk_repository(clone_path, sha_name)

    # Status: parsed
    print("[Status] parsed")
    
    # Update repository table with final data
    try:
        supabase.table("repositories").update({
            "total_files": structure['total_files']
        }).eq("repo_id", sha_name).execute()
    except Exception as e:
         print(f"Failed to update repository record: {e}")

    final_output = {
        "repo_url": repo_url,
        "metadata": metadata,
        "structure": structure,
        "chunks_extracted": len(chunks)
    }

    print("\n[SUCCESS] Ingestion Complete")
    print(json.dumps(final_output, indent=2))

    return final_output


# =============================
# ENTRY
# =============================

if __name__ == "__main__":
    import sys
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/pallets/click"
    ingest_repository(test_url)