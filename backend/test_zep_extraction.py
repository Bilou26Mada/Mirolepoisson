from zep_cloud.client import Zep
from zep_cloud import EpisodeData, EntityEdgeSourceTarget
import uuid
import time
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("ZEP_API_KEY")

def test_extraction():
    client = Zep(api_key=api_key)
    graph_id = f"test_miro_{uuid.uuid4().hex[:8]}"
    print(f"Creating test graph: {graph_id}")
    
    # 1. Create Graph
    client.graph.create(graph_id=graph_id, name="Test extraction")
    
    # 2. Set simplified ontology
    from pydantic import Field
    from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel
    
    class Person(EntityModel):
        """A person entity"""
        role: EntityText = Field(description="Their role", default=None)

    class Company(EntityModel):
        """A company entity"""
        sector: EntityText = Field(description="Business sector", default=None)

    class WORKS_FOR(EdgeModel):
        """Works for relationship"""
        pass

    client.graph.set_ontology(
        graph_ids=[graph_id],
        entities={"Person": Person, "Company": Company},
        edges={"WORKS_FOR": (WORKS_FOR, [EntityEdgeSourceTarget(source="Person", target="Company")])}
    )
    
    # 3. Add rich text
    text = """
    Jean Dupont est le PDG de la société TechVision. 
    Marie Curie travaille comme chercheuse chez BioLabs.
    TechVision et BioLabs collaborent sur un projet d'intelligence artificielle.
    Elon Musk a fondé SpaceX et Tesla.
    """
    
    print("Adding text episodes...")
    episodes = [EpisodeData(data=text, type="text")]
    batch_result = client.graph.add_batch(graph_id=graph_id, episodes=episodes)
    ep_uuid = batch_result[0].uuid_
    
    # 4. Wait for processing
    print(f"Waiting for processing of episode {ep_uuid}...")
    for _ in range(30):
        ep = client.graph.episode.get(uuid_=ep_uuid)
        if ep.processed:
            print("Processing complete!")
            break
        time.sleep(2)
    else:
        print("Timed out waiting for processing.")
        return

    # 5. Check nodes
    nodes = client.graph.node.get_by_graph_id(graph_id=graph_id)
    print(f"Nodes found: {len(nodes)}")
    for n in nodes:
        print(f"- {n.name} ({n.labels})")

if __name__ == "__main__":
    test_extraction()
