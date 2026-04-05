---
title: Vedic Astrology AI
emoji: 🔯
colorFrom: yellow
colorTo: blue
sdk: docker
app_file: app.py
pinned: false
license: mit
---

# 🔯 Vedic Astrology AI

Classical Parashari readings powered by **deterministic Swiss Ephemeris computation**, **hardcoded BPHS rules**, and **multi-agent LLM synthesis**.

**Live demo:** https://huggingface.co/spaces/Radha006/vedic-astro-ai

---

## System Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Gradio UI (app.py)                       │
│  Birth form → domain detection → ReadingRequest                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PipelineRunner (pipeline.py)                  │
│                                                                  │
│  Stage 1 · GEOCODE    resolve place → lat/lon/timezone           │
│  Stage 2 · CHART      NatalChart D1 via Swiss Ephemeris          │
│  Stage 3 · DASHA      Vimshottari DashaWindow                    │
│  Stage 3 · TRANSIT    Gochara TransitOverlay (dual-anchor)       │
│  Stage 3 · VARGAS     D9/D10/D7 divisional charts                │
│  Stage 4 · YOGAS      Yoga/Dosha detection engine                │
│  Stage 5 · FEATURES   AstroFeatures flat vector                  │
│  Stage 6 · SCORE      WeightedScorer breakdown by domain         │
│  Stage 7 · BPHS RAG   Hardcoded rule injection per agent         │
│  Stage 8 · SOLVE      5 specialist agents (parallel LLM calls)   │
│               ├── NatalAgent      → natal narrative              │
│               ├── DashaAgent      → timing narrative             │
│               ├── TransitAgent    → gochara narrative            │
│               ├── DivisionalAgent → varga refinement             │
│               └── YogaAgent       → yoga/dosha narrative         │
│  Stage 9 · SYNTHESISE  SynthesisAgent — final reading            │
│  Stage 10· CRITIQUE    CriticAgent (only if score < 0.75)        │
│  Stage 11· REVISE      ReviserAgent (only if critic fails)       │
│  Stage 12· FORMAT      StructuredReading with reasoning chain    │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Component | Choice | Reason |
|-----------|--------|--------|
| Ephemeris | Swiss Ephemeris (pyswisseph) | Industry-standard, sub-arcsecond accuracy |
| Ayanamsha | Lahiri (Chitrapaksha) | Most widely used in Parashari tradition |
| House system | Whole-sign | Standard for Parashari Jyotish |
| Dasha | Vimshottari | Universal Parashari timing system |
| BPHS rules | Hardcoded Python dicts | Zero latency, no vector DB needed, always available |
| LLM routing | Pluggable backend | Anthropic / Ollama / HF Inference — swap via env var |
| Caching | Redis (optional) | Natal charts cached permanently; LLM responses 7 days |

---

## BPHS Rule Library

The system hardcodes classical rules from **Brihat Parashara Hora Shastra** in `src/vedic_astro/rules/bphs_rules.py`:

- **Planet-in-house results** — all 9 planets × 12 houses (108 aphorisms)
- **Planet-in-sign results** — all 9 planets × 12 signs (108 aphorisms)
- **Dignity rules** — exaltation, debilitation, own sign, Moolatrikona, Neecha Bhanga
- **House significations** — all 12 bhavas with karakas
- **20+ Yoga definitions** — Raj Yoga, Pancha Mahapurusha, Dhana Yoga, Viparita, etc.
- **Dasha/Antardasha phala** — Mahadasha lord results + key antardasha combinations
- **Domain rules** — marriage, career, wealth, health, children, travel, spirituality
- **Transit (Gochara) rules** — Sade Sati, Gurubala, Ashtama Mangala
- **Navamsha rules** — Vargottama, Pushkara, D9 confirmation
- **Ashtakavarga rules** — bindu thresholds and transit quality
- **Chara Karaka rules** — Atmakaraka through Darakaraka
- **Special Lagna rules** — Arudha, Upapada, Hora, Ghati Lagnas

At query time, `rule_selector.py` picks the 5–8 most relevant rules for **each of the 5 specialist agents** based on the actual planetary positions, active dasha lords, and query domain.

---

## Local Setup

### Prerequisites

- **Python 3.11+**
- **Swiss Ephemeris files** (`sepl_18.se1`, `semo_18.se1`, `seas_18.se1`)
- One of: Anthropic API key, Ollama, or HuggingFace token

### 1. Clone & install

```bash
git clone https://github.com/aakritigupta0408/vedic-astro-ai.git
cd vedic-astro-ai

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

### 2. Swiss Ephemeris files

The `ephe/` folder is bundled in the repo (2 MB). If missing, download:

```bash
mkdir -p ephe
# Download from GitHub mirror:
BASE="https://raw.githubusercontent.com/aloistr/swisseph/master/ephe"
curl -L "$BASE/sepl_18.se1" -o ephe/sepl_18.se1
curl -L "$BASE/semo_18.se1" -o ephe/semo_18.se1
curl -L "$BASE/seas_18.se1" -o ephe/seas_18.se1
```

### 3. Configure `.env`

Copy the example and edit:

```bash
cp .env.example .env
```

```env
# ── LLM Backend (choose one) ──────────────────────────
LLM_BACKEND=ollama          # free, local
# LLM_BACKEND=anthropic     # paid, best quality
# LLM_BACKEND=hf_inference  # free, cloud

# ── Anthropic (if LLM_BACKEND=anthropic) ─────────────
ANTHROPIC_API_KEY=sk-ant-...

# ── Ollama (if LLM_BACKEND=ollama) ───────────────────
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2:7b        # or llama3.2, mistral, etc.

# ── HuggingFace Inference (if LLM_BACKEND=hf_inference)
HF_TOKEN=hf_...
HF_INFERENCE_MODEL=Qwen/Qwen2.5-7B-Instruct

# ── Ephemeris ─────────────────────────────────────────
SWISSEPH_PATH=ephe
DEFAULT_AYANAMSHA=lahiri
```

### 4. Run the UI

```bash
PYTHONPATH=src .venv/bin/python ui/gradio_app.py
# Open http://localhost:7860
```

---

## LLM Model Options

### Option A — Ollama (free, local, recommended for development)

Install Ollama from https://ollama.com, then pull a model:

```bash
# Fast, good quality (4 GB RAM)
ollama pull qwen2:7b

# Best local quality (8 GB RAM)
ollama pull llama3.1:8b

# Fastest, smallest (2 GB RAM)
ollama pull llama3.2:3b

# Multilingual, strong reasoning
ollama pull mistral
```

Set in `.env`:
```env
LLM_BACKEND=ollama
OLLAMA_MODEL=qwen2:7b
```

### Option B — Anthropic Claude (best quality, paid)

Get an API key from https://console.anthropic.com.

```env
LLM_BACKEND=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

The system uses `claude-sonnet-4-6` for synthesis and specialist agents.

### Option C — HuggingFace Inference API (free, cloud)

Get a free token from https://huggingface.co/settings/tokens.

```env
LLM_BACKEND=hf_inference
HF_TOKEN=hf_...
HF_INFERENCE_MODEL=Qwen/Qwen2.5-7B-Instruct
```

Free-tier models that work well:
- `Qwen/Qwen2.5-7B-Instruct` (default)
- `meta-llama/Meta-Llama-3.1-8B-Instruct`
- `mistralai/Mistral-7B-Instruct-v0.2`

---

## Optional Services

Both are optional — the system degrades gracefully without them.

### Redis (response caching)

```bash
# macOS
brew install redis && brew services start redis

# Docker
docker run -d -p 6379:6379 redis:alpine
```

```env
REDIS_URL=redis://localhost:6379/0
```

### MongoDB (session persistence)

```bash
# Docker
docker run -d -p 27017:27017 mongo:7
```

```env
MONGODB_URI=mongodb://localhost:27017
```

---

## Project Structure

```
vedic-astro-ai/
├── app.py                          # HuggingFace Spaces entry point
├── ephe/                           # Bundled Swiss Ephemeris files
│   ├── sepl_18.se1
│   ├── semo_18.se1
│   └── seas_18.se1
├── src/vedic_astro/
│   ├── engines/
│   │   ├── natal_engine.py         # Swiss Ephemeris → NatalChart
│   │   ├── dasha_engine.py         # Vimshottari dasha computation
│   │   ├── transit_engine.py       # Gochara overlay
│   │   ├── varga_engine.py         # Divisional charts (D9, D10…)
│   │   ├── yoga_dosha_engine.py    # Yoga/dosha detection
│   │   └── panchang_engine.py      # Tithi, nakshatra, vara
│   ├── agents/
│   │   ├── pipeline.py             # Main pipeline orchestrator
│   │   ├── natal_agent.py          # Natal chart specialist
│   │   ├── dasha_agent.py          # Dasha timing specialist
│   │   ├── transit_agent.py        # Gochara specialist
│   │   ├── divisional_agent.py     # Varga specialist
│   │   ├── synthesis_agent.py      # Final synthesis
│   │   ├── critic_agent.py         # Quality reviewer
│   │   └── reviser_agent.py        # Auto-reviser
│   ├── rules/
│   │   ├── bphs_rules.py           # Hardcoded BPHS aphorisms
│   │   └── rule_selector.py        # Context-aware rule picker
│   ├── learning/
│   │   ├── feature_builder.py      # AstroFeatures flat vector
│   │   └── scorer.py               # WeightedScorer by domain
│   ├── tools/
│   │   ├── llm_client.py           # Multi-backend LLM client
│   │   ├── cache.py                # Redis cache wrapper
│   │   └── geo.py                  # Place → lat/lon/timezone
│   └── settings.py                 # Pydantic settings from .env
└── ui/
    └── gradio_app.py               # Gradio 5 web interface
```

---

## HuggingFace Spaces Deployment

The space at `Radha006/vedic-astro-ai` uses the Docker SDK with:
- Python 3.11-slim base image
- Bundled ephemeris files (no download at runtime)
- `HF_TOKEN` secret for free Inference API access
- `Qwen/Qwen2.5-7B-Instruct` as the default model

To redeploy after local changes:

```bash
hf upload Radha006/vedic-astro-ai . --type space --commit-message "Update"
```

---

## Architecture Decisions — Deep Dive

### Why hardcode BPHS rules instead of RAG?

A vector database requires:
1. Text corpus ingestion
2. Embedding model running at query time
3. Index files (100s of MB) stored somewhere
4. Cold-start latency

Hardcoded rules have zero infrastructure cost, zero latency, and are deterministically correct. The `rule_selector.py` acts as a "smart lookup" — given the actual planetary positions in a chart, it pulls exactly the rules that apply (e.g., "Sun in 10th house" or "Jupiter-Saturn antardasha").

### Why multi-agent instead of one big prompt?

Each specialist agent gets a focused, smaller context window:
- NatalAgent sees only natal chart data + natal BPHS rules
- DashaAgent sees only dasha window data + dasha timing rules
- TransitAgent sees only transit overlay + gochara rules

This fits comfortably in small models (7B parameters) that have limited context windows. Five parallel 600-token calls finish faster than one 3000-token call. The SynthesisAgent then combines all five narratives into the final reading.

### Scoring system

The `WeightedScorer` computes a 0–1 score across six layers:

| Layer | Weight | What it measures |
|-------|--------|-----------------|
| Yoga support | 30% | Active benefic yogas for the domain |
| Dasha activation | 25% | Dasha lord's alignment with query domain |
| Transit trigger | 20% | Favorable transits for the domain |
| Dignity base | 15% | Planetary strength of domain karakas |
| Dosha penalty | −10% | Active doshas harming the domain |
| Bhava strength | 10% | Strength of the key house for domain |

Score < 0.65 → CriticAgent reviews → ReviserAgent improves if needed.

---

## License

MIT
