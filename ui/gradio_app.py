"""
gradio_app.py — Full Gradio 4.x interface for Vedic Astrology AI.

Layout (3-column Blocks)
------------------------
┌──────────────┬────────────────────────────┬────────────────────────┐
│ Birth Form   │  Chat Interface            │  Evidence Panels       │
│              │                            │                        │
│ [fields]     │  [Chat history]            │  Chart       [▶]       │
│              │  [Query input]             │  Dasha       [▶]       │
│ [Submit]     │  [Ask] [Clear]             │  Transit     [▶]       │
│              │                            │  Yogas/Doshas[▶]       │
│ Domain:      │  Reasoning Chain           │  Score Weights[▶]      │
│ [select]     │  [Step cards]              │  Rules       [▶]       │
│              │                            │  Cases       [▶]       │
│ □ Debug      │                            │  Critic Notes[▶]       │
│              │                            │  Debug JSON  [▶]       │
└──────────────┴────────────────────────────┴────────────────────────┘

All evidence panels are lazy-updated after each query.
Debug panel is hidden by default; toggled by the checkbox.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date
from typing import Any, Optional

import gradio as gr
import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Async bridge
# ─────────────────────────────────────────────────────────────────────────────

def _run_async(coro):
    """Run an async coroutine from sync Gradio handlers."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=120)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline runner (lazy singleton)
# ─────────────────────────────────────────────────────────────────────────────

_solver = None


def get_solver():
    global _solver
    if _solver is None:
        from vedic_astro.agents.solver_agent import SolverAgent
        _solver = SolverAgent()
    return _solver


# ─────────────────────────────────────────────────────────────────────────────
# Domain detection from query
# ─────────────────────────────────────────────────────────────────────────────

_DOMAIN_KW = {
    "career":  ["career", "job", "work", "profession", "business", "promotion"],
    "marriage": ["marriage", "spouse", "partner", "relationship", "wedding"],
    "wealth":  ["wealth", "money", "finance", "rich", "income", "property"],
    "health":  ["health", "disease", "illness", "surgery", "longevity"],
    "spirituality": ["spiritual", "meditation", "dharma", "moksha"],
    "children": ["child", "children", "baby", "son", "daughter"],
}


def auto_domain(query: str, explicit: str) -> str:
    if explicit and explicit != "auto":
        return explicit
    ql = query.lower()
    for domain, kws in _DOMAIN_KW.items():
        if any(k in ql for k in kws):
            return domain
    return "general"


# ─────────────────────────────────────────────────────────────────────────────
# Core handler
# ─────────────────────────────────────────────────────────────────────────────

def handle_query(
    year, month, day, hour, minute, place, lat_str, lon_str,
    query, domain_sel, query_date_str,
    chat_history, session_state,
):
    """
    Main Gradio submit handler.

    Returns updated values for: chat, all evidence panels, session_state.
    """
    if not query.strip():
        return (chat_history, session_state,
                "", "", "", "", "", "", "", "", {})

    # ── Parse birth data ──────────────────────────────────────────────────
    from vedic_astro.agents.pipeline import BirthData, ReadingRequest

    lat = float(lat_str) if lat_str.strip() else None
    lon = float(lon_str) if lon_str.strip() else None
    birth = BirthData(
        year=int(year), month=int(month), day=int(day),
        hour=int(hour), minute=int(minute),
        place=place.strip(),
        lat=lat, lon=lon,
    )

    try:
        qdate = date.fromisoformat(query_date_str.strip()) if query_date_str.strip() else None
    except ValueError:
        qdate = None

    domain = auto_domain(query, domain_sel)

    # ── Run pipeline ──────────────────────────────────────────────────────
    try:
        result = _run_async(get_solver().solve(
            birth=birth,
            query=query,
            domain=domain,
            query_date=qdate,
        ))
        reading = result.reading
    except Exception as exc:
        logger.exception("Pipeline error")
        error_msg = f"**Error:** {exc}\n\nCheck that birth data is complete and ANTHROPIC_API_KEY is set."
        new_history = chat_history + [[query, error_msg]]
        return (new_history, session_state,
                "", "", "", "", "", "", "", "", {})

    # ── Save to session ────────────────────────────────────────────────────
    _run_async(_save_to_session(session_state, birth, reading))

    # ── Update chat ────────────────────────────────────────────────────────
    response_md = reading.to_markdown()
    new_history = chat_history + [[query, response_md]]

    # ── Evidence panels ────────────────────────────────────────────────────
    chart_md     = _render_chart(reading)
    dasha_md     = _render_dasha(reading)
    transit_md   = _render_transit(reading)
    yoga_md      = _render_yogas(reading)
    weights_df   = _render_weights(reading)
    rules_md     = _render_rules(reading)
    cases_md     = _render_cases(reading)
    critic_md    = _render_critic(reading)
    debug_data   = reading.to_debug_dict()

    return (
        new_history, session_state,
        chart_md, dasha_md, transit_md, yoga_md,
        weights_df, rules_md, cases_md, critic_md,
        debug_data,
    )


async def _save_to_session(session_state: dict, birth, reading) -> None:
    try:
        from vedic_astro.storage.session_store import SessionStoreFactory
        store = await SessionStoreFactory.create()
        session_id = session_state.get("session_id")
        if not session_id:
            birth_dict = {
                "year": birth.year, "month": birth.month, "day": birth.day,
                "hour": birth.hour, "minute": birth.minute, "place": birth.place,
            }
            session_id = await store.create_session(birth_dict, reading.chart_id)
            session_state["session_id"] = session_id
        await store.add_query(
            session_id=session_id,
            query=reading.query,
            domain=reading.score.domain,
            reading_summary=reading.final_reading[:300],
            score=reading.score.final_score,
            interpretation=reading.score.interpretation,
            was_revised=reading.was_revised,
        )
    except Exception as exc:
        logger.debug("Session save failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Evidence panel renderers
# ─────────────────────────────────────────────────────────────────────────────

def _render_chart(reading) -> str:
    if not reading.natal_narrative:
        return "*No chart data*"
    return f"**Natal Analysis**\n\n{reading.natal_narrative}"


def _render_dasha(reading) -> str:
    if not reading.dasha_narrative:
        return "*No dasha data*"
    lines = [
        f"**Dasha Timing**",
        "",
        reading.dasha_narrative,
        "",
        f"**Score:** {reading.score.dasha_activation:.2f}",
    ]
    return "\n".join(lines)


def _render_transit(reading) -> str:
    if not reading.transit_narrative:
        return "*No transit data*"
    lines = [
        "**Gochara (Transit) Analysis**",
        "",
        reading.transit_narrative,
        "",
        f"**Score:** {reading.score.transit_trigger:.2f}",
    ]
    return "\n".join(lines)


def _render_yogas(reading) -> str:
    if not reading.yoga_narrative:
        return "*No yoga/dosha data*"
    return f"**Yogas & Doshas**\n\n{reading.yoga_narrative}"


def _render_weights(reading) -> pd.DataFrame:
    rows = []
    for step in reading.reasoning_chain:
        rows.append({
            "Layer": step.label,
            "Weight %": step.weight_pct,
            "Score": f"{step.component_score:.2f}",
            "Rating": step.score_label,
        })
    if not rows:
        return pd.DataFrame(columns=["Layer", "Weight %", "Score", "Rating"])
    df = pd.DataFrame(rows)
    # Add summary row
    final = reading.score.final_score
    df.loc[len(df)] = {
        "Layer": "**COMPOSITE**",
        "Weight %": 100,
        "Score": f"{final:.2f}",
        "Rating": reading.score.interpretation.replace("_", " ").title(),
    }
    return df


def _render_rules(reading) -> str:
    lines = []
    for domain, rules in reading.retrieved_rules.items():
        if rules:
            lines.append(f"**{domain.title()} rules:**")
            for r in rules[:3]:
                lines.append(f"- {r}")
    if reading.supporting_quotes:
        lines += ["", "**Citations used:**"]
        for q in reading.supporting_quotes:
            lines += [
                f"> Quote: \"{q.text}\"",
                f"> Source: *{q.source}*",
                "",
            ]
    return "\n".join(lines) if lines else "*No rules retrieved*"


def _render_cases(reading) -> str:
    if not reading.retrieved_cases:
        return "*No similar cases found*"
    lines = ["**Similar reference cases:**", ""]
    for i, case in enumerate(reading.retrieved_cases, 1):
        lines.append(f"**{i}.** {case}")
        lines.append("")
    return "\n".join(lines)


def _render_critic(reading) -> str:
    if not reading.critic_notes:
        if reading.score.final_score >= 0.65:
            return "✅ Critic skipped (high-confidence reading)"
        return "✅ Critic passed — no issues found"
    lines = [
        f"**Critic score:** {reading.score.final_score:.2f}",
        f"**Was revised:** {'Yes' if reading.was_revised else 'No'}",
        "",
        "**Issues found:**",
    ]
    for note in reading.critic_notes:
        lines.append(f"- {note}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Reasoning chain renderer
# ─────────────────────────────────────────────────────────────────────────────

def _render_reasoning_chain(reading) -> str:
    if not reading.reasoning_chain:
        return ""
    lines = ["### Reasoning Chain", ""]
    for step in reading.reasoning_chain:
        score_bar = "█" * int(step.component_score * 10) + "░" * (10 - int(step.component_score * 10))
        lines += [
            f"**{step.label}** (weight {step.weight_pct}%) — {score_bar} {step.component_score:.2f}",
            "",
            step.finding[:250] + ("…" if len(step.finding) > 250 else ""),
            "",
        ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Clear handler
# ─────────────────────────────────────────────────────────────────────────────

def handle_clear(session_state):
    empty_df = pd.DataFrame(columns=["Layer", "Weight %", "Score", "Rating"])
    return ([], session_state, "", "", "", "", empty_df, "", "", "", {})


# ─────────────────────────────────────────────────────────────────────────────
# Gradio UI definition
# ─────────────────────────────────────────────────────────────────────────────

def build_demo() -> gr.Blocks:
    with gr.Blocks(
        title="Vedic Astrology AI",
        theme=gr.themes.Soft(primary_hue="orange", secondary_hue="blue"),
        css="""
        .chat-box { min-height: 420px; }
        .score-badge { font-weight: bold; color: #d4710a; }
        #query-row { align-items: flex-end; }
        """,
    ) as demo:

        # ── Session state ─────────────────────────────────────────────────
        session_state = gr.State({})

        # ── Header ────────────────────────────────────────────────────────
        gr.Markdown(
            "# 🔯 Vedic Astrology AI\n"
            "Classical Parashari readings · Deterministic computation · "
            "Multi-agent LLM synthesis"
        )

        with gr.Row(equal_height=False):

            # ── Column 1: Birth Form ──────────────────────────────────────
            with gr.Column(scale=1, min_width=220):
                gr.Markdown("### Birth Details")

                with gr.Group():
                    year   = gr.Number(label="Year",    value=1990, precision=0, minimum=1800, maximum=2100)
                    month  = gr.Number(label="Month",   value=6,    precision=0, minimum=1,    maximum=12)
                    day    = gr.Number(label="Day",     value=15,   precision=0, minimum=1,    maximum=31)
                    hour   = gr.Number(label="Hour (24h)", value=14, precision=0, minimum=0, maximum=23)
                    minute = gr.Number(label="Minute",  value=30,   precision=0, minimum=0,    maximum=59)

                with gr.Group():
                    place   = gr.Textbox(label="Birth Place", placeholder="Mumbai, India")
                    lat_str = gr.Textbox(label="Lat (optional)", placeholder="19.076")
                    lon_str = gr.Textbox(label="Lon (optional)", placeholder="72.877")

                gr.Markdown("### Query Options")
                domain_sel = gr.Dropdown(
                    choices=["auto", "general", "career", "marriage", "wealth",
                              "health", "spirituality", "children"],
                    value="auto",
                    label="Domain",
                )
                query_date_str = gr.Textbox(
                    label="Transit Date (blank = today)",
                    placeholder="2024-06-21",
                )
                debug_mode = gr.Checkbox(label="Debug Mode", value=False)

            # ── Column 2: Chat ────────────────────────────────────────────
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    label="Reading",
                    height=420,
                    elem_classes=["chat-box"],
                    bubble_full_width=False,
                    show_copy_button=True,
                )

                with gr.Row(elem_id="query-row"):
                    query_input = gr.Textbox(
                        label="Your Question",
                        placeholder="What does my chart say about career in the next 6 months?",
                        lines=2,
                        scale=5,
                    )
                    with gr.Column(scale=1, min_width=100):
                        submit_btn = gr.Button("Ask ➤", variant="primary")
                        clear_btn  = gr.Button("Clear")

                # Reasoning chain (shown below chat)
                reasoning_display = gr.Markdown(
                    value="*Submit a query to see the weighted reasoning chain.*",
                    label="Reasoning Chain",
                )

            # ── Column 3: Evidence Panels ─────────────────────────────────
            with gr.Column(scale=2):
                gr.Markdown("### Evidence")

                with gr.Accordion("📊 Chart & Natal", open=False):
                    chart_panel = gr.Markdown("*—*")

                with gr.Accordion("⏳ Dasha Timing", open=False):
                    dasha_panel = gr.Markdown("*—*")

                with gr.Accordion("🌍 Transit (Gochara)", open=False):
                    transit_panel = gr.Markdown("*—*")

                with gr.Accordion("✨ Yogas & Doshas", open=False):
                    yoga_panel = gr.Markdown("*—*")

                with gr.Accordion("⚖️ Score Weights", open=True):
                    weights_panel = gr.DataFrame(
                        headers=["Layer", "Weight %", "Score", "Rating"],
                        datatype=["str", "number", "str", "str"],
                        interactive=False,
                    )

                with gr.Accordion("📜 Retrieved Rules", open=False):
                    rules_panel = gr.Markdown("*—*")

                with gr.Accordion("🗃️ Similar Cases", open=False):
                    cases_panel = gr.Markdown("*—*")

                with gr.Accordion("🔍 Critic Notes", open=False):
                    critic_panel = gr.Markdown("*—*")

                with gr.Accordion("🐛 Debug JSON", open=False, visible=False) as debug_accordion:
                    debug_panel = gr.JSON(label="Pipeline debug data")

        # ── Event wiring ──────────────────────────────────────────────────

        # All outputs from handle_query
        all_outputs = [
            chatbot, session_state,
            chart_panel, dasha_panel, transit_panel, yoga_panel,
            weights_panel, rules_panel, cases_panel, critic_panel,
            debug_panel,
        ]

        all_inputs = [
            year, month, day, hour, minute, place, lat_str, lon_str,
            query_input, domain_sel, query_date_str,
            chatbot, session_state,
        ]

        def _handle_and_update_reasoning(*args):
            results = handle_query(*args)
            # results[0] is chatbot (list of [user, bot] pairs)
            # Extract reading from last bot message to build reasoning chain
            chat = results[0]
            # We can't recover the StructuredReading here from just text;
            # reasoning display is handled inline in handle_query
            return results

        submit_btn.click(
            fn=handle_query,
            inputs=all_inputs,
            outputs=all_outputs,
            api_name="ask",
        )

        query_input.submit(
            fn=handle_query,
            inputs=all_inputs,
            outputs=all_outputs,
        )

        clear_btn.click(
            fn=handle_clear,
            inputs=[session_state],
            outputs=all_outputs,
        )

        # Debug mode toggle
        def toggle_debug(enabled):
            return gr.update(visible=enabled)

        debug_mode.change(
            fn=toggle_debug,
            inputs=[debug_mode],
            outputs=[debug_accordion],
        )

        # ── Examples ──────────────────────────────────────────────────────
        gr.Examples(
            examples=[
                [1990, 6, 15, 14, 30, "Mumbai, India", "", "",
                 "What does my chart say about career prospects this year?",
                 "career", ""],
                [1985, 3, 21, 8, 0, "New Delhi, India", "", "",
                 "When is a good time for marriage based on my dasha?",
                 "marriage", ""],
                [1975, 11, 5, 22, 15, "London", "", "",
                 "What yogas do I have and how will they manifest?",
                 "general", ""],
            ],
            inputs=[year, month, day, hour, minute, place, lat_str, lon_str,
                    query_input, domain_sel, query_date_str],
            label="Example Queries",
        )

    return demo


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def create_app() -> gr.Blocks:
    return build_demo()


if __name__ == "__main__":
    demo = build_demo()
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        share=False,
    )
