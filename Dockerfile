# ─── Base ────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System deps: gcc for pyswisseph compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# ─── Python dependencies ─────────────────────────────────────────────────────
# Pin huggingface_hub to a version compatible with gradio 5
COPY requirements.txt .
RUN pip install --no-cache-dir \
    "huggingface_hub>=0.27.0" \
    "gradio>=5.0.0,<6.0.0" \
    && pip install --no-cache-dir -r requirements.txt

# Download sentence-transformer model at build time (avoids cold-start delay)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" \
    || echo "Warning: sentence-transformer download failed"

# ─── Application ─────────────────────────────────────────────────────────────
COPY . .
RUN pip install --no-cache-dir -e .

# Create data directories
RUN mkdir -p data/raw/texts data/raw/vedastro data/processed data/embeddings

# ─── Runtime ─────────────────────────────────────────────────────────────────
ENV PYTHONPATH=/app/src
ENV SWISSEPH_PATH=/app/ephe

# HF Spaces runs as non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 7860

# HF Spaces expects the app to listen on port 7860
CMD ["python", "app.py"]
