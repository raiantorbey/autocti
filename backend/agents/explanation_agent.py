"""
Agent 4 — Explanation Agent (LLM).

Uses a locally-hosted Ollama model (llama3 by default) to generate:
  * a natural-language incident summary,
  * the reasoning trail,
  * recommended analyst actions.

Retrieval-Augmented Generation: before prompting the LLM, we pull the top-k
most-similar historical incidents from ChromaDB.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.logging import logger
from backend.db.chroma_client import vector_store
from backend.ml.embeddings import embed, incident_text
from backend.models.models import Incident


SYSTEM_PROMPT = """You are a senior SOC analyst assistant. You receive a structured
incident description and related historical incidents. Produce a JSON object with
EXACTLY these keys:

  summary: short paragraph explaining what happened, in plain English.
  reasoning: bullet-list string explaining why this is/isn't suspicious.
  recommended_actions: array of 3-6 concrete next steps for the analyst.

Return ONLY the JSON — no markdown fences, no commentary.
"""


class ExplanationAgent:
    name = "explanation"

    def __init__(
        self,
        ollama_host: str = settings.ollama_host,
        model: str = settings.ollama_model,
    ) -> None:
        self.host = ollama_host.rstrip("/")
        self.model = model

    async def _retrieve_similar(self, incident: Incident, k: int = 3) -> List[Dict]:
        try:
            text = incident_text(
                {
                    "title": incident.title,
                    "events": [
                        {
                            "event_type": e.event_type,
                            "src_ip": e.src_ip,
                            "dst_ip": e.dst_ip,
                            "severity": e.severity,
                            "description": e.description,
                        }
                        for e in incident.events
                    ],
                }
            )
            q = embed(text)
            return vector_store.query(q, n_results=k)
        except Exception as e:
            logger.warning(f"Similar-incident retrieval failed: {e}")
            return []

    async def _call_ollama(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": SYSTEM_PROMPT,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as c:
                r = await c.post(f"{self.host}/api/generate", json=payload)
                r.raise_for_status()
                return r.json().get("response", "")
        except Exception as e:
            logger.warning(f"Ollama call failed: {e} — falling back to template")
            return self._fallback(prompt)

    def _fallback(self, prompt: str) -> str:
        return json.dumps(
            {
                "summary": (
                    "Cluster of related security events sharing common network "
                    "endpoints. Review enrichment data and attack-chain ordering."
                ),
                "reasoning": (
                    "- Multiple events correlated by shared IPs within time window.\n"
                    "- Enrichment flags from threat-intel sources contributed to the score.\n"
                    "- Cluster size and distinct-IP count drove the correlation component."
                ),
                "recommended_actions": [
                    "Triage highest-severity event in the chain first.",
                    "Block malicious source IPs at perimeter if confirmed.",
                    "Isolate affected hosts and take forensic snapshots.",
                    "Check EDR timeline for process/command execution on destinations.",
                    "Hunt for similar patterns across the last 30 days.",
                ],
            }
        )

    def _build_prompt(
        self, incident: Incident, chain: Dict[str, Any], similar: List[Dict]
    ) -> str:
        events_section = "\n".join(
            f"- [{e.timestamp}] {e.event_type} src={e.src_ip} dst={e.dst_ip} "
            f"sev={e.severity} | {e.description}"
            for e in incident.events
        )
        similar_section = (
            "\n".join(
                f"- ({s.get('metadata', {}).get('verdict', 'unknown')}) "
                f"{s.get('document', '')[:220]}"
                for s in similar
            )
            or "- (no similar prior incidents)"
        )
        tactics = ", ".join(chain.get("tactics", [])) or "(none mapped)"

        return f"""INCIDENT ID: {incident.id}
TITLE: {incident.title}
RISK SCORE: {incident.risk_score:.3f}
MITRE TACTICS: {tactics}

EVENTS IN THIS INCIDENT (ordered by time):
{events_section}

SIMILAR PAST INCIDENTS (retrieved via vector search):
{similar_section}

Produce the JSON object as specified in the system prompt.
"""

    async def handle(
        self, incident: Incident, chain: Dict[str, Any], session: AsyncSession
    ) -> Dict[str, Any]:
        similar = await self._retrieve_similar(incident)
        prompt = self._build_prompt(incident, chain, similar)
        raw = await self._call_ollama(prompt)
        used_llm = "Ollama call failed" not in (raw or "") and raw != self._fallback(prompt)

        parsed: Dict[str, Any]
        try:
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            parsed = json.loads(cleaned)
        except Exception:
            logger.warning("Could not parse LLM output — using raw text.")
            parsed = {
                "summary": raw[:800] if raw else "(no summary)",
                "reasoning": "",
                "recommended_actions": [],
            }

        incident.explanation = parsed.get("summary", "") + "\n\n" + parsed.get(
            "reasoning", ""
        )
        incident.recommended_actions = parsed.get("recommended_actions", [])
        await session.flush()

        try:
            text = incident_text(
                {
                    "title": incident.title,
                    "events": [
                        {
                            "event_type": e.event_type,
                            "src_ip": e.src_ip,
                            "dst_ip": e.dst_ip,
                            "severity": e.severity,
                            "description": e.description,
                        }
                        for e in incident.events
                    ],
                }
            )
            if text:
                vector_store.add(
                    ids=[str(incident.id)],
                    embeddings=[embed(text)],
                    documents=[text],
                    metadatas=[
                        {
                            "incident_id": str(incident.id),
                            "risk_score": float(incident.risk_score),
                            "tactics": ",".join(incident.tactics or []),
                        }
                    ],
                )
        except Exception as e:
            logger.warning(f"Vector-store add failed: {e}")

        # Emit realtime event to dashboard
        try:
            from backend.api.realtime import emit

            await emit(
                "explain",
                incident_id=str(incident.id),
                used_llm=used_llm,
            )
        except Exception:
            pass

        return parsed


explanation_agent = ExplanationAgent()