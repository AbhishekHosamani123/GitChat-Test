import os
import sys
import json
import numpy as np
from google import genai
from google.genai import types
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

try:
    pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
    pinecone_index = pc.Index("gitchat")
except Exception as e:
    pinecone_index = None
    print(f"Warning: Could not initialize Pinecone: {e}")

# System prompt giving the LLM context of how to answer based on RAG
SYSTEM_PROMPT = """
You are an expert software engineer discussing a codebase with a user.
You will be provided with chunks of code retrieved from the repository based on the user's question.

Answer the user's question using ONLY the provided code context.
Be concise, clear, and refer back to the specific functions, classes, or files mentioned in the context.
If the answer cannot be found in the provided context, politely say so instead of making up an answer.
"""

def retrieve_context(query: str, repo_id: str, top_k: int = 5) -> tuple[str, list, float, list, list]:
    """Embeds the query, fetches top 20 from Pinecone, and reranks locally using Hybrid scoring."""
    try:
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        response = client.models.embed_content(
            model="models/gemini-embedding-001",
            contents=[query],
        )
        query_vector = response.embeddings[0].values
    except Exception as e:
        print(f"Error embedding query: {e}")
        return ""
    
    # 1. Query Pinecone
    if not pinecone_index:
        print("Pinecone not initialized.")
        return "", [], 0.0, [], []
        
    try:
        pc_results = pinecone_index.query(
            namespace=repo_id,
            vector=query_vector,
            top_k=5,
            include_metadata=True
        )
    except Exception as e:
        print(f"Pinecone query error: {e}")
        return ""
        
    if not pc_results.get('matches'):
        print(f"No matches found in Pinecone for {query}")
        return "", [], 0.0, [], []
        
    # Get the chunk IDs and Pinecone scores
    pinecone_scores = {match['id']: match['score'] for match in pc_results['matches']}
    chunk_ids = [match['id'] for match in pc_results.get('matches', [])]
    print(f"Pinecone matches: {chunk_ids}")
    
    if not chunk_ids:
        return "", [], 0.0, [], []
        
    # Calculate Confidence Score based on Pinecone raw scores
    raw_scores = [match['score'] for match in pc_results.get('matches', [])]
    avg_score = sum(raw_scores) / len(raw_scores) if raw_scores else 0
    top_score = raw_scores[0] if raw_scores else 0
    confidence = round((0.6 * top_score) + (0.4 * avg_score), 3)
        
    from supabase import create_client
    try:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_ANON_KEY")
        supabase = create_client(url, key)
        
        chunk_res = supabase.table("chunks").select("chunk_id, file_path, start_line, end_line, code, summary, symbol_name").in_("chunk_id", chunk_ids).eq("repo_id", repo_id).execute()
        rows = chunk_res.data
    except Exception as e:
        print(f"Failed to fetch chunk data from Supabase: {e}")
        return "", [], 0.0, [], []
    
    if not rows:
        print(f"No chunk data found in Supabase for IDs: {chunk_ids}")
        return "", [], 0.0, [], []
        
    results = []
    
    # Pre-process query for keywords
    query_words = set([w.lower() for w in query.replace('_', ' ').split() if len(w) > 2])
    
    # 3. Calculate Hybrid Score
    for row in rows:
        chunk_id = row['chunk_id']
        file_path = row['file_path']
        symbol_name = row.get('symbol_name', '') or ''
        summary = row.get('summary', '') or ''
        code = row.get('code', '') or ''
        start_line = row.get('start_line', '?')
        end_line = row.get('end_line', '?')
        
        # Base score from Pinecone
        pinecone_score = pinecone_scores.get(chunk_id, 0.0)
            
        # 2. Keyword Match Score (25% weight)
        # Compute keywords dynamically from available fields
        text_for_keywords = f"{file_path} {symbol_name} {summary}".lower()
        chunk_keywords = set([w for w in text_for_keywords.replace('_', ' ').replace('/', ' ').split() if len(w) > 2])
        keyword_overlap = len(query_words.intersection(chunk_keywords))
        keyword_match_score = min(keyword_overlap / max(len(query_words), 1), 1.0)
        
        # 3. Symbol Name Exact Match Boost (10% weight)
        symbol_name_exact_match_boost = 1.0 if any(w in symbol_name.lower() for w in query_words) else 0.0
        
        # 4. File Importance Score (5% weight)
        file_importance_score = 0.0
        path_lower = file_path.lower()
        if path_lower.startswith(('src/', 'app/', 'click/', 'lib/')):
            file_importance_score = 1.0
        elif path_lower.startswith(('examples/', 'docs/', 'tests/')):
            file_importance_score = -1.0 # Penalize mildly
            
        # Final hybrid score formula
        final_score = (
            (0.7 * pinecone_score) +
            (0.2 * keyword_match_score) +
            (0.1 * symbol_name_exact_match_boost) +
            (0.05 * file_importance_score)
        )
            
        results.append({
            "chunk_id": chunk_id,
            "file_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
            "symbol": symbol_name,
            "summary": summary,
            "code": code,
            "score": float(final_score),
            "sim": float(pinecone_score)
        })
        
    # Sort and take top_k
    results.sort(key=lambda x: x["score"], reverse=True)
    top_results = results[:top_k]
    boosted_scores = [res['score'] for res in top_results]
    
    # Build text string to pass to LLM
    context_str = "--- RETRIEVED CODE CONTEXT ---\n"
    for i, res in enumerate(top_results):
        context_str += f"\n[Document {i+1}] File: {res['file_path']} | Component: {res['symbol']} | Score: {res['score']:.2f}\n"
        if res['summary']:
            context_str += f"Description: {res['summary']}\n"
        context_str += f"Code:\n{res['code']}\n"
        context_str += "-"*40 + "\n"
        
    return context_str, top_results, confidence, chunk_ids, boosted_scores

def chat_interface(repo_id: str):
    print(f"\n[{repo_id}] GitChat CLI initialized.")
    print("Type 'exit' or 'quit' to leave.")
    print("-" * 50)
    
    try:
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    except Exception as e:
        print(f"Error initializing Gemini: {e}")
        return
        
    # Start a chat session that maintains history
    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
        )
    )

    while True:
        user_query = input("\n[You]: ").strip()
        if user_query.lower() in ['exit', 'quit', 'q']:
            print("Goodbye!")
            break
            
        if not user_query:
            continue
            
        print("Searching repository for context...")
        context, top_results, confidence, retrieved_ids, boosted_scores = retrieve_context(user_query, repo_id)
        
        if not context or not top_results:
            print("\n[GitChat]:\nNo relevant context found.")
            continue
            
        # Combine user query with the retrieved context
        augmented_prompt = f"User Question: {user_query}\n\n{context}"
        
        print("Generating answer...\n")
        try:
            # Send message to LLM (this maintains conversation history in `chat`)
            response = chat.send_message(augmented_prompt)
            answer = "Answer:\n" + response.text.strip()
            
            # 4. Failure Modes: Add warning if low confidence
            raw_scores = [res['sim'] for res in top_results]
            if raw_scores and raw_scores[0] < 0.35:
                answer += "\n\n⚠ Low retrieval confidence. Answer may be incomplete."
                
            # 1. Source Citations
            sources = []
            for row in top_results:
                sources.append(f"- {row['file_path']}: {row['start_line']}–{row['end_line']}")
            
            answer += "\n\nSources:\n" + "\n".join(sources)
            
            # 2. Confidence Score
            answer += f"\n\nConfidence: {confidence}"
            
            print(f"[GitChat]:\n{answer}")
            
            # 3. Retrieval Logging
            from datetime import datetime
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "query": user_query,
                "repo_id": repo_id,
                "retrieved_chunk_ids": retrieved_ids,
                "raw_scores": raw_scores,
                "boosted_scores": boosted_scores,
                "confidence": confidence,
                "response_length": len(answer)
            }
            with open("logs.json", "a") as f:
                f.write(json.dumps(log_entry) + "\n")
                
        except Exception as e:
            print(f"\n[Error generating response]: {e}")

def generate_chat_answer(repo_id: str, query: str) -> tuple[str, list, float]:
    """Generates an answer for a given query and repo, returning structured data for the API."""
    
    # Start a chat session (stateless for API currently)
    try:
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    except Exception as e:
        raise Exception(f"Error initializing Gemini: {e}")
        
    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
        )
    )
    
    context, top_results, confidence, retrieved_ids, boosted_scores = retrieve_context(query, repo_id)
    
    if not context or not top_results:
        return "No relevant context found.", [], 0.0
        
    augmented_prompt = f"User Question: {query}\n\n{context}"
    
    try:
        response = chat.send_message(augmented_prompt)
        answer = response.text.strip()
        
        # Format sources
        sources_list = []
        for row in top_results:
            sources_list.append({
                "file": row['file_path'],
                "start_line": row['start_line'],
                "end_line": row['end_line']
            })
            
        # Logging
        from datetime import datetime
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "repo_id": repo_id,
            "retrieved_chunk_ids": retrieved_ids,
            "raw_scores": [res['sim'] for res in top_results],
            "boosted_scores": boosted_scores,
            "confidence": confidence,
            "response_length": len(answer)
        }
        with open("logs.json", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
            
        return answer, sources_list, confidence
        
    except Exception as e:
        raise Exception(f"Failed to generate answer: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python chat.py <repo_id>")
        sys.exit(1)
        
    target_repo_id = sys.argv[1]
    chat_interface(target_repo_id)
