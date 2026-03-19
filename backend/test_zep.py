import os
from dotenv import load_dotenv
from zep_cloud.client import Zep
import uuid

load_dotenv()

def test_zep_connectivity():
    api_key = os.getenv("ZEP_API_KEY")
    print(f"Testing Zep API Key (first 10 chars): {api_key[:10] if api_key else 'None'}...")
    
    if not api_key:
        print("Error: ZEP_API_KEY not found in .env")
        return False
        
    client = Zep(api_key=api_key)
    
    try:
        # Instead of list(), try a small operation like searching for a non-existent graph
        # or just try to create a dummy graph and delete it immediately.
        graph_id = f"test_auth_{uuid.uuid4().hex[:8]}"
        print(f"Attempting to create a temporary test graph: {graph_id}")
        
        client.graph.create(
            graph_id=graph_id,
            name="Auth Test",
            description="Testing API Key"
        )
        
        print("Success! Zep connectivity established (Graph created).")
        
        # Cleanup
        client.graph.delete(graph_id=graph_id)
        print("Cleanup: Test graph deleted.")
        return True
    except Exception as e:
        print(f"Zep Error: {type(e).__name__}: {e}")
        if "401" in str(e) or "unauthorized" in str(e).lower():
            print("CRITICAL RESULT: The Zep API Key is INVALID (401 Unauthorized).")
        return False

if __name__ == "__main__":
    test_zep_connectivity()
