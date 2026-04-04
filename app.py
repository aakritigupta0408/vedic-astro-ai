"""
app.py — HuggingFace Spaces entry point.

This file must be at the project root for HF Spaces to auto-detect it.
It imports and launches the Gradio app from ui/gradio_app.py.

HF Spaces configuration
------------------------
- SDK: gradio
- app_file: app.py
- python_version: 3.11

Environment variables required (set in HF Spaces Secrets):
    ANTHROPIC_API_KEY   — Claude API key
    OPENCAGE_API_KEY    — Optional: geocoding API key
    MONGODB_URI         — Optional: MongoDB Atlas URI for session persistence
    REDIS_URL           — Optional: Redis URL for caching
"""

import sys
import os

# Add src/ to Python path so vedic_astro imports work
_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_root, "src"))

# Point Swiss Ephemeris at bundled ephe/ folder if not already set
if not os.environ.get("SWISSEPH_PATH"):
    _ephe = os.path.join(_root, "ephe")
    if os.path.isdir(_ephe):
        os.environ["SWISSEPH_PATH"] = _ephe

from ui.gradio_app import build_demo

demo = build_demo()

if __name__ == "__main__":
    demo.launch()
