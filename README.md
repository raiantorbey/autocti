# AutoCTI – Autonomous Cyber Threat Intelligence System

**Agentic AI SOC Framework** — a production-ready multi-agent system for autonomous
cyber threat intelligence, detection, correlation, scoring, and analyst-facing
natural-language explanation.

---

## 1. High-level architecture

```
                ┌─────────────────────────────────────────────────┐
                │                   React SOC UI                   │
                └───────────────────────┬─────────────────────────┘
                                        │ REST / WebSocket
                ┌───────────────────────▼─────────────────────────┐
                │                 FastAPI Gateway                  │
                │      (JWT auth · RBAC · async orchestration)     │
                └──┬───────────┬──────────┬───────────┬───────────┘
                   │           │          │           │
        ┌──────────▼──┐  ┌─────▼─────┐ ┌──▼──────┐ ┌─▼─────────────┐
        │ Ingestion & │  │Correlation│ │  Risk   │ │ LLM Explain   │
        │ Enrichment  │→ │& Hypothes.│→│ Scoring │→│ (Ollama)      │
        │   Agent     │  │  Agent    │ │  Agent  │ │  Agent        │
        └──────┬──────┘  └─────┬─────┘ └────┬────┘ └──────┬────────┘
               │               │            │             │
               │               ▼            │             │
               │        ┌───────────┐       │             │
               │        │   Neo4j   │       │             │
               │        │ (graph)   │       │             │
               │        └───────────┘       │             │
               │                            │             │
        ┌──────▼────────────────────────────▼─────────────▼──────┐
        │  PostgreSQL · ChromaDB (vectors) · Redis (broker/queue)│
        └────────────────────────┬───────────────────────────────┘
                                 │
                       ┌─────────▼──────────┐
                       │  Feedback & Learn. │
                       │       Agent        │
                       └────────────────────┘
```

Five autonomous agents cooperate via Redis pub/sub and a shared event store.

| # | Agent | Responsibility |
|---|-------|----------------|
| 1 | **Ingestion & Enrichment** | Pulls raw events, enriches with VirusTotal / AbuseIPDB / Shodan / GeoIP / WHOIS |
| 2 | **Correlation & Hypothesis** | Builds Neo4j attack graphs, clusters related events, reconstructs kill-chains |
| 3 | **Prioritization & Risk Scoring** | Computes `Risk = αS + βE + γC`, adjusts by analyst feedback |
| 4 | **Explanation (LLM)** | Generates analyst-ready incident summaries via Ollama |
| 5 | **Feedback & Learning** | Persists analyst verdicts, retunes weights / retrains models |

---

## 2. Quick start

```bash
# 1. Clone & enter
git clone <this-repo> autocti && cd autocti

# 2. Copy env template and fill in keys (see bottom of README)
cp .env.example .env

# 3. Bring up the full stack
docker compose up -d --build

# 4. Pull an Ollama model (one-time, ~4 GB)
docker exec -it autocti-ollama ollama pull llama3

# 5. (Optional) Train detection model on CICIDS2017
docker exec -it autocti-backend python -m scripts.train_detection

# 6. Open the SOC UI
open http://localhost:3000
```

Default credentials: **admin / admin123** (change immediately — see `/backend/scripts/create_admin.py`).

---

## 3. Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI (async), Python 3.11 |
| Frontend | React 18 + Vite + Tailwind |
| Graph DB | Neo4j 5 |
| Relational DB | PostgreSQL 15 |
| Vector DB | ChromaDB (primary) + FAISS fallback |
| LLM | Ollama (llama3 / mistral) |
| Broker | Redis 7 |
| Auth | JWT + bcrypt + RBAC |
| Container | Docker + docker-compose |

---

## 4. ML pipeline

* **Detection** — RandomForest + XGBoost ensemble on CICIDS2017 + UNSW-NB15, plus
  an optional PyTorch autoencoder for unsupervised anomaly detection.
* **Correlation** — Neo4j Cypher + networkx clustering.
* **Risk** — linear weighted model `Risk = αS + βE + γC` with online feedback
  gradient updates.
* **Explanation** — RAG over ChromaDB → Ollama prompt.

---

## 5. What YOU still have to do (manual steps)

See the end of this file — section **"Manual steps"**.

---

## 6. Project tree

```
autocti/
├── backend/
│   ├── agents/                  # The 5 AI agents
│   │   ├── ingestion_agent.py
│   │   ├── correlation_agent.py
│   │   ├── risk_agent.py
│   │   ├── explanation_agent.py
│   │   └── feedback_agent.py
│   ├── api/                     # FastAPI routers
│   │   ├── auth.py
│   │   ├── incidents.py
│   │   ├── feedback.py
│   │   ├── graph.py
│   │   └── admin.py
│   ├── core/                    # config, security, logging
│   │   ├── config.py
│   │   ├── security.py
│   │   └── logging.py
│   ├── db/                      # DB clients
│   │   ├── postgres.py
│   │   ├── neo4j_client.py
│   │   ├── redis_client.py
│   │   └── chroma_client.py
│   ├── integrations/            # External API wrappers
│   │   ├── virustotal.py
│   │   ├── abuseipdb.py
│   │   ├── shodan_api.py
│   │   ├── geoip.py
│   │   └── whois_api.py
│   ├── ml/                      # ML models & pipelines
│   │   ├── detection.py
│   │   ├── autoencoder.py
│   │   ├── risk_model.py
│   │   └── embeddings.py
│   ├── models/                  # SQLAlchemy ORM models
│   │   └── models.py
│   ├── schemas/                 # Pydantic schemas
│   │   └── schemas.py
│   ├── scripts/                 # Training / seeding
│   │   ├── train_detection.py
│   │   ├── create_admin.py
│   │   └── demo_pipeline.py
│   ├── tests/                   # pytest suite
│   │   ├── test_risk.py
│   │   ├── test_agents.py
│   │   └── test_api.py
│   ├── main.py                  # FastAPI entrypoint
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   └── App.jsx
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```
