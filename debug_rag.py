import os
from dotenv import load_dotenv
from supabase import create_client
from pinecone import Pinecone

load_dotenv()

print("--- Check 1: Supabase Chunk Status ---")
try:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    supabase = create_client(url, key)

    response = supabase.table("chunks").select("embedding_status").execute()
    status_counts = {}
    for row in response.data:
        status = row.get("embedding_status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    for status, count in status_counts.items():
        print(f"{status} | {count}")
    print(f"Total chunks: {len(response.data)}")
except Exception as e:
    print(f"Error checking Supabase: {e}")

print("\n--- Check 2: Pinecone Stats ---")
try:
    pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
    index = pc.Index("gitchat")
    print(index.describe_index_stats())
except Exception as e:
    print(f"Error checking Pinecone: {e}")
