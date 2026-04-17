import os
from dotenv import load_dotenv
from pinecone import Pinecone
from google import genai

load_dotenv()

repo_id = "59f828ed3d490a539f0d4f45a408311a481b28d6eba483d28306e2d8bce069f5"

print("--- Check 3: Query Embedding ---")
try:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    response = client.models.embed_content(
        model="models/gemini-embedding-001",
        contents=["how does authentication work"],
    )
    query_vector = response.embeddings[0].values
    print(f"Embedding length: {len(query_vector)}")
except Exception as e:
    print("Embedding error:", e)
    query_vector = None

if query_vector:
    print("\n--- Check 4: Pinecone Query ---")
    try:
        pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
        index = pc.Index("gitchat")
        
        stats = index.describe_index_stats()
        print("Available Namespaces:", list(stats.get('namespaces', {}).keys()))
        
        results = index.query(
            namespace=repo_id,
            vector=query_vector,
            top_k=2,
            include_metadata=True
        )
        print("Matches found in namespace:", len(results.get('matches', [])))
        if results.get('matches'):
            for match in results['matches']:
                print(f" - score: {match['score']}, metadata keys: {list(match['metadata'].keys()) if 'metadata' in match else 'None'}")
    except Exception as e:
        print("Pinecone query error:", e)
