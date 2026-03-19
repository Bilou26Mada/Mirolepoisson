from zep_cloud.client import Zep
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("ZEP_API_KEY")
graph_id = "mirofish_cfddc3a000d4484c"

client = Zep(api_key=api_key)

print(f"Testing node retrieval for graph: {graph_id}")

# Try client.graph.node.get_by_graph_id
try:
    print("Trying client.graph.node.get_by_graph_id...")
    # This might require paging or just return a list
    nodes = client.graph.node.get_by_graph_id(graph_id=graph_id)
    print(f"Nodes found: {len(nodes) if hasattr(nodes, '__len__') else 'N/A'}")
    print(f"Nodes type: {type(nodes)}")
    if hasattr(nodes, '__iter__'):
        for i, node in enumerate(list(nodes)[:5]):
             print(f"{i}: {getattr(node, 'name', 'N/A')}")
except Exception as e:
    print(f"client.graph.node.get_by_graph_id failed: {e}")

# Try client.graph.node.list if it exists (it wasn't in dir but check just in case)
if hasattr(client.graph, 'node') and hasattr(client.graph.node, 'list'):
    try:
        print("Trying client.graph.node.list...")
        nodes = client.graph.node.list(graph_id=graph_id)
        print(f"Nodes found (list): {len(nodes)}")
    except Exception as e:
        print(f"client.graph.node.list failed: {e}")

# Check edge retrieval as well
try:
    print("Checking edges...")
    edges = client.graph.edge.get_by_graph_id(graph_id=graph_id)
    print(f"Edges found: {len(edges) if hasattr(edges, '__len__') else 'N/A'}")
except Exception as e:
    print(f"Edge retrieval failed: {e}")
