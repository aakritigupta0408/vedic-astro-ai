"""
gradio_app.py — Vedic Astrology AI · Minimal Apple-inspired UI
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
/* ── Reset & Base ─────────────────────────────────────── */
* { box-sizing: border-box; }
body, .gradio-container {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial, sans-serif !important;
    background: #f5f5f7 !important;
    color: #1d1d1f !important;
}
.gradio-container { max-width: 1400px !important; margin: 0 auto !important; padding: 0 1.5rem !important; }

/* ── Header ───────────────────────────────────────────── */
.hdr {
    text-align: center;
    padding: 3.5rem 1rem 2.5rem;
}
.hdr h1 {
    font-size: 3rem;
    font-weight: 700;
    letter-spacing: -0.04em;
    color: #1d1d1f;
    margin: 0 0 0.5rem;
    line-height: 1.1;
}
.hdr p {
    font-size: 1.1rem;
    color: #6e6e73;
    margin: 0;
    font-weight: 400;
    letter-spacing: -0.01em;
}

/* ── Cards ────────────────────────────────────────────── */
.card {
    background: #ffffff;
    border-radius: 18px;
    padding: 1.5rem;
    border: none;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04);
}

/* ── Form labels ──────────────────────────────────────── */
.field-group-label {
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #aeaeb2;
    margin: 1.2rem 0 0.5rem;
    display: block;
}
.field-group-label:first-child { margin-top: 0; }

/* ── Inputs ───────────────────────────────────────────── */
input[type=number], input[type=text], textarea, select,
.gr-textbox textarea, .gr-number input, .gr-dropdown select {
    background: #f5f5f7 !important;
    border: 1.5px solid transparent !important;
    border-radius: 10px !important;
    font-size: 0.9rem !important;
    color: #1d1d1f !important;
    transition: border-color 0.15s, background 0.15s !important;
    font-family: inherit !important;
}
input:focus, textarea:focus, select:focus,
.gr-textbox textarea:focus, .gr-number input:focus {
    background: #fff !important;
    border-color: #0071e3 !important;
    box-shadow: 0 0 0 3px rgba(0,113,227,0.12) !important;
    outline: none !important;
}

/* ── Primary button ───────────────────────────────────── */
.btn-primary {
    background: #0071e3 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 980px !important;
    font-weight: 600 !important;
    font-size: 0.92rem !important;
    padding: 0.6rem 1.4rem !important;
    letter-spacing: -0.01em !important;
    transition: background 0.15s, transform 0.1s !important;
    box-shadow: none !important;
    font-family: inherit !important;
}
.btn-primary:hover { background: #0077ed !important; transform: none !important; }
.btn-primary:active { background: #006edb !important; transform: scale(0.98) !important; }

/* ── Secondary button ─────────────────────────────────── */
.btn-secondary {
    background: #e8e8ed !important;
    color: #1d1d1f !important;
    border: none !important;
    border-radius: 980px !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    padding: 0.5rem 1.1rem !important;
    font-family: inherit !important;
}
.btn-secondary:hover { background: #d2d2d7 !important; }

/* ── Chat ─────────────────────────────────────────────── */
.chatbot-wrap { border-radius: 18px !important; overflow: hidden; }
.chatbot-wrap .message-wrap { padding: 1rem !important; }
.chatbot-wrap .user { background: #0071e3 !important; color: #fff !important; border-radius: 18px 18px 4px 18px !important; }
.chatbot-wrap .bot  { background: #f5f5f7 !important; color: #1d1d1f !important; border-radius: 18px 18px 18px 4px !important; }

/* ── Query box ────────────────────────────────────────── */
.query-wrap textarea {
    background: #f5f5f7 !important;
    border: 1.5px solid transparent !important;
    border-radius: 14px !important;
    font-size: 0.95rem !important;
    resize: none !important;
    line-height: 1.5 !important;
    padding: 0.75rem 1rem !important;
}
.query-wrap textarea:focus {
    background: #fff !important;
    border-color: #0071e3 !important;
    box-shadow: 0 0 0 3px rgba(0,113,227,0.12) !important;
}

/* ── Status line ──────────────────────────────────────── */
.status-line {
    font-size: 0.8rem;
    color: #aeaeb2;
    text-align: center;
    padding: 0.3rem 0;
    letter-spacing: -0.01em;
}
.status-line strong { color: #1d1d1f; }

/* ── Tabs ─────────────────────────────────────────────── */
.tabs-wrap .tab-nav {
    border-bottom: 1px solid #e5e5ea !important;
    margin-bottom: 1rem !important;
    gap: 0 !important;
}
.tabs-wrap .tab-nav button {
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    color: #6e6e73 !important;
    border: none !important;
    border-radius: 0 !important;
    padding: 0.5rem 0.9rem !important;
    background: transparent !important;
    border-bottom: 2px solid transparent !important;
    transition: color 0.15s, border-color 0.15s !important;
    font-family: inherit !important;
}
.tabs-wrap .tab-nav button.selected, .tabs-wrap .tab-nav button:focus {
    color: #0071e3 !important;
    border-bottom-color: #0071e3 !important;
    background: transparent !important;
}

/* ── Panel text ───────────────────────────────────────── */
.panel-md { font-size: 0.88rem !important; line-height: 1.7 !important; color: #1d1d1f !important; }
.panel-md h2, .panel-md h3 { font-size: 0.9rem !important; font-weight: 600 !important; margin: 1rem 0 0.3rem !important; }
.panel-md p { margin: 0.4rem 0 !important; }
.panel-md blockquote {
    border-left: 3px solid #e5e5ea;
    margin: 0.5rem 0;
    padding: 0.3rem 0.8rem;
    color: #6e6e73;
    font-size: 0.84rem;
}

/* ── BPHS rule pills ──────────────────────────────────── */
.rule-item {
    display: block;
    background: #f5f5f7;
    border-radius: 10px;
    padding: 0.55rem 0.85rem;
    margin: 0.3rem 0;
    font-size: 0.82rem;
    color: #3a3a3c;
    line-height: 1.5;
}
.rule-label {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #aeaeb2;
    display: block;
    margin-bottom: 0.15rem;
}

/* ── Examples ─────────────────────────────────────────── */
.examples-wrap .label { font-size: 0.8rem !important; color: #6e6e73 !important; font-weight: 500 !important; }
.examples-wrap table td { font-size: 0.82rem !important; padding: 0.4rem 0.6rem !important; }

/* ── Section heading ──────────────────────────────────── */
.section-heading {
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: #aeaeb2;
    margin: 0 0 0.75rem;
}

/* ── Score table ──────────────────────────────────────── */
.score-table table { font-size: 0.85rem !important; }
.score-table th { color: #6e6e73 !important; font-weight: 600 !important; font-size: 0.78rem !important; text-transform: uppercase !important; letter-spacing: 0.04em !important; }

/* ── Hide gradio chrome ───────────────────────────────── */
footer, .built-with { display: none !important; }
.gr-prose h2 { font-size: 1rem !important; }
.hide-label > label > span { display: none !important; }
"""

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


_solver = None

def get_solver():
    global _solver
    if _solver is None:
        from vedic_astro.agents.solver_agent import SolverAgent
        _solver = SolverAgent()
    return _solver


_DOMAIN_KW = {
    "career":       ["career", "job", "work", "profession", "business", "promotion"],
    "marriage":     ["marriage", "spouse", "partner", "relationship", "wedding", "love", "husband", "wife"],
    "wealth":       ["wealth", "money", "finance", "rich", "income", "property"],
    "health":       ["health", "disease", "illness", "surgery", "longevity", "body"],
    "spirituality": ["spiritual", "meditation", "dharma", "moksha", "karma"],
    "children":     ["child", "children", "baby", "son", "daughter", "pregnancy"],
    "travel":       ["travel", "foreign", "abroad", "relocate", "journey"],
    "family":       ["family", "mother", "father", "sibling", "home"],
}

def auto_domain(query: str, explicit: str) -> str:
    if explicit and explicit != "auto":
        return explicit
    ql = query.lower()
    for domain, kws in _DOMAIN_KW.items():
        if any(k in ql for k in kws):
            return domain
    return "general"


_EMPTY_DF = pd.DataFrame(columns=["Layer", "Weight %", "Score", "Rating"])


def handle_query(
    year, month, day, hour, minute, place, lat_str, lon_str,
    query, domain_sel, query_date_str,
    chat_history, session_state,
):
    if not str(query).strip():
        return (chat_history, session_state, "", "", "", "", "", _EMPTY_DF.copy(), "", {}, "", "")

    from vedic_astro.agents.pipeline import BirthData

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
        err = f"Something went wrong — {exc}"
        return (
            chat_history + [{"role": "user", "content": str(query)}, {"role": "assistant", "content": err}],
            session_state, "", "", "", "", "", _EMPTY_DF.copy(), "", {}, "", err,
        )

    _run_async(_save_session(session_state, birth, reading))

    response_md = reading.to_markdown() if hasattr(reading, "to_markdown") else str(reading.final_reading)
    new_history = chat_history + [{"role": "user", "content": str(query)}, {"role": "assistant", "content": response_md}]

    score_val = reading.score.final_score if reading.score else 0
    status = f"Domain · **{domain}** &nbsp;·&nbsp; Score · **{score_val:.2f}** &nbsp;·&nbsp; {reading.score.interpretation.replace('_',' ').title() if reading.score else ''}"

    return (
        new_history, session_state,
        _render_chart(reading),
        _render_dasha(reading),
        _render_transit(reading),
        _render_yogas(reading),
        _render_bphs_rules(reading),
        _render_weights(reading),
        _render_critic(reading),
        reading.to_debug_dict() if hasattr(reading, "to_debug_dict") else {},
        _bphs_rule_html(reading),
        status,
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


# ── Renderers ────────────────────────────────────────────────────────────────

def _render_chart(r) -> str:
    if not r.natal_narrative:
        return "*—*"
    tail = f"\n\n**Score** `{r.score.final_score:.2f}` · {r.score.interpretation.replace('_',' ').title()}" if r.score else ""
    return r.natal_narrative + tail


def _render_dasha(r) -> str:
    if not r.dasha_narrative:
        return "*—*"
    tail = f"\n\n**Dasha activation** `{r.score.dasha_activation:.2f}`" if r.score else ""
    return r.dasha_narrative + tail


def _render_transit(r) -> str:
    if not r.transit_narrative:
        return "*—*"
    tail = f"\n\n**Transit trigger** `{r.score.transit_trigger:.2f}`" if r.score else ""
    return r.transit_narrative + tail


def _render_yogas(r) -> str:
    return r.yoga_narrative if r.yoga_narrative else "*—*"


def _render_bphs_rules(r) -> str:
    rules = getattr(r, "retrieved_rules", {})
    if not rules:
        return "*—*"
    lines = []
    for agent, rule_list in rules.items():
        if rule_list:
            lines.append(f"**{agent.title()}**")
            for rule in rule_list[:4]:
                lines.append(f"> {rule}\n")
    return "\n".join(lines) or "*—*"


def _bphs_rule_html(r) -> str:
    rules = getattr(r, "retrieved_rules", {})
    flat = [(agent, rule) for agent, rl in rules.items() for rule in rl[:2]]
    if not flat:
        return '<p style="color:#aeaeb2;font-size:0.82rem">No rules retrieved.</p>'
    html = ""
    for agent, rule in flat[:8]:
        html += (
            f'<span class="rule-item">'
            f'<span class="rule-label">{agent.title()}</span>'
            f'{rule}'
            f'</span>'
        )
    return html


def _render_weights(r) -> pd.DataFrame:
    rows = [
        {"Layer": s.label, "Weight %": s.weight_pct, "Score": f"{s.component_score:.2f}", "Rating": s.score_label}
        for s in r.reasoning_chain
    ]
    if not rows:
        return _EMPTY_DF.copy()
    df = pd.DataFrame(rows)
    df.loc[len(df)] = {
        "Layer": "COMPOSITE", "Weight %": 100,
        "Score": f"{r.score.final_score:.2f}",
        "Rating": r.score.interpretation.replace("_", " ").title(),
    }
    return df


def _render_critic(r) -> str:
    score = r.score.final_score if r.score else 0
    if not r.critic_notes:
        return f"Passed · {score:.2f}" + (" — high confidence" if score >= 0.65 else "")
    lines = [f"Score `{score:.2f}` · Revised: {'yes' if r.was_revised else 'no'}", ""]
    for note in r.critic_notes:
        lines.append(f"- {note}")
    return "\n".join(lines)


def handle_clear(session_state):
    return ([], session_state, "", "", "", "", "", _EMPTY_DF.copy(), "", {}, "", "")


# ── Build UI ─────────────────────────────────────────────────────────────────

def build_demo() -> gr.Blocks:

    with gr.Blocks(title="Vedic Astrology AI", css=CSS) as demo:

        session_state = gr.State({})

        # Header
        gr.HTML("""
        <div class="hdr">
          <h1>Vedic Astrology AI</h1>
          <p>Classical Parashari readings · Swiss Ephemeris · BPHS rules · Multi-agent synthesis</p>
        </div>
        """)

        with gr.Row(equal_height=False):

            # ── Left: Birth Form ──────────────────────────────────────────
            with gr.Column(scale=1, min_width=220, elem_classes="card"):

                gr.HTML('<span class="field-group-label">Date of birth</span>')
                with gr.Row():
                    day   = gr.Number(label="Day",   value=15,   precision=0, minimum=1,   maximum=31,   scale=1, elem_classes="hide-label")
                    month = gr.Number(label="Month", value=6,    precision=0, minimum=1,   maximum=12,   scale=1, elem_classes="hide-label")
                    year  = gr.Number(label="Year",  value=1990, precision=0, minimum=1800, maximum=2100, scale=2, elem_classes="hide-label")

                gr.HTML('<span class="field-group-label">Time of birth</span>')
                with gr.Row():
                    hour   = gr.Number(label="Hour",   value=14, precision=0, minimum=0, maximum=23, scale=1, elem_classes="hide-label")
                    minute = gr.Number(label="Minute", value=30, precision=0, minimum=0, maximum=59, scale=1, elem_classes="hide-label")

                gr.HTML('<span class="field-group-label">Place of birth</span>')
                place = gr.Textbox(label="Place", placeholder="Mumbai, India", lines=1, show_label=False)

                with gr.Row():
                    lat_str = gr.Textbox(label="Lat", placeholder="19.076", scale=1, show_label=False)
                    lon_str = gr.Textbox(label="Lon", placeholder="72.877", scale=1, show_label=False)

                gr.HTML('<span class="field-group-label" style="margin-top:1rem">Domain</span>')
                domain_sel = gr.Dropdown(
                    choices=["auto","general","career","marriage","wealth",
                             "health","spirituality","children","travel","family","social_standing"],
                    value="auto", show_label=False,
                )

                gr.HTML('<span class="field-group-label">Transit date</span>')
                query_date_str = gr.Textbox(
                    label="Date", placeholder="Leave blank for today",
                    show_label=False,
                )

                gr.HTML('<div style="height:0.5rem"></div>')
                clear_btn = gr.Button("Clear", elem_classes="btn-secondary", size="sm")

            # ── Centre: Chat ──────────────────────────────────────────────
            with gr.Column(scale=3):

                chatbot = gr.Chatbot(
                    label="",
                    height=480,
                    show_copy_button=True,
                    show_label=False,
                    type="messages",
                    elem_classes="chatbot-wrap",
                    placeholder=(
                        "**Ask anything about your chart**\n\n"
                        "Enter your birth details, then type a question — "
                        "career, relationships, health, timing, spiritual path…\n\n"
                        "Or try one of the examples below."
                    ),
                )

                with gr.Row(equal_height=True):
                    query_input = gr.Textbox(
                        label="", placeholder="What does my chart say about…",
                        lines=2, scale=5, show_label=False,
                        elem_classes="query-wrap",
                    )
                    ask_btn = gr.Button("Ask", variant="primary", scale=1,
                                        min_width=70, elem_classes="btn-primary")

                status_bar = gr.Markdown("", elem_classes="status-line")

                # BPHS rules
                gr.HTML('<p class="section-heading" style="margin-top:1.2rem">Classical rules applied</p>')
                bphs_highlights = gr.HTML(
                    '<p style="color:#aeaeb2;font-size:0.82rem">Rules will appear after your first reading.</p>'
                )

            # ── Right: Analysis ───────────────────────────────────────────
            with gr.Column(scale=2, elem_classes="card"):

                gr.HTML('<p class="section-heading">Analysis</p>')

                with gr.Tabs(elem_classes="tabs-wrap"):

                    with gr.TabItem("Natal"):
                        chart_panel = gr.Markdown("*—*", elem_classes="panel-md")

                    with gr.TabItem("Dasha"):
                        dasha_panel = gr.Markdown("*—*", elem_classes="panel-md")

                    with gr.TabItem("Transits"):
                        transit_panel = gr.Markdown("*—*", elem_classes="panel-md")

                    with gr.TabItem("Yogas"):
                        yoga_panel = gr.Markdown("*—*", elem_classes="panel-md")

                    with gr.TabItem("BPHS"):
                        bphs_panel = gr.Markdown("*—*", elem_classes="panel-md")

                    with gr.TabItem("Score"):
                        weights_panel = gr.DataFrame(
                            value=_EMPTY_DF.copy(),
                            interactive=False,
                            elem_classes="score-table",
                        )

                    with gr.TabItem("Critic"):
                        critic_panel = gr.Markdown("*—*", elem_classes="panel-md")

                    with gr.TabItem("Debug"):
                        debug_panel = gr.JSON(label="")

        # Examples
        gr.HTML('<div style="height:1.5rem"></div>')
        gr.Examples(
            examples=[
                [15, 6,  1990, 14, 30, "Mumbai, India",    "", "", "What does my chart say about career this year?",              "career",   ""],
                [21, 3,  1985,  8,  0, "New Delhi, India", "", "", "When is a good time for marriage based on my dasha?",         "marriage", ""],
                [4,  8,  1994,  1, 50, "Delhi, India",     "", "", "What is my current dasha period and what does it mean?",      "general",  ""],
                [5,  11, 1975, 22, 15, "London, UK",       "", "", "What yogas do I have and how strong are they?",               "general",  ""],
                [12, 1,  1988, 10, 20, "Chennai, India",   "", "", "What does my chart say about health and longevity?",          "health",   ""],
                [7,  4,  1995, 18, 45, "Singapore",        "", "", "Will I settle abroad? What does my chart say about travel?",  "travel",   ""],
            ],
            inputs=[day, month, year, hour, minute, place, lat_str, lon_str,
                    query_input, domain_sel, query_date_str],
            label="Examples",
            examples_per_page=3,
        )

        # Wire
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
