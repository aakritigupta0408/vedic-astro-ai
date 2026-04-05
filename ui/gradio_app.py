"""
gradio_app.py — Vedic Astrology AI · Gradio 5.x interface

Layout
------
┌─────────────────────────────────────────────────────────────────┐
│  Header: title + subtitle + status badge                        │
├──────────────┬──────────────────────────┬───────────────────────┤
│ Birth Form   │  Chat                    │  Analysis Panels      │
│  Year/Mo/Day │  [Chat history]          │  🪐 Natal Chart        │
│  Hour/Min    │  [Query input]           │  ⏳ Dasha Timing       │
│  Place       │  [Ask] [Clear]           │  🌍 Gochara Transits   │
│  Lat/Lon     │                          │  ✨ Yogas & Doshas     │
│  Domain      │  BPHS Rules Applied      │  📖 BPHS Rules Used   │
│  Date        │  [rules list]            │  ⚖️ Score Breakdown    │
│  [Ask]       │                          │  🔍 Critic Notes       │
└──────────────┴──────────────────────────┴───────────────────────┘
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date

import gradio as gr
import pandas as pd

logger = logging.getLogger(__name__)

CSS = """
.app-header { text-align: center; padding: 1.2rem 0 0.4rem; }
.app-header h1 { font-size: 2rem; font-weight: 700; color: #b45309; margin: 0; }
.app-header p  { color: #6b7280; margin: 0.3rem 0 0; }
.status-ok   { color: #16a34a; font-weight: 600; }
.status-err  { color: #dc2626; font-weight: 600; }
.bphs-rule   { background: #fffbeb; border-left: 3px solid #d97706;
               padding: 0.4rem 0.7rem; margin: 0.3rem 0;
               border-radius: 0 4px 4px 0; font-size: 0.85rem; }
.section-label { font-size: 0.75rem; font-weight: 600;
                 text-transform: uppercase; color: #9ca3af;
                 letter-spacing: 0.05em; margin-bottom: 0.3rem; }
.reading-box textarea { font-size: 0.95rem; line-height: 1.6; }
footer { display: none !important; }
"""

# ─────────────────────────────────────────────────────────────────────────────
# Async bridge
# ─────────────────────────────────────────────────────────────────────────────

def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result(timeout=180)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ─────────────────────────────────────────────────────────────────────────────
# Lazy solver singleton
# ─────────────────────────────────────────────────────────────────────────────

_solver = None

def get_solver():
    global _solver
    if _solver is None:
        from vedic_astro.agents.solver_agent import SolverAgent
        _solver = SolverAgent()
    return _solver


# ─────────────────────────────────────────────────────────────────────────────
# Domain auto-detection
# ─────────────────────────────────────────────────────────────────────────────

_DOMAIN_KW = {
    "career":       ["career", "job", "work", "profession", "business", "promotion", "office"],
    "marriage":     ["marriage", "spouse", "partner", "relationship", "wedding", "love", "husband", "wife"],
    "wealth":       ["wealth", "money", "finance", "rich", "income", "property", "savings"],
    "health":       ["health", "disease", "illness", "surgery", "longevity", "body", "sick"],
    "spirituality": ["spiritual", "meditation", "dharma", "moksha", "karma", "soul"],
    "children":     ["child", "children", "baby", "son", "daughter", "pregnancy"],
    "travel":       ["travel", "foreign", "abroad", "move", "relocate", "journey"],
    "family":       ["family", "mother", "father", "sibling", "home", "house"],
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
# Core query handler
# ─────────────────────────────────────────────────────────────────────────────

def handle_query(
    year, month, day, hour, minute, place, lat_str, lon_str,
    query, domain_sel, query_date_str,
    chat_history, session_state,
):
    if not str(query).strip():
        empty_df = pd.DataFrame(columns=["Layer", "Weight %", "Score", "Rating"])
        return (chat_history, session_state, "", "", "", "", "", empty_df, "", "", [])

    from vedic_astro.agents.pipeline import BirthData, ReadingRequest

    lat = float(lat_str) if str(lat_str).strip() else None
    lon = float(lon_str) if str(lon_str).strip() else None
    birth = BirthData(
        year=int(year), month=int(month), day=int(day),
        hour=int(hour), minute=int(minute),
        place=str(place).strip(), lat=lat, lon=lon,
    )

    try:
        qdate = date.fromisoformat(str(query_date_str).strip()) if str(query_date_str).strip() else None
    except ValueError:
        qdate = None

    domain = auto_domain(str(query), domain_sel)

    try:
        result = _run_async(get_solver().solve(
            birth=birth, query=str(query), domain=domain, query_date=qdate,
        ))
        reading = result.reading
    except Exception as exc:
        logger.exception("Pipeline error")
        empty_df = pd.DataFrame(columns=["Layer", "Weight %", "Score", "Rating"])
        error_md = f"**Error:** {exc}"
        new_history = chat_history + [[str(query), error_md]]
        return (new_history, session_state, "", "", "", "", "", empty_df, error_md, {}, "*—*")

    _run_async(_save_session(session_state, birth, reading))

    response_md = reading.to_markdown() if hasattr(reading, "to_markdown") else str(reading.final_reading)
    new_history = chat_history + [[str(query), response_md]]

    chart_md    = _render_chart(reading)
    dasha_md    = _render_dasha(reading)
    transit_md  = _render_transit(reading)
    yoga_md     = _render_yogas(reading)
    bphs_md     = _render_bphs_rules(reading)
    weights_df  = _render_weights(reading)
    critic_md   = _render_critic(reading)
    debug_json  = reading.to_debug_dict() if hasattr(reading, "to_debug_dict") else {}
    bphs_list   = _bphs_rule_list(reading)

    return (
        new_history, session_state,
        chart_md, dasha_md, transit_md, yoga_md,
        bphs_md, weights_df, critic_md, debug_json,
        bphs_list,
    )


async def _save_session(session_state, birth, reading):
    try:
        from vedic_astro.storage.session_store import SessionStoreFactory
        store = await SessionStoreFactory.create()
        sid = session_state.get("session_id")
        if not sid:
            birth_dict = {k: getattr(birth, k) for k in ("year","month","day","hour","minute","place")}
            sid = await store.create_session(birth_dict, reading.chart_id)
            session_state["session_id"] = sid
        await store.add_query(
            session_id=sid, query=reading.query,
            domain=reading.score.domain,
            reading_summary=reading.final_reading[:300],
            score=reading.score.final_score,
            interpretation=reading.score.interpretation,
            was_revised=reading.was_revised,
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Panel renderers
# ─────────────────────────────────────────────────────────────────────────────

def _render_chart(reading) -> str:
    if not reading.natal_narrative:
        return "*No natal data computed.*"
    score_line = ""
    if hasattr(reading, "score") and reading.score:
        score_line = f"\n\n**Composite Score:** `{reading.score.final_score:.2f}` — *{reading.score.interpretation.replace('_',' ').title()}*"
    return f"**Natal Analysis**\n\n{reading.natal_narrative}{score_line}"


def _render_dasha(reading) -> str:
    if not reading.dasha_narrative:
        return "*No dasha data.*"
    score_line = ""
    if hasattr(reading, "score") and reading.score:
        score_line = f"\n\n**Dasha Activation Score:** `{reading.score.dasha_activation:.2f}`"
    return f"**Vimshottari Dasha**\n\n{reading.dasha_narrative}{score_line}"


def _render_transit(reading) -> str:
    if not reading.transit_narrative:
        return "*No transit data.*"
    score_line = ""
    if hasattr(reading, "score") and reading.score:
        score_line = f"\n\n**Transit Trigger Score:** `{reading.score.transit_trigger:.2f}`"
    return f"**Gochara (Transit) Analysis**\n\n{reading.transit_narrative}{score_line}"


def _render_yogas(reading) -> str:
    if not reading.yoga_narrative:
        return "*No yoga/dosha data.*"
    return f"**Yogas & Doshas**\n\n{reading.yoga_narrative}"


def _render_bphs_rules(reading) -> str:
    rules = getattr(reading, "retrieved_rules", {})
    if not rules:
        return "*No classical rules retrieved.*"
    lines = ["**Classical BPHS Rules Applied**\n"]
    for agent, rule_list in rules.items():
        if rule_list:
            lines.append(f"**{agent.title()}:**")
            for r in rule_list[:4]:
                lines.append(f"> {r}")
            lines.append("")
    return "\n".join(lines) if len(lines) > 1 else "*No rules applied.*"


def _bphs_rule_list(reading) -> str:
    """Markdown string of top BPHS rules for sidebar highlights."""
    rules = getattr(reading, "retrieved_rules", {})
    flat = []
    for agent, rule_list in rules.items():
        for r in rule_list[:2]:
            flat.append(f"**{agent.title()}:** {r}")
    if not flat:
        return "*No rules applied.*"
    return "\n\n".join(f"> {r}" for r in flat[:10])


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
    df.loc[len(df)] = {
        "Layer": "COMPOSITE",
        "Weight %": 100,
        "Score": f"{reading.score.final_score:.2f}",
        "Rating": reading.score.interpretation.replace("_", " ").title(),
    }
    return df


def _render_critic(reading) -> str:
    score = reading.score.final_score if reading.score else 0
    if not reading.critic_notes:
        if score >= 0.65:
            return f"✅ **Critic passed** — high-confidence reading (score: {score:.2f})"
        return "✅ Critic passed — no issues found."
    lines = [
        f"**Critic Score:** `{score:.2f}`  |  **Revised:** {'Yes' if reading.was_revised else 'No'}",
        "",
        "**Issues flagged:**",
    ]
    for note in reading.critic_notes:
        lines.append(f"- {note}")
    return "\n".join(lines)


def handle_clear(session_state):
    empty_df = pd.DataFrame(columns=["Layer", "Weight %", "Score", "Rating"])
    return ([], session_state, "", "", "", "", "", empty_df, "", {}, "*—*")


# ─────────────────────────────────────────────────────────────────────────────
# UI definition
# ─────────────────────────────────────────────────────────────────────────────

def build_demo() -> gr.Blocks:

    with gr.Blocks(title="Vedic Astrology AI", css=CSS) as demo:

        session_state = gr.State({})

        # ── Header ────────────────────────────────────────────────────────
        gr.HTML("""
        <div class="app-header">
          <h1>🔯 Vedic Astrology AI</h1>
          <p>Classical Parashari readings · Swiss Ephemeris computation ·
             Hardcoded BPHS rules · Multi-agent LLM synthesis</p>
        </div>
        """)

        with gr.Row(equal_height=False):

            # ── Column 1: Birth Form ──────────────────────────────────────
            with gr.Column(scale=1, min_width=230):

                gr.Markdown("### 🗓 Birth Details")
                with gr.Group():
                    with gr.Row():
                        day   = gr.Number(label="Day",   value=15,   precision=0, minimum=1,  maximum=31,   scale=1)
                        month = gr.Number(label="Month", value=6,    precision=0, minimum=1,  maximum=12,   scale=1)
                        year  = gr.Number(label="Year",  value=1990, precision=0, minimum=1800, maximum=2100, scale=2)
                    with gr.Row():
                        hour   = gr.Number(label="Hour (24h)", value=14, precision=0, minimum=0, maximum=23, scale=1)
                        minute = gr.Number(label="Minute",     value=30, precision=0, minimum=0, maximum=59, scale=1)
                    place   = gr.Textbox(label="Birth Place", placeholder="Mumbai, India")
                    with gr.Row():
                        lat_str = gr.Textbox(label="Lat (opt)", placeholder="19.076", scale=1)
                        lon_str = gr.Textbox(label="Lon (opt)", placeholder="72.877", scale=1)

                gr.Markdown("### 🎯 Query Options")
                domain_sel = gr.Dropdown(
                    choices=["auto","general","career","marriage","wealth",
                             "health","spirituality","children","travel","family","social_standing"],
                    value="auto", label="Domain",
                )
                query_date_str = gr.Textbox(
                    label="Transit Date (blank = today)", placeholder="2026-06-01",
                )

                ask_btn   = gr.Button("✨ Get Reading", variant="primary", size="lg")
                clear_btn = gr.Button("🗑 Clear", size="sm")

                gr.Markdown("---")
                gr.Markdown("**About**\n\nEnter birth details, ask a question about any life area. "
                            "The system computes a full Parashari chart, runs 5 specialist agents "
                            "with hardcoded BPHS rules, and synthesises a classical reading.")

            # ── Column 2: Chat + BPHS rules sidebar ──────────────────────
            with gr.Column(scale=3):

                chatbot = gr.Chatbot(
                    label="Reading",
                    height=440,
                    type="tuples",
                    show_copy_button=True,
                    placeholder="*Enter birth details and ask a question to receive your Vedic reading.*",
                )

                with gr.Row(elem_id="query-row"):
                    query_input = gr.Textbox(
                        label="Your Question",
                        placeholder="What does my chart say about career in the next 6 months?",
                        lines=2,
                        scale=5,
                        show_label=True,
                    )
                    with gr.Column(scale=1, min_width=90):
                        submit_btn = gr.Button("Ask ➤", variant="primary")

                gr.Markdown("#### 📖 BPHS Rules Applied to This Reading")
                bphs_highlights = gr.Markdown(
                    value="*Rules will appear here after a query.*",
                    elem_id="bphs-list",
                )

            # ── Column 3: Evidence Panels ─────────────────────────────────
            with gr.Column(scale=2):

                gr.Markdown("### 📊 Analysis Panels")

                with gr.Accordion("🪐 Natal Chart", open=True):
                    chart_panel = gr.Markdown("*—*")

                with gr.Accordion("⏳ Dasha Timing", open=False):
                    dasha_panel = gr.Markdown("*—*")

                with gr.Accordion("🌍 Gochara Transits", open=False):
                    transit_panel = gr.Markdown("*—*")

                with gr.Accordion("✨ Yogas & Doshas", open=False):
                    yoga_panel = gr.Markdown("*—*")

                with gr.Accordion("📖 All BPHS Rules", open=False):
                    bphs_panel = gr.Markdown("*—*")

                with gr.Accordion("⚖️ Score Breakdown", open=False):
                    weights_panel = gr.DataFrame(
                        value=pd.DataFrame(columns=["Layer","Weight %","Score","Rating"]),
                        interactive=False,
                    )

                with gr.Accordion("🔍 Critic Notes", open=False):
                    critic_panel = gr.Markdown("*—*")

                with gr.Accordion("🐛 Debug JSON", open=False):
                    debug_panel = gr.JSON(label="Pipeline debug data")

        # ── Examples ──────────────────────────────────────────────────────
        gr.Examples(
            examples=[
                [15, 6, 1990, 14, 30, "Mumbai, India",  "", "", "What does my chart say about career prospects this year?",    "career",       ""],
                [21, 3, 1985,  8,  0, "New Delhi, India","","", "When is a good time for marriage based on my dasha?",          "marriage",     ""],
                [4,  8, 1994,  1, 50, "Delhi, India",   "", "", "What is my current dasha period and what does it mean?",       "general",      ""],
                [5, 11, 1975, 22, 15, "London",         "", "", "What yogas do I have and how strong are they?",                "general",      ""],
                [12, 1, 1988, 10, 20, "Chennai, India", "", "", "How is my health and what precautions should I take?",         "health",       ""],
                [7,  4, 1995, 18, 45, "Singapore",      "", "", "Will I settle abroad? What does my chart indicate about travel?","travel",      ""],
            ],
            inputs=[day, month, year, hour, minute, place, lat_str, lon_str,
                    query_input, domain_sel, query_date_str],
            label="📋 Example Charts & Queries",
        )

        # ── Outputs list ──────────────────────────────────────────────────
        all_outputs = [
            chatbot, session_state,
            chart_panel, dasha_panel, transit_panel, yoga_panel,
            bphs_panel, weights_panel, critic_panel, debug_panel,
            bphs_highlights,
        ]

        all_inputs = [
            year, month, day, hour, minute, place, lat_str, lon_str,
            query_input, domain_sel, query_date_str,
            chatbot, session_state,
        ]

        # Wire events
        ask_btn.click(fn=handle_query, inputs=all_inputs, outputs=all_outputs)
        submit_btn.click(fn=handle_query, inputs=all_inputs, outputs=all_outputs, api_name="ask")
        query_input.submit(fn=handle_query, inputs=all_inputs, outputs=all_outputs)
        clear_btn.click(fn=handle_clear, inputs=[session_state], outputs=all_outputs)

    return demo


def create_app() -> gr.Blocks:
    return build_demo()


if __name__ == "__main__":
    demo = build_demo()
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        share=False,
    )
