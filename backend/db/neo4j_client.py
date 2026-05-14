"""Neo4j async driver wrapper for the correlation agent."""
from typing import Any, Dict, List, Optional

from neo4j import AsyncGraphDatabase, AsyncDriver

from backend.core.config import settings
from backend.core.logging import logger


class Neo4jClient:
    """Thin async wrapper over the neo4j driver."""

    def __init__(self) -> None:
        self._driver: Optional[AsyncDriver] = None

    async def connect(self) -> None:
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
            logger.info("Neo4j driver initialised")

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def run(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query and return records as dicts."""
        await self.connect()
        assert self._driver is not None
        async with self._driver.session() as session:
            result = await session.run(query, params or {})
            return [record.data() async for record in result]

    # ---------- graph helpers ----------
    async def upsert_event(self, event: Dict[str, Any]) -> None:
        """Create/merge an event and link its src/dst IPs."""
        cypher = """
        MERGE (e:Event {id: $id})
          SET e.severity = $severity,
              e.type = $type,
              e.timestamp = $timestamp,
              e.description = $description
        WITH e
        MERGE (src:IP {address: $src_ip})
        MERGE (dst:IP {address: $dst_ip})
        MERGE (src)-[:SOURCE_OF]->(e)
        MERGE (e)-[:TARGETS]->(dst)
        """
        await self.run(cypher, event)

    async def link_events_by_ip(self, ip: str) -> List[Dict[str, Any]]:
        """Find events that share an IP — attack-chain candidate."""
        cypher = """
        MATCH (ip:IP {address: $ip})-[:SOURCE_OF|TARGETS]-(e:Event)
        RETURN e.id AS id, e.type AS type, e.severity AS severity,
               e.timestamp AS timestamp
        ORDER BY e.timestamp
        """
        return await self.run(cypher, {"ip": ip})

    async def get_subgraph(self, incident_id: str) -> Dict[str, Any]:
        """Return nodes + edges for visualisation."""
        cypher = """
        MATCH (i:Incident {id: $id})-[:CONTAINS]->(e:Event)
        OPTIONAL MATCH (e)-[r]-(n)
        RETURN collect(distinct e) as events,
               collect(distinct n) as related,
               collect(distinct r) as relationships
        """
        rows = await self.run(cypher, {"id": incident_id})
        return rows[0] if rows else {"events": [], "related": [], "relationships": []}


neo4j_client = Neo4jClient()
