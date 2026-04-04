"""
ui/app.py — Gradio interface for the Vedic Astrology AI system.

Launch with:
    uv run python ui/app.py
or via:
    make serve-ui

The UI sends requests to the FastAPI backend (localhost:8000) so the API
server must be running.  Alternatively it can call the orchestrator directly.
"""

from __future__ import annotations

import asyncio
from datetime import date

import gradio as gr


def _run_reading(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    place: str,
    query: str,
    query_date_str: str,
) -> tuple[str, str, str, str, str, float]:
    """
    Synchronous wrapper around the async orchestrator for Gradio.

    Returns
    -------
    (reading, natal_narrative, dasha_narrative, transit_narrative, div_narrative, critic_score)
    """
    from vedic_astro.agents.orchestrator import (
        AstrologyOrchestrator, BirthData, ReadingRequest
    )

    birth = BirthData(
        year=int(year), month=int(month), day=int(day),
        hour=int(hour), minute=int(minute),
        place=place.strip(),
    )

    try:
        qdate = date.fromisoformat(query_date_str) if query_date_str else None
    except ValueError:
        qdate = None

    orch = AstrologyOrchestrator()
    result = asyncio.run(orch.run(ReadingRequest(birth=birth, query=query, query_date=qdate)))

    return (
        result.reading,
        result.natal_narrative,
        result.dasha_narrative,
        result.transit_narrative,
        result.divisional_narrative,
        round(result.critic_score, 3),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Build UI
# ─────────────────────────────────────────────────────────────────────────────

with gr.Blocks(title="Vedic Astrology AI", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# Vedic Astrology AI\nClassical Parashari readings with deterministic computation.")

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### Birth Details")
            year   = gr.Number(label="Year",   value=1990, precision=0)
            month  = gr.Number(label="Month",  value=6,    precision=0, minimum=1, maximum=12)
            day    = gr.Number(label="Day",    value=15,   precision=0, minimum=1, maximum=31)
            hour   = gr.Number(label="Hour (24h)", value=14, precision=0, minimum=0, maximum=23)
            minute = gr.Number(label="Minute", value=30,   precision=0, minimum=0, maximum=59)
            place  = gr.Textbox(label="Birth Place", placeholder="Mumbai, India")

            gr.Markdown("### Query")
            query = gr.Textbox(
                label="Your Question",
                placeholder="What does my chart say about career prospects in the next 6 months?",
                lines=3,
            )
            query_date = gr.Textbox(
                label="Query Date (YYYY-MM-DD, leave blank for today)",
                placeholder="2024-06-21",
            )
            submit_btn = gr.Button("Generate Reading", variant="primary")

        with gr.Column(scale=2):
            gr.Markdown("### Reading")
            final_reading = gr.Textbox(label="Synthesised Reading", lines=10, interactive=False)
            critic_score  = gr.Number(label="Quality Score (0–1)", interactive=False)

            with gr.Accordion("Agent Sub-Reports", open=False):
                natal_out    = gr.Textbox(label="Natal Agent",       lines=4, interactive=False)
                dasha_out    = gr.Textbox(label="Dasha Agent",        lines=4, interactive=False)
                transit_out  = gr.Textbox(label="Transit Agent",      lines=4, interactive=False)
                div_out      = gr.Textbox(label="Divisional Agent",   lines=4, interactive=False)

    submit_btn.click(
        fn=_run_reading,
        inputs=[year, month, day, hour, minute, place, query, query_date],
        outputs=[final_reading, natal_out, dasha_out, transit_out, div_out, critic_score],
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)
