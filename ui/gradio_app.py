"""
gradio_app.py — Vedic Astrology AI · Gradio 5.x interface
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
/* ── Fonts & Base ─────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

body, .gradio-container { font-family: 'Inter', sans-serif !important; }

/* ── Header ───────────────────────────────────────────── */
.app-header {
    background: linear-gradient(135deg, #78350f 0%, #b45309 50%, #d97706 100%);
    border-radius: 12px;
    padding: 1.8rem 2rem 1.4rem;
    margin-bottom: 1rem;
    text-align: center;
    box-shadow: 0 4px 20px rgba(180, 83, 9, 0.25);
}
.app-header h1 {
    font-size: 2.2rem;
    font-weight: 700;
    color: #fff;
    margin: 0 0 0.4rem;
    letter-spacing: -0.02em;
}
.app-header .subtitle {
    color: rgba(255,255,255,0.85);
    font-size: 0.95rem;
    margin: 0;
}
.app-header .badges {
    display: flex;
    justify-content: center;
    gap: 0.6rem;
    margin-top: 0.8rem;
    flex-wrap: wrap;
}
.badge {
    background: rgba(255,255,255,0.2);
    color: #fff;
    padding: 0.2rem 0.7rem;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    backdrop-filter: blur(4px);
}

/* ── Form Card ─────────────────────────────────────────── */
.form-card {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 1.2rem;
    box-shadow: 0 1px 6px rgba(0,0,0,0.06);
}
.form-section-title {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #9ca3af;
    margin: 1rem 0 0.4rem;
}

/* ── Chat Panel ────────────────────────────────────────── */
.chat-wrap {
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid #e5e7eb;
    box-shadow: 0 1px 6px rgba(0,0,0,0.06);
}

/* ── Query Box ─────────────────────────────────────────── */
.query-area textarea {
    border-radius: 10px !important;
    border: 2px solid #e5e7eb !important;
    font-size: 0.95rem !important;
    transition: border-color 0.2s;
}
.query-area textarea:focus {
    border-color: #d97706 !important;
    box-shadow: 0 0 0 3px rgba(217,119,6,0.1) !important;
}

/* ── Buttons ───────────────────────────────────────────── */
.btn-ask {
    background: linear-gradient(135deg, #b45309, #d97706) !important;
    border: none !important;
    border-radius: 10px !important;
    color: #fff !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    padding: 0.75rem 1.5rem !important;
    transition: opacity 0.2s, transform 0.1s !important;
    box-shadow: 0 2px 8px rgba(180,83,9,0.3) !important;
}
.btn-ask:hover { opacity: 0.9 !important; transform: translateY(-1px) !important; }
.btn-clear {
    border-radius: 8px !important;
    font-size: 0.85rem !important;
}

/* ── Analysis Tabs ─────────────────────────────────────── */
.tab-nav button {
    font-size: 0.82rem !important;
    padding: 0.4rem 0.7rem !important;
}

/* ── BPHS rule callout ─────────────────────────────────── */
.bphs-callout {
    background: linear-gradient(135deg, #fffbeb, #fef3c7);
    border: 1px solid #fcd34d;
    border-left: 4px solid #d97706;
    border-radius: 0 8px 8px 0;
    padding: 0.6rem 0.9rem;
    margin: 0.35rem 0;
    font-size: 0.84rem;
    line-height: 1.5;
}

/* ── Score table ───────────────────────────────────────── */
.score-table table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
.score-table th { background: #f9fafb; color: #374151; font-weight: 600; text-align: left; padding: 0.5rem 0.75rem; border-bottom: 2px solid #e5e7eb; }
.score-table td { padding: 0.45rem 0.75rem; border-bottom: 1px solid #f3f4f6; }

/* ── Step guide ────────────────────────────────────────── */
.step-guide {
    background: #f9fafb;
    border-radius: 10px;
    padding: 1rem;
    font-size: 0.85rem;
    color: #374151;
    line-height: 1.7;
}
.step-num {
    display: inline-block;
    background: #d97706;
    color: #fff;
    border-radius: 50%;
    width: 1.3rem;
    height: 1.3rem;
    text-align: center;
    font-size: 0.72rem;
    font-weight: 700;
    line-height: 1.3rem;
    margin-right: 0.4rem;
}

/* ── Loading indicator ─────────────────────────────────── */
.status-pending { color: #d97706; font-weight: 600; font-size: 0.88rem; }
.status-ok      { color: #16a34a; font-weight: 600; font-size: 0.88rem; }
.status-err     { color: #dc2626; font-weight: 600; font-size: 0.88rem; }

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

_EMPTY_DF = pd.DataFrame(columns=["Layer", "Weight %", "Score", "Rating"])

def handle_query(
    year, month, day, hour, minute, place, lat_str, lon_str,
    query, domain_sel, query_date_str,
    chat_history, session_state,
):
    if not str(query).strip():
        return (chat_history, session_state, "", "", "", "", "", _EMPTY_DF.copy(), "", {}, "*Ask a question to see rules.*", "")

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
        error_md = f"**Error:** {exc}"
        new_history = chat_history + [[str(query), error_md]]
        return (new_history, session_state, "", "", "", "", "", _EMPTY_DF.copy(), error_md, {}, "*—*", f"❌ Error: {exc}")

    _run_async(_save_session(session_state, birth, reading))

    response_md = reading.to_markdown() if hasattr(reading, "to_markdown") else str(reading.final_reading)
    new_history = chat_history + [[str(query), response_md]]

    chart_md   = _render_chart(reading)
    dasha_md   = _render_dasha(reading)
    transit_md = _render_transit(reading)
    yoga_md    = _render_yogas(reading)
    bphs_md    = _render_bphs_rules(reading)
    weights_df = _render_weights(reading)
    critic_md  = _render_critic(reading)
    debug_json = reading.to_debug_dict() if hasattr(reading, "to_debug_dict") else {}
    bphs_list  = _bphs_rule_list(reading)
    score_val  = reading.score.final_score if reading.score else 0
    status_md  = f"✅ Reading complete · Domain: **{domain}** · Score: **{score_val:.2f}**"

    return (
        new_history, session_state,
        chart_md, dasha_md, transit_md, yoga_md,
        bphs_md, weights_df, critic_md, debug_json,
        bphs_list, status_md,
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
        score_line = f"\n\n---\n**Composite Score:** `{reading.score.final_score:.2f}` — *{reading.score.interpretation.replace('_',' ').title()}*"
    return f"{reading.natal_narrative}{score_line}"


def _render_dasha(reading) -> str:
    if not reading.dasha_narrative:
        return "*No dasha data.*"
    score_line = ""
    if hasattr(reading, "score") and reading.score:
        score_line = f"\n\n---\n**Dasha Activation Score:** `{reading.score.dasha_activation:.2f}`"
    return f"{reading.dasha_narrative}{score_line}"


def _render_transit(reading) -> str:
    if not reading.transit_narrative:
        return "*No transit data.*"
    score_line = ""
    if hasattr(reading, "score") and reading.score:
        score_line = f"\n\n---\n**Transit Trigger Score:** `{reading.score.transit_trigger:.2f}`"
    return f"{reading.transit_narrative}{score_line}"


def _render_yogas(reading) -> str:
    if not reading.yoga_narrative:
        return "*No yoga/dosha data.*"
    return reading.yoga_narrative


def _render_bphs_rules(reading) -> str:
    rules = getattr(reading, "retrieved_rules", {})
    if not rules:
        return "*No classical rules retrieved.*"
    lines = []
    for agent, rule_list in rules.items():
        if rule_list:
            lines.append(f"### {agent.title()}")
            for r in rule_list[:4]:
                lines.append(f"> {r}\n")
    return "\n".join(lines) if lines else "*No rules applied.*"


def _bphs_rule_list(reading) -> str:
    rules = getattr(reading, "retrieved_rules", {})
    flat = []
    for agent, rule_list in rules.items():
        for r in rule_list[:2]:
            flat.append(f"**{agent.title()}:** {r}")
    if not flat:
        return "*No rules applied.*"
    return "\n\n".join(f'<div class="bphs-callout">{r}</div>' for r in flat[:10])


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
        return _EMPTY_DF.copy()
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
            return f"✅ **Passed** — high-confidence reading (score: {score:.2f})"
        return "✅ Passed — no issues found."
    lines = [
        f"**Score:** `{score:.2f}`  ·  **Revised:** {'Yes ✓' if reading.was_revised else 'No'}",
        "",
        "**Issues flagged:**",
    ]
    for note in reading.critic_notes:
        lines.append(f"- {note}")
    return "\n".join(lines)


def handle_clear(session_state):
    return ([], session_state, "", "", "", "", "", _EMPTY_DF.copy(), "", {}, "*Ask a question to see rules.*", "")


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
          <p class="subtitle">Classical Parashari readings powered by Swiss Ephemeris · BPHS rules · Multi-agent AI</p>
          <div class="badges">
            <span class="badge">🪐 Swiss Ephemeris</span>
            <span class="badge">📜 BPHS Rules</span>
            <span class="badge">🤖 5-Agent Pipeline</span>
            <span class="badge">⚖️ Lahiri Ayanamsha</span>
          </div>
        </div>
        """)

        with gr.Row(equal_height=False):

            # ── Column 1: Birth Form ──────────────────────────────────────
            with gr.Column(scale=1, min_width=240):

                with gr.Group(elem_classes="form-card"):
                    gr.Markdown("### 📅 Birth Details")

                    gr.HTML('<p class="form-section-title">Date of Birth</p>')
                    with gr.Row():
                        day   = gr.Number(label="Day",   value=15,   precision=0, minimum=1,  maximum=31,   scale=1)
                        month = gr.Number(label="Month", value=6,    precision=0, minimum=1,  maximum=12,   scale=1)
                        year  = gr.Number(label="Year",  value=1990, precision=0, minimum=1800, maximum=2100, scale=2)

                    gr.HTML('<p class="form-section-title">Time of Birth</p>')
                    with gr.Row():
                        hour   = gr.Number(label="Hour (0–23)", value=14, precision=0, minimum=0, maximum=23, scale=1)
                        minute = gr.Number(label="Minute",      value=30, precision=0, minimum=0, maximum=59, scale=1)

                    gr.HTML('<p class="form-section-title">Place of Birth</p>')
                    place = gr.Textbox(label="City, Country", placeholder="Mumbai, India", lines=1)
                    with gr.Row():
                        lat_str = gr.Textbox(label="Latitude (optional)",  placeholder="19.076", scale=1)
                        lon_str = gr.Textbox(label="Longitude (optional)", placeholder="72.877", scale=1)

                    gr.HTML('<p class="form-section-title">Query Settings</p>')
                    domain_sel = gr.Dropdown(
                        choices=["auto","general","career","marriage","wealth",
                                 "health","spirituality","children","travel","family","social_standing"],
                        value="auto",
                        label="Life Domain (auto-detects from question)",
                        info="Leave as 'auto' for automatic detection",
                    )
                    query_date_str = gr.Textbox(
                        label="Transit Reference Date",
                        placeholder="Leave blank for today",
                        info="Format: YYYY-MM-DD",
                    )

                clear_btn = gr.Button("🗑 Clear Conversation", size="sm", elem_classes="btn-clear")

                gr.HTML("""
                <div class="step-guide" style="margin-top:1rem">
                  <strong>How to use:</strong><br>
                  <span class="step-num">1</span> Enter birth date, time &amp; place<br>
                  <span class="step-num">2</span> Type your question below<br>
                  <span class="step-num">3</span> Click <strong>Get Reading</strong><br>
                  <span class="step-num">4</span> Explore analysis tabs →
                </div>
                """)

            # ── Column 2: Chat ────────────────────────────────────────────
            with gr.Column(scale=3):

                status_bar = gr.Markdown("", elem_id="status-bar")

                chatbot = gr.Chatbot(
                    label="",
                    height=460,
                    type="tuples",
                    show_copy_button=True,
                    placeholder=(
                        "### Welcome to Vedic Astrology AI\n\n"
                        "Fill in your birth details on the left and ask any question about your life — "
                        "career, relationships, health, wealth, timing of events, or spiritual path.\n\n"
                        "*Try an example below to get started.*"
                    ),
                    elem_classes="chat-wrap",
                )

                with gr.Row():
                    query_input = gr.Textbox(
                        label="",
                        placeholder="Ask about career, marriage, health, wealth, travel, spirituality…",
                        lines=2,
                        scale=5,
                        show_label=False,
                        elem_classes="query-area",
                    )
                    ask_btn = gr.Button("✨ Get\nReading", variant="primary", scale=1, min_width=90, elem_classes="btn-ask")

                gr.Markdown("#### 📜 Classical Rules Applied")
                bphs_highlights = gr.HTML(
                    value='<p style="color:#9ca3af;font-size:0.85rem;font-style:italic">BPHS rules injected into each agent will appear here after a reading.</p>',
                    elem_id="bphs-list",
                )

            # ── Column 3: Analysis Panels ─────────────────────────────────
            with gr.Column(scale=2):

                gr.Markdown("### 📊 Analysis")

                with gr.Tabs(elem_classes="tab-nav"):

                    with gr.TabItem("🪐 Natal"):
                        chart_panel = gr.Markdown("*Run a reading to see natal analysis.*")

                    with gr.TabItem("⏳ Dasha"):
                        dasha_panel = gr.Markdown("*Run a reading to see dasha timing.*")

                    with gr.TabItem("🌍 Transit"):
                        transit_panel = gr.Markdown("*Run a reading to see transit overlay.*")

                    with gr.TabItem("✨ Yogas"):
                        yoga_panel = gr.Markdown("*Run a reading to see yoga/dosha analysis.*")

                    with gr.TabItem("📖 BPHS"):
                        bphs_panel = gr.Markdown("*Classical rules per agent will appear here.*")

                    with gr.TabItem("⚖️ Score"):
                        weights_panel = gr.DataFrame(
                            value=_EMPTY_DF.copy(),
                            interactive=False,
                            elem_classes="score-table",
                        )

                    with gr.TabItem("🔍 Critic"):
                        critic_panel = gr.Markdown("*Critic review will appear here.*")

                    with gr.TabItem("🐛 Debug"):
                        debug_panel = gr.JSON(label="")

        # ── Examples ──────────────────────────────────────────────────────
        with gr.Row():
            gr.Examples(
                examples=[
                    [15, 6,  1990, 14, 30, "Mumbai, India",   "", "", "What does my chart say about career prospects this year?",         "career",   ""],
                    [21, 3,  1985,  8,  0, "New Delhi, India", "", "", "When is a good time for marriage based on my dasha?",              "marriage", ""],
                    [4,  8,  1994,  1, 50, "Delhi, India",    "", "", "What is my current dasha period and what does it mean?",            "general",  ""],
                    [5,  11, 1975, 22, 15, "London, UK",      "", "", "What yogas do I have and how strong are they?",                    "general",  ""],
                    [12, 1,  1988, 10, 20, "Chennai, India",  "", "", "How is my health and what precautions should I take?",             "health",   ""],
                    [7,  4,  1995, 18, 45, "Singapore",       "", "", "Will I settle abroad? What does my chart say about foreign travel?","travel",   ""],
                ],
                inputs=[day, month, year, hour, minute, place, lat_str, lon_str,
                        query_input, domain_sel, query_date_str],
                label="📋 Try an Example",
                examples_per_page=3,
            )

        # ── Outputs list ──────────────────────────────────────────────────
        all_outputs = [
            chatbot, session_state,
            chart_panel, dasha_panel, transit_panel, yoga_panel,
            bphs_panel, weights_panel, critic_panel, debug_panel,
            bphs_highlights, status_bar,
        ]

        all_inputs = [
            year, month, day, hour, minute, place, lat_str, lon_str,
            query_input, domain_sel, query_date_str,
            chatbot, session_state,
        ]

        # Wire events
        ask_btn.click(fn=handle_query, inputs=all_inputs, outputs=all_outputs)
        query_input.submit(fn=handle_query, inputs=all_inputs, outputs=all_outputs, api_name="ask")
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
