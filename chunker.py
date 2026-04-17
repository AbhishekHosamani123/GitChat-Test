import os
import ast
import json
import hashlib
import time
from pathlib import Path
from google import genai
from dotenv import load_dotenv

load_dotenv()

# CONFIG
CHUNK_SIZE_LIMIT = 2000 # fallback chunk character limit for text files
MIN_AST_LINES = 5

import re

# Initialize Gemini Client for Summarization
try:
    gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
except Exception as e:
    gemini_client = None
    print(f"Warning: Could not initialize Gemini client: {e}")

# Basic stopwords for heuristic extraction
STOPWORDS = {"and", "the", "for", "with", "this", "that", "from", "into", "onto", "upon", "returns", "gets", "sets", "is", "are"}

def extract_heuristic_metadata(node: ast.AST, symbol_name: str, file_path: str) -> tuple[str, list[str]]:
    """Generates a deterministic summary and keywords using AST without calling an LLM."""
    summary = ""
    keywords = set()
    
    # 1. Extract base keywords from name (e.g., validate_user_input -> validate, user, input)
    name_parts = [p.lower() for p in symbol_name.replace('.', '_').split('_') if len(p) > 2]
    for p in name_parts:
        if p not in STOPWORDS:
            keywords.add(p)

    # 2. Extract docstring if present for summary
    docstring = ast.get_docstring(node)
    if docstring:
        lines = docstring.strip().split('\n')
        if lines:
            summary = lines[0].strip() # Use first sentence of docstring
            
        # Add a few docstring words to keywords
        words = "".join(c if c.isalnum() else " " for c in docstring).split()
        for w in words:
            w_low = w.lower()
            if len(w_low) > 3 and w_low not in STOPWORDS:
                keywords.add(w_low)

    # 3. Analyze AST Node type
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        verb = name_parts[0] if name_parts else "processes"
        if not summary:
            # Build heuristic summary
            summary = f"Function {symbol_name} handles logic to {verb}."
            
        # Check arguments for keywords
        for arg in node.args.args:
            arg_name = arg.arg.lower()
            if len(arg_name) > 2 and arg_name not in STOPWORDS:
                keywords.add(arg_name)
    
    elif isinstance(node, ast.ClassDef):
        if not summary:
            summary = f"Class {symbol_name} defines structure and methods."
            
    # Clean up keywords and limit to 10
    final_keywords = list(keywords)[:10]
    
    return summary, final_keywords

def generate_llm_metadata(code_text: str, file_path: str, symbol_name: str) -> tuple[str, list[str]]:
    """Uses Gemini to generate a concise summary and keywords for a code chunk."""
    if not gemini_client:
        return "", []
        
    prompt = f"""
    Analyze the following code chunk from file '{file_path}'.
    Component: {symbol_name}
    
    Code:
    ```
    {code_text}
    ```
    
    Provide two things:
    1. A single concise sentence summarizing what this code does.
    2. A JSON array of 5-10 highly relevant keywords or concepts (e.g. ["authentication", "database", "user_login"]).
    
    Format your response EXACTLY like this:
    SUMMARY: [Your one sentence summary]
    KEYWORDS: ["keyword1", "keyword2", ...]
    """
    
    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.1,
            )
        )
        
        text = response.text
        summary = ""
        keywords = []
        
        for line in text.splitlines():
            if line.startswith("SUMMARY:"):
                summary = line.replace("SUMMARY:", "").strip()
            elif line.startswith("KEYWORDS:"):
                try:
                    kw_text = line.replace("KEYWORDS:", "").strip()
                    if kw_text.startswith("```json"):
                        kw_text = kw_text[7:].strip()
                    if kw_text.endswith("```"):
                        kw_text = kw_text[:-3].strip()
                    keywords = json.loads(kw_text)
                except Exception:
                    pass
                    
        time.sleep(0.5)
        return summary, keywords
        
    except Exception as e:
        print(f"Failed to generate LLM metadata: {e}")
        return None, None # Signal fallback needed

def init_chunk_db():
    # Since we are using Supabase, we don't need to manually create tables here.
    # The tables should already be created in the Supabase SQL Editor.
    pass

def save_chunks_to_db(chunks):
    if not chunks:
        return
        
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    supabase = create_client(url, key)
    
    records = []
    for c in chunks:
        records.append({
            "chunk_id": c['chunk_id'],
            "repo_id": c['repo_id'],
            "file_path": c['file_path'],
            "symbol_name": c.get('symbol_name', ''),  # Use exact column names based on the SQLite PRAGMA
            "symbol_type": c.get('symbol_type', 'function'),
            "start_line": c.get('start_line', 0),
            "end_line": c.get('end_line', 0),
            "language": c.get('language', 'python'),
            "code": c['code'],
            "summary": c.get('summary', ''),
            "keywords": c.get('keywords', []),
            "code_hash": c['code_hash'],
            "embedding_status": 'pending'
        })
        
    # Supabase allows bulk inserts by passing a list of dicts
    try:
        # We process in batches of 100 to avoid request size limits
        batch_size = 100
        total_inserted = 0
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            response = supabase.table("chunks").upsert(batch).execute()
            total_inserted += len(response.data)
            
        print(f"[DB] Saved {total_inserted} chunks to Supabase.")
    except Exception as e:
        print(f"Failed to insert chunks: {e}")

def extract_python_chunks(file_path: Path, repo_id: str, repo_root: Path) -> list:
    """Parses a Python file using AST and extracts high-quality functions and classes."""
    chunks = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
            lines = source.splitlines()
    except Exception as e:
        return chunks

    try:
        tree = ast.parse(source)
    except Exception as e:
        return chunks
        
    rel_path = file_path.relative_to(repo_root).as_posix()

    # Gather global imports to prepend for context
    file_imports = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            start = node.lineno - 1
            end = getattr(node, "end_lineno", node.lineno)
            file_imports.append("\n".join(lines[start:end]))
    
    preamble = "\n".join(file_imports)
    if preamble:
        preamble = f"### IMPORTS ###\n{preamble}\n\n"

    # Global structure prep for chunker logic
    # We no longer use simple docstring extraction
    pass

    # We use a custom NodeVisitor to keep track of parent classes
    class ChunkVisitor(ast.NodeVisitor):
        def __init__(self):
            self.current_class = None

        def visit_ClassDef(self, node):
            old_class = self.current_class
            self.current_class = node.name
            
            # We no longer make class-level chunks - "One function = one chunk."
            # Visit children (methods)
            self.generic_visit(node)
            self.current_class = old_class

        def visit_FunctionDef(self, node):
            self._make_chunk(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            self._make_chunk(node)
            self.generic_visit(node)

        def _make_chunk(self, node):
            start_line = node.lineno
            end_line = getattr(node, "end_lineno", start_line)
            
            # Skip tiny chunks
            if (end_line - start_line + 1) < MIN_AST_LINES:
                return
                
            raw_code = "\n".join(lines[start_line - 1:end_line])
            
            symbol_name = node.name
            if self.current_class:
                symbol_name = f"{self.current_class}.{node.name}"
                
            # Reconstruct with context BEFORE summary extraction
            context_header = f"### CONTEXT ###\nFile: {rel_path}\n"
            context_header += f"Component: {symbol_name}\n\n"
            final_code = preamble + context_header + raw_code
            
            # 1. Try LLM Metadata (Optional Phase 3)
            # summary, keywords = generate_llm_metadata(raw_code, rel_path, symbol_name)
            
            # 2. Heuristic Metadata (Phases 1 & 2)
            summary, keywords = extract_heuristic_metadata(node, symbol_name, rel_path)
            
            # Deduplication hash
            code_hash = hashlib.sha256(final_code.encode()).hexdigest()
            chunk_id = hashlib.sha1(f"{repo_id}_{file_path}_{symbol_name}_{start_line}".encode()).hexdigest()
            
            chunks.append({
                "chunk_id": chunk_id,
                "repo_id": repo_id,
                "file_path": rel_path,
                "symbol_name": symbol_name,
                "symbol_type": "function",
                "start_line": start_line,
                "end_line": end_line,
                "language": "python",
                "code": final_code,
                "summary": summary,
                "keywords": keywords,
                "code_hash": code_hash
            })

    visitor = ChunkVisitor()
    visitor.visit(tree)

    return chunks

def extract_text_chunks(file_path: Path, repo_id: str, repo_root: Path) -> list:
    chunks = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return chunks

    rel_path = file_path.relative_to(repo_root).as_posix()
    
    current_chunk_lines = []
    current_length = 0
    start_line = 1
    
    for i, line in enumerate(lines):
        current_chunk_lines.append(line)
        current_length += len(line)
        
        if current_length >= CHUNK_SIZE_LIMIT or i == len(lines) - 1:
            end_line = i + 1
            code = "".join(current_chunk_lines).strip()
            
            if code:
                # Add basic context for naive text chunks too
                final_code = f"### CONTEXT ###\nFile: {rel_path}\n\n{code}"
                code_hash = hashlib.sha256(final_code.encode()).hexdigest()
                chunk_id = hashlib.sha1(f"{repo_id}_{file_path}_txt_{start_line}".encode()).hexdigest()
                
                # Generate Heuristic Baseline
                summary = f"Text document chunk from {rel_path}"
                keywords = [w for w in rel_path.replace('.', '/').split('/') if len(w) > 2]
                
                chunks.append({
                    "chunk_id": chunk_id,
                    "repo_id": repo_id,
                    "file_path": rel_path,
                    "symbol_name": "",
                    "symbol_type": "text",
                    "start_line": start_line,
                    "end_line": end_line,
                    "language": file_path.suffix.lstrip('.') if file_path.suffix else "text",
                    "code": final_code,
                    "summary": summary,
                    "keywords": keywords,
                    "code_hash": code_hash
                })
            
            current_chunk_lines = []
            current_length = 0
            start_line = end_line + 1
            
    return chunks

def chunk_repository(repo_path: Path, repo_id: str):
    init_chunk_db()
    
    print(f"\n--- Starting Semantic Chunking for: {repo_id} ---")
    all_chunks = []
    
    for root, dirs, files in os.walk(repo_path):
        # Additional safety check to skip hidden directories that might have lingered
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            # Skip hidden files
            if file.startswith('.'):
                continue
                
            file_path = Path(root) / file
            
            if file_path.suffix == ".py":
                chunks = extract_python_chunks(file_path, repo_id, repo_path)
            elif file_path.suffix in [".js", ".ts", ".java", ".go"]: # Added support for other code files
                chunks = extract_text_chunks(file_path, repo_id, repo_path)
            else:
                continue # Skip all other text/config files for now
                
            all_chunks.extend(chunks)
            
    save_chunks_to_db(all_chunks)
    print(f"[SUCCESS] Chunking Complete. Created {len(all_chunks)} chunks total.")
    return all_chunks

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        test_path = Path(sys.argv[1])
        test_id = sys.argv[2]
        if test_path.exists():
            chunk_repository(test_path, test_id)
        else:
            print(f"Path not found: {test_path}")
