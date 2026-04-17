import os
import time
from supabase import create_client
from google import genai
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv

load_dotenv()

# CONFIG
EMBEDDING_MODEL = "models/gemini-embedding-001"
# Set to 3072 for Gemini models
PINECONE_DIMENSION = 3072
BATCH_SIZE = 20

def init_pinecone():
    """Initializes the Pinecone index, creating it if it doesn't exist."""
    pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
    index_name = "gitchat"
    
    if index_name not in [i.name for i in pc.list_indexes()]:
        print(f"Creating Pinecone index '{index_name}' with dimension {PINECONE_DIMENSION}...")
        pc.create_index(
            name=index_name,
            dimension=PINECONE_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
        print("Waiting for index to be ready...")
        time.sleep(10) # Give it a moment to initialize
    
    return pc.Index(index_name)

def get_gemini_embeddings(texts: list[str]) -> list[list[float]]:
    """Retrieve embeddings for a list of text strings using the Gemini API."""
    try:
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=texts,
        )
        return [e.values for e in response.embeddings]
    except Exception as e:
        print(f"Error fetching embeddings from Gemini: {e}")
        return []

def fetch_pending_chunks(batch_size):
    """Fetches a batch of pending chunks from the database."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    supabase = create_client(url, key)
    
    try:
        response = supabase.table("chunks") \
            .select("chunk_id, repo_id, code, file_path, symbol_name, code_hash, embedding_status") \
            .eq("embedding_status", "pending") \
            .limit(batch_size) \
            .execute()
        return response.data
    except Exception as e:
        print(f"Failed to fetch pending chunks: {e}")
        return []

def mark_chunks_as_indexed(chunk_ids):
    """Updates the database status for successfully embedded chunks."""
    if not chunk_ids:
        return
        
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    supabase = create_client(url, key)
    
    try:
        # Supabase allows updating multiple rows matching an IN clause
        supabase.table("chunks") \
            .update({"embedding_status": "indexed"}) \
            .in_("chunk_id", chunk_ids) \
            .execute()
    except Exception as e:
        print(f"Failed to update chunk status: {e}")

def run_worker():
    print("--- Starting Embedding Worker ---")
    pinecone_index = init_pinecone()
    
    while True:
        # Fetch a batch of pending chunks
        batch = fetch_pending_chunks(BATCH_SIZE)
        
        if not batch:
            print("No more pending chunks. Worker sleeping for 60 seconds...")
            time.sleep(60)
            continue
            
        print(f"Processing batch of {len(batch)} chunks...")
        
        # Ensure Supabase client is available for duplicate checking
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_ANON_KEY")
        supabase = create_client(url, key)
        
        # Collect context to find existing indexed chunks
        batch_repos = list(set(row['repo_id'] for row in batch))
        batch_hashes = list(set(row['code_hash'] for row in batch))
        
        existing_res = supabase.table("chunks") \
            .select("repo_id, code_hash") \
            .in_("repo_id", batch_repos) \
            .in_("code_hash", batch_hashes) \
            .eq("embedding_status", "indexed") \
            .execute()
            
        indexed_repo_hashes = set(f"{r['repo_id']}_{r['code_hash']}" for r in existing_res.data) if existing_res.data else set()
        
        # Prepare data for embedding
        texts_to_embed = []
        vectors_to_upsert = []
        chunks_to_mark_indexed = []
        
        hashes_in_this_batch = set()
        
        for row in batch:
            chunk_id = row['chunk_id']
            repo_id = row['repo_id']
            code = row['code']
            file_path = row['file_path']
            symbol_name = row['symbol_name']
            code_hash = row['code_hash']
            
            repo_hash_key = f"{repo_id}_{code_hash}"
            chunks_to_mark_indexed.append(chunk_id)
            
            # If we've already embedded this code hash for this repo (either previously or in this batch), skip it
            if repo_hash_key in indexed_repo_hashes or repo_hash_key in hashes_in_this_batch:
                continue
                
            hashes_in_this_batch.add(repo_hash_key)
            
            # Reconstruct content logic
            context = f"File: {file_path}\n"
            if symbol_name:
                context += f"Symbol: {symbol_name}\n"
            context += f"\nCode:\n{code}\n"
            
            texts_to_embed.append(context)
            
            # Prepare the Pinecone upsert tuple (without the vector yet)
            vectors_to_upsert.append({
                "id": chunk_id,
                "values": None, # Will fill this next
                "metadata": {
                    "repo_id": repo_id,
                    "file_path": file_path,
                    "symbol_name": symbol_name if symbol_name else ""
                },
                "namespace": repo_id # Clean isolation
            })
            
        # Call the Gemini API only if we have unique chunks to embed
        if texts_to_embed:
            embeddings = get_gemini_embeddings(texts_to_embed)
            
            if not embeddings or len(embeddings) != len(texts_to_embed):
                print("Failed to generate embeddings. Retrying in 30 seconds...")
                time.sleep(30)
                continue
                
            # Group vectors by namespace (repo_id) for upserting
            namespaces = {}
            for i, vec_dict in enumerate(vectors_to_upsert):
                vec_dict["values"] = embeddings[i]
                ns = vec_dict.pop("namespace") # Extract namespace
                if ns not in namespaces:
                    namespaces[ns] = []
                namespaces[ns].append(vec_dict)
                
            # Upsert to Pinecone per namespace
            success = True
            for ns, vectors in namespaces.items():
                try:
                    pinecone_index.upsert(vectors=vectors, namespace=ns)
                except Exception as e:
                    print(f"Failed to upsert namespace {ns} to Pinecone: {e}")
                    success = False
                    break
                    
            if not success:
                print("Skipping database update due to Pinecone upsert failure.")
                time.sleep(10)
                continue
            
        # Mark chunks as indexed in local DB (including duplicates that skipped embedding)
        mark_chunks_as_indexed(chunks_to_mark_indexed)
        
        print(f"Successfully processed {len(batch)} chunks. (Embedded {len(texts_to_embed)}, Skipped {len(batch) - len(texts_to_embed)} duplicates)")
        
        # Free tier rate limit protection
        print("Sleeping for 12 seconds to respect rate limits...")
        time.sleep(12)

if __name__ == "__main__":
    run_worker()
