---
title: Vedic Astrology AI
emoji: 🔯
colorFrom: orange
colorTo: blue
sdk: gradio
sdk_version: "4.36.0"
app_file: app.py
pinned: false
license: mit
---

# Vedic Astrology AI

Production-quality Vedic astrology reading system combining **deterministic Swiss Ephemeris computation** with **multi-agent LLM synthesis** (Claude Sonnet / Haiku).

## Architecture

```
User Query
    │
    ▼
PipelineRunner
    ├── Stage 1:  GEOCODE      resolve birth place → lat/lon/timezone
    ├── Stage 2:  CHART        NatalChart (D1) — permanent Redis cache
    ├── Stage 3:  DASHA        Vimshottari DashaWindow — permanent cache
    ├── Stage 3:  TRANSIT      TransitOverlay — 24h Redis cache
    ├── Stage 3:  VARGAS       D9/D10/… DivisionalCharts — permanent cache
    ├── Stage 4:  YOGAS        Yoga/Dosha detection — permanent cache
    ├── Stage 5:  FEATURES     AstroFeatures flat vector (no cache, derived)
    ├── Stage 6:  SCORE        WeightedScorer breakdown (no cache, derived)
    ├── Stage 7:  RAG          Classical rules + VedAstro cases (parallel, 7d cache)
    ├── Stage 8:  SOLVE        5 specialist agents in parallel (prompt-cached)
    │               ├── NatalAgent     → natal foundation narrative
    │               ├── DashaAgent     → timing prediction
    │               ├── TransitAgent   → gochara activation
    │               ├── DivisionalAgent→ varga refinement
    │               └── YogaAgent      → yoga/dosha synthesis
    ├── Stage 9:  SYNTHESISE   SynthesisAgent — 1 LLM call (prompt-cached)
    ├── Stage 10: CRITIQUE     CriticAgent — only if score < 0.65
    ├── Stage 11: REVISE       ReviserAgent — only if critic fails
    └── Stage 12: FORMAT       StructuredReading with quotes + reasoning chain
```

### LLM call budget

| Condition | LLM calls |
|-----------|-----------|
| Cache hit (same query) | **0** |
| High-confidence path (score ≥ 0.65) | **5** (specialists + synthesis) |
| Low-confidence + critic pass | **6** (+critic) |
| Low-confidence + critic fail | **7** (+critic +reviser) |

All LLM responses are Redis-cached for 7 days keyed by sha256(prompt).

---

## Installation

### Prerequisites

- Python 3.11+
- [Swiss Ephemeris data files](https://www.astro.com/swisseph/) in `/usr/share/ephe`
- Redis (optional, degrades gracefully without it)
- MongoDB (optional, uses in-memory session store without it)

### Quick start

```bash
# 1. Clone
git clone https://github.com/your-org/vedic-astro-ai
cd vedic-astro-ai

# 2. Install (using uv — recommended)
pip install uv
uv sync --extra dev

# or with pip
pip install -r requirements.txt
pip install -e .

# 3. Configure
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY

# 4. Start services (optional but recommended)
docker compose up -d     # starts MongoDB + Redis

# 5. Run the UI
make serve-ui            # opens Gradio at http://localhost:7860

# or the API
make serve-api           # FastAPI at http://localhost:8000
```

### Swiss Ephemeris setup

```bash
# Download ephemeris files (required for chart computation)
mkdir -p /usr/share/ephe
cd /usr/share/ephe
# Download from https://www.astro.com/swisseph/ephe/
wget https://www.astro.com/ftp/swisseph/ephe/sepl_18.se1
wget https://www.astro.com/ftp/swisseph/ephe/semo_18.se1
wget https://www.astro.com/ftp/swisseph/ephe/seas_18.se1
```

---

## Configuration

All settings are in `.env` (copy from `.env.example`):

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional but recommended
OPENCAGE_API_KEY=...          # geocoding API (falls back to 25 built-in cities)
MONGODB_URI=mongodb://...     # session persistence (falls back to in-memory)
REDIS_URL=redis://...         # caching (falls back to no-cache)

# Astrology settings
SWISSEPH_PATH=/usr/share/ephe
DEFAULT_AYANAMSHA=lahiri      # lahiri | krishnamurti | raman | yukteshwar
RETROGRADE_DIGNITY_RULE=none  # none | kalidasa | mantreshwar

# Thresholds
CRITIC_PASS_THRESHOLD=0.75    # below → trigger reviser
MAX_REVISION_PASSES=1
```

---

## Offline pipelines (run once)

```bash
# 1. Place classical texts in data/raw/texts/ (*.txt or *.pdf)
#    Suggested: BPHS, Saravali, Phaladeepika

# 2. Extract structured rules
make ingest-rules              # → data/processed/rules.json

# 3. Place VedAstro dataset exports in data/raw/vedastro/ (*.json)
make ingest-cases              # → data/raw/vedastro/cases.json

# 4. Build FAISS indexes
make build-index               # → data/embeddings/rules.index
                               # → data/embeddings/cases.index
```

---

## Output format

Every reading returns a `StructuredReading` with:

```
### Strong Positive Reading

[Final narrative text answering the user's query]

---
**Weighted Analysis**

**Natal Foundation [35%]** — [first sentence of natal narrative]

**Vimshottari Dasha Timing [30%]** — [first sentence of dasha narrative]

**Gochara Transit Activation [25%]** — [first sentence of transit narrative]

**Divisional Chart Refinement [10%]** — [first sentence of divisional narrative]

Composite score for *career*: **0.72** (strong positive)

---
**Classical References**

> Quote: "Jupiter in the 9th house gives fortune and wisdom"
> Source: *BPHS Chapter 12*
> *(Applies because: confirms natal chart promise)*

> Quote: "Saturn in 3rd from Moon in transit is favourable"
> Source: *Phaladeepika*
> *(Applies because: applies to current transits)*
```

---

## API reference

### `POST /reading`

```json
{
  "birth": {
    "year": 1990, "month": 6, "day": 15,
    "hour": 14,   "minute": 30,
    "place": "Mumbai, India",
    "timezone_str": "Asia/Kolkata"
  },
  "query": "What are my career prospects this year?",
  "query_date": "2024-06-21"
}
```

Response: `StructuredReading` serialised as JSON.

### `GET /health`

Returns `{"status": "ok"}`.

### `GET /chart/{chart_id}`

Retrieve a saved natal chart by its fingerprint ID.

---

## Deployment on HuggingFace Spaces

### Option A: Direct push

```bash
# 1. Create a new Space (Gradio SDK) at huggingface.co/spaces
# 2. Push the repo
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/vedic-astro-ai
git push hf main
```

### Option B: Docker Space

```bash
# 1. Create a Docker Space at huggingface.co/spaces
# 2. The repo's Dockerfile handles the build
git push hf main
```

### Required Secrets (HF Spaces → Settings → Repository secrets)

| Secret | Required | Description |
|--------|----------|-------------|
| `ANTHROPIC_API_KEY` | **Yes** | Claude API key |
| `OPENCAGE_API_KEY`  | No | Geocoding (25 cities built-in as fallback) |
| `MONGODB_URI`       | No | Session persistence (in-memory fallback) |
| `REDIS_URL`         | No | Response caching (no-cache fallback) |

### Notes

- Swiss Ephemeris data must be available. The Dockerfile downloads it automatically.
- Without Redis, every request makes up to 7 LLM calls. With Redis (e.g. Redis Cloud free tier), repeated queries are served from cache at zero cost.
- The free HF Spaces tier has 16 GB RAM — sufficient for the FAISS index and sentence-transformer model.

---

## Testing

```bash
# Fast tests (no ephemeris required)
make test-fast

# All tests
make test

# Specific engine
make test-engines

# With coverage
make test-cov
```

Test suites cover all 6 engines (natal, dasha, transit, varga, panchang, yoga/dosha) with 200+ assertions.

---

## Project structure

```
vedic-astro-ai/
├── src/vedic_astro/
│   ├── engines/            # Deterministic computation (no LLM)
│   │   ├── natal_engine.py
│   │   ├── dasha_engine.py
│   │   ├── transit_engine.py
│   │   ├── varga_engine.py
│   │   ├── panchang_engine.py
│   │   └── yoga_dosha_engine.py
│   ├── agents/             # LLM reasoning layer
│   │   ├── pipeline.py         # Pipeline state machine
│   │   ├── solver_agent.py     # High-level solver interface
│   │   ├── output_formatter.py # Structured output + citations
│   │   ├── natal_agent.py
│   │   ├── dasha_agent.py
│   │   ├── transit_agent.py
│   │   ├── divisional_agent.py
│   │   ├── synthesis_agent.py
│   │   ├── critic_agent.py
│   │   └── reviser_agent.py
│   ├── rag/                # Retrieval-Augmented Generation
│   │   ├── loaders.py
│   │   ├── chunker.py
│   │   ├── vector_store.py
│   │   ├── embedder.py
│   │   ├── rule_extractor.py
│   │   ├── rule_retriever.py
│   │   ├── case_ingester.py
│   │   └── case_retriever.py
│   ├── learning/           # Feature extraction + scoring
│   │   ├── feature_builder.py
│   │   └── scorer.py
│   ├── storage/            # Persistence
│   │   ├── mongo_client.py
│   │   ├── chart_repo.py
│   │   ├── report_repo.py
│   │   └── session_store.py
│   ├── tools/              # Shared utilities
│   │   ├── cache.py
│   │   ├── hasher.py
│   │   ├── geo.py
│   │   ├── llm_client.py
│   │   └── datetime_utils.py
│   ├── api.py              # FastAPI endpoints
│   └── settings.py         # Pydantic Settings
├── ui/
│   ├── gradio_app.py       # Full Gradio UI
│   └── app.py              # Legacy entry
├── tests/
│   └── engines/            # 200+ unit tests
├── scripts/
│   ├── extract_rules.py    # Classical text → structured rules
│   ├── ingest_vedastro.py  # VedAstro dataset ingestion
│   └── build_index.py      # FAISS index builder
├── data/
│   ├── raw/
│   │   ├── texts/          # Classical astrology texts (*.txt, *.pdf)
│   │   └── vedastro/       # VedAstro dataset exports
│   ├── processed/
│   │   └── rules.json      # Extracted structured rules
│   └── embeddings/         # FAISS indexes
├── app.py                  # HF Spaces entry point
├── requirements.txt
├── pyproject.toml
├── Makefile
├── Dockerfile
└── docker-compose.yml
```

---

## Classical texts supported

| Text | Language | Domain |
|------|----------|--------|
| Brihat Parashara Hora Shastra (BPHS) | Sanskrit/Translation | All |
| Saravali | Sanskrit/Translation | Natal |
| Phaladeepika | Sanskrit/Translation | Natal, Dasha |
| Jataka Parijata | Sanskrit/Translation | Natal |
| Uttara Kalamrita | Sanskrit/Translation | Dasha |

Place `.txt` or `.pdf` files in `data/raw/texts/` and run `make ingest-rules`.

---

## License

MIT
