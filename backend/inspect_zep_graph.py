from zep_cloud.client import Zep
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("ZEP_API_KEY")

def inspect_graph():
    graph_id = "mirofish_cfddc3a000d4484c"
    client = Zep(api_key=api_key)
    
    print(f"Inspecting graph: {graph_id}")
    try:
        # In v3.x, graph.get returns the graph data which might include nodes
        graph_data = client.graph.get(graph_id=graph_id)
        # Check nodes
        nodes = getattr(graph_data, 'nodes', [])
        print(f"Total nodes found: {len(nodes)}")
        for i, node in enumerate(nodes[:20]):
            print(f"{i}: {getattr(node, 'name', 'N/A')} - labels: {getattr(node, 'labels', [])}")
            
        if not nodes:
             print("Graph is empty or nodes are not in the response.")
             # Check for other methods if empty
             print(f"Graph data attributes: {dir(graph_data)}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_graph()
