"""Graph visualization endpoint — returns Neo4j nodes/edges for an incident."""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from backend.core.security import ROLE_READONLY, require_roles
from backend.db.neo4j_client import neo4j_client
from backend.schemas.schemas import GraphEdge, GraphNode, GraphResponse

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get(
    "/incident/{incident_id}",
    response_model=GraphResponse,
    dependencies=[Depends(require_roles(*ROLE_READONLY))],
)
async def incident_graph(incident_id: uuid.UUID):
    try:
        rows = await neo4j_client.run(
            """
            MATCH (i:Incident {id: $id})-[r1:CONTAINS]->(e:Event)
            OPTIONAL MATCH (src:IP)-[r2:SOURCE_OF]->(e)
            OPTIONAL MATCH (e)-[r3:TARGETS]->(dst:IP)
            RETURN i, e, src, dst
            """,
            {"id": str(incident_id)},
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Graph DB unavailable: {e}")

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    def add_node(n, label: str, ntype: str) -> None:
        if n is None:
            return
        nid = str(n.get("id") or n.get("address") or id(n))
        if nid not in nodes:
            nodes[nid] = GraphNode(
                id=nid, label=label, type=ntype, properties=dict(n)
            )

    for row in rows:
        i = row.get("i")
        e = row.get("e")
        src = row.get("src")
        dst = row.get("dst")

        if i:
            add_node(i, i.get("title", "Incident"), "Incident")
        if e:
            add_node(e, e.get("type", "Event"), "Event")
            if i:
                edges.append(
                    GraphEdge(
                        source=str(i.get("id")),
                        target=str(e.get("id")),
                        type="CONTAINS",
                    )
                )
        if src:
            add_node(src, src.get("address", "IP"), "IP")
            if e:
                edges.append(
                    GraphEdge(
                        source=str(src.get("address")),
                        target=str(e.get("id")),
                        type="SOURCE_OF",
                    )
                )
        if dst:
            add_node(dst, dst.get("address", "IP"), "IP")
            if e:
                edges.append(
                    GraphEdge(
                        source=str(e.get("id")),
                        target=str(dst.get("address")),
                        type="TARGETS",
                    )
                )

    return GraphResponse(nodes=list(nodes.values()), edges=edges)
