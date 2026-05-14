# AutoCTI — What was built automatically vs. what YOU must do

This file is the single source of truth for finishing the deployment.

---

## ✅ WHAT THE AI BUILT (already done — no action required)

| Area | Files |
|------|-------|
| Backend service | `backend/main.py`, FastAPI app with lifespan, CORS, routers |
| Config / logging | `backend/core/config.py`, `backend/core/logging.py` |
| Auth | JWT + bcrypt + RBAC in `backend/core/security.py`, `backend/api/auth.py` |
| Postgres / SQLAlchemy | async engine, ORM models (`User`, `Event`, `Incident`, `Feedback`, `RiskWeights`) |
| Neo4j client | `backend/db/neo4j_client.py` with attack-graph helpers |
| ChromaDB + FAISS fallback | `backend/db/chroma_client.py` with HTTP client, FAISS failover |
| Redis pub/sub | `backend/db/redis_client.py` with 5 agent channels |
| 5 AI agents | `backend/agents/*` — ingestion, correlation, risk, explanation, feedback |
| External API wrappers | VirusTotal, AbuseIPDB, Shodan, GeoIP, WHOIS — **with mock mode** if no key |
| Detection ML | RF + XGBoost ensemble, preprocessing + training (`backend/ml/detection.py`) |
| Optional autoencoder | PyTorch AE for unsupervised anomaly (`backend/ml/autoencoder.py`) |
| Risk scoring | `Risk = αS + βE + γC` with online gradient feedback (`backend/ml/risk_model.py`) |
| Embeddings / RAG | sentence-transformers → ChromaDB (`backend/ml/embeddings.py`) |
| LLM explain agent | Ollama client with RAG retrieval + JSON-structured output |
| Tests | `backend/tests/test_risk.py`, `test_agents.py`, `test_api.py` |
| Scripts | `train_detection.py`, `create_admin.py`, `demo_pipeline.py` |
| React frontend | Vite + Tailwind + react-router + ReactFlow (graph) + recharts |
| Pages | Login, Incidents list (auto-refresh 15 s), Incident detail, Graph, Timeline, Feedback buttons |
| DevOps | `backend/Dockerfile`, `frontend/Dockerfile` (multi-stage + nginx), `docker-compose.yml`, `.env.example` |
| Security | JWT, bcrypt, role-based access control (admin/analyst/viewer), HTTPS-ready via nginx reverse proxy |

The service starts and runs end-to-end in mock mode **without any manual steps** — mock enrichment gives it realistic data to work on, and the LLM agent falls back to a templated explanation if Ollama isn't available.

---

## ⚠️ WHAT YOU MUST DO MANUALLY

### 1. Environment & secrets (required)

```bash
cp .env.example .env
# Edit .env and, at minimum, change:
#   JWT_SECRET            → generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
#   POSTGRES_PASSWORD     → something real
#   NEO4J_PASSWORD        → something real
```

### 2. External API keys (optional — app uses mock mode if missing)

Add to `.env`:

| Key | Where to get it |
|-----|-----------------|
| `VIRUSTOTAL_API_KEY` | https://www.virustotal.com/gui/my-apikey (free tier: 4 req/min, 500/day) |
| `ABUSEIPDB_API_KEY`  | https://www.abuseipdb.com/account/api (free tier: 1,000 req/day) |
| `SHODAN_API_KEY`     | https://account.shodan.io/ (requires paid subscription for host lookups) |
| `GEOIP_API_KEY`      | https://ipinfo.io/signup (free tier: 50,000 req/month) |

WHOIS needs no key (uses `python-whois`).

Without keys, every integration returns deterministic mock data, so the pipeline still runs end-to-end.

### 3. Download training datasets (required only if you want to train the detection model)

Create these directories and drop the CSVs in:

```
data/datasets/cicids2017/        ← CICIDS2017 "MachineLearningCVE" CSVs (8 files)
data/datasets/unsw-nb15/         ← UNSW_NB15_training-set.csv + UNSW_NB15_testing-set.csv
```

Download links (official sources):

* **CICIDS2017** — https://www.unb.ca/cic/datasets/ids-2017.html (fill the request form; download the "MachineLearningCVE" subset)
* **UNSW-NB15** — https://research.unsw.edu.au/projects/unsw-nb15-dataset (download the CSV partition)

These are large datasets (CICIDS: ~2.8 GB raw, ~500 MB as CSVs). A Kaggle mirror exists if the primary site is slow.

### 4. Bring up the stack

```bash
docker compose up -d --build
docker compose logs -f backend       # watch startup
```

Wait until you see `Postgres schema ready`.

### 5. Create the admin user (required, one-time)

```bash
docker exec -it autocti-backend python -m backend.scripts.create_admin \
    --username admin --password 'YourStrongPassword!' --email you@example.com
```

### 6. Pull the Ollama model (required only if you want real LLM explanations)

```bash
docker exec -it autocti-ollama ollama pull llama3
# or a lighter model:
docker exec -it autocti-ollama ollama pull mistral
```

Then in `.env` set `OLLAMA_MODEL=llama3` or `OLLAMA_MODEL=mistral` and restart the backend:

```bash
docker compose restart backend
```

If you skip this step, the explanation agent automatically falls back to a templated explanation — so the system remains functional.

### 7. Train the detection model (required only if you want real scoring over raw events)

After the datasets are in place:

```bash
docker exec -it autocti-backend python -m backend.scripts.train_detection --dataset both
# artifacts land in /app/data/models/ (persisted via the ./data bind mount)
```

Expected runtime on a laptop CPU: 10-30 min depending on dataset size. Evaluation metrics are written to `data/models/detection_metrics.json`.

Without trained artifacts, `detection.predict_proba` uses a harmless magnitude-based fallback — the pipeline still works, it just can't distinguish attacks from benign traffic on raw flow features.

### 8. Run the demo pipeline (recommended smoke test)

```bash
docker exec -it autocti-backend python -m backend.scripts.demo_pipeline
```

This synthesises 6 events (a full kill-chain + a decoy), runs them through all 5 agents, and prints the resulting incidents with risk scores and explanations. Perfect for a screen-recording or live demo.

### 9. Run the tests

```bash
docker exec -it autocti-backend pytest -v backend/tests/
```

### 10. Open the dashboard

Navigate to **http://localhost:3000** and log in with the admin user you created in step 5.

Ingest a live event through the API (from anywhere):

```bash
curl -X POST http://localhost:8000/api/events/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "suricata",
    "event_type": "brute_force",
    "src_ip": "45.33.32.156",
    "dst_ip": "10.0.0.5",
    "severity": 0.8,
    "description": "40 failed SSH logins from single source"
  }'
```

Watch it appear in the UI within 15 s (auto-refresh).

---

## 🛠 Troubleshooting

| Symptom | Fix |
|---------|-----|
| `backend` exits with `asyncpg` / connection errors | Wait 30 s for Postgres healthcheck; re-run `docker compose up -d` |
| `Vector store init failed` in logs | Chroma container still booting — retry; FAISS fallback kicks in automatically |
| `Ollama call failed` in logs | Either pull a model (step 6) or ignore — fallback explanation is served |
| `JWT decode error` on login | `JWT_SECRET` changed after tokens were issued — log in again |
| Neo4j refuses connection | Visit http://localhost:7474 and set the password to match `NEO4J_PASSWORD` in `.env` (Neo4j forces a one-time change on fresh installs) |
| Frontend 502 Bad Gateway | Backend isn't up yet — check `docker compose logs backend` |

---

## 🔐 Going to production

1. Replace `JWT_SECRET`, all DB passwords, and the admin password.
2. Put everything behind a TLS terminator (Traefik, nginx, Caddy, or cloud LB). The nginx config in `frontend/nginx.conf` already sets the right proxy headers.
3. Move Postgres and Neo4j to managed services; keep volumes backed up.
4. Use `alembic` migrations instead of `init_db()` (the model module is already Alembic-compatible).
5. For Kubernetes: each service in `docker-compose.yml` maps 1:1 to a Deployment + Service; secrets → `Secret` objects; `data/` → `PersistentVolumeClaim`. The backend is stateless and horizontally scalable.
6. Enable rate limiting on `/api/auth/login` (e.g. via nginx `limit_req_zone`).
7. Rotate external-API keys regularly and store them in a vault (Hashicorp Vault, AWS Secrets Manager, etc.), not in `.env`.

---

## 📋 Summary — 3 commands to get running (mock mode)

```bash
cp .env.example .env                                          # 1. env
docker compose up -d --build                                  # 2. start
docker exec -it autocti-backend python -m backend.scripts.create_admin  # 3. admin
```

Then browse to http://localhost:3000 and log in with `admin / <your-admin-password`.
