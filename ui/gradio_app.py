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

# ─────────────────────────────────────────────────────────────────────────────
# City database for place autocomplete
# ─────────────────────────────────────────────────────────────────────────────

CITIES: list[str] = [
    # India
    "Mumbai, India", "Delhi, India", "New Delhi, India", "Bengaluru, India",
    "Bangalore, India", "Chennai, India", "Kolkata, India", "Hyderabad, India",
    "Pune, India", "Ahmedabad, India", "Jaipur, India", "Lucknow, India",
    "Kanpur, India", "Nagpur, India", "Indore, India", "Thane, India",
    "Bhopal, India", "Visakhapatnam, India", "Vadodara, India", "Surat, India",
    "Patna, India", "Agra, India", "Varanasi, India", "Nashik, India",
    "Meerut, India", "Faridabad, India", "Rajkot, India", "Kalyan, India",
    "Amritsar, India", "Ludhiana, India", "Jabalpur, India", "Gwalior, India",
    "Coimbatore, India", "Madurai, India", "Vijayawada, India", "Jodhpur, India",
    "Ranchi, India", "Guwahati, India", "Chandigarh, India", "Kochi, India",
    "Thiruvananthapuram, India", "Bhubaneswar, India", "Dehradun, India",
    "Shimla, India", "Srinagar, India", "Jammu, India", "Mysore, India",
    "Mangalore, India", "Hubli, India", "Belgaum, India", "Tiruchirappalli, India",
    "Tirupati, India", "Raipur, India", "Udaipur, India", "Ajmer, India",
    "Mathura, India", "Haridwar, India", "Rishikesh, India", "Allahabad, India",
    "Prayagraj, India", "Aurangabad, India", "Solapur, India", "Kolhapur, India",
    # UK
    "London, UK", "Manchester, UK", "Birmingham, UK", "Glasgow, UK",
    "Liverpool, UK", "Leeds, UK", "Sheffield, UK", "Bristol, UK",
    "Edinburgh, UK", "Leicester, UK", "Coventry, UK", "Bradford, UK",
    "Nottingham, UK", "Cardiff, UK", "Belfast, UK", "Southampton, UK",
    "Oxford, UK", "Cambridge, UK",
    # USA
    "New York, USA", "Los Angeles, USA", "Chicago, USA", "Houston, USA",
    "Phoenix, USA", "Philadelphia, USA", "San Antonio, USA", "San Diego, USA",
    "Dallas, USA", "San Jose, USA", "Austin, USA", "Jacksonville, USA",
    "San Francisco, USA", "Columbus, USA", "Indianapolis, USA", "Seattle, USA",
    "Denver, USA", "Nashville, USA", "Washington DC, USA", "Boston, USA",
    "Las Vegas, USA", "Portland, USA", "Memphis, USA", "Atlanta, USA",
    "Miami, USA", "Minneapolis, USA", "Honolulu, USA",
    # Canada
    "Toronto, Canada", "Vancouver, Canada", "Montreal, Canada", "Calgary, Canada",
    "Edmonton, Canada", "Ottawa, Canada", "Winnipeg, Canada", "Quebec City, Canada",
    # Australia
    "Sydney, Australia", "Melbourne, Australia", "Brisbane, Australia",
    "Perth, Australia", "Adelaide, Australia", "Gold Coast, Australia",
    "Canberra, Australia", "Auckland, New Zealand",
    # Europe
    "Paris, France", "Berlin, Germany", "Madrid, Spain", "Rome, Italy",
    "Amsterdam, Netherlands", "Brussels, Belgium", "Vienna, Austria",
    "Zurich, Switzerland", "Geneva, Switzerland", "Stockholm, Sweden",
    "Oslo, Norway", "Copenhagen, Denmark", "Helsinki, Finland",
    "Lisbon, Portugal", "Athens, Greece", "Warsaw, Poland", "Prague, Czech Republic",
    "Budapest, Hungary", "Bucharest, Romania", "Sofia, Bulgaria",
    "Zagreb, Croatia", "Ljubljana, Slovenia", "Munich, Germany",
    "Hamburg, Germany", "Frankfurt, Germany", "Cologne, Germany",
    "Barcelona, Spain", "Milan, Italy", "Naples, Italy", "Turin, Italy",
    "Marseille, France", "Lyon, France",
    # Middle East
    "Dubai, UAE", "Abu Dhabi, UAE", "Riyadh, Saudi Arabia", "Jeddah, Saudi Arabia",
    "Mecca, Saudi Arabia", "Medina, Saudi Arabia", "Kuwait City, Kuwait",
    "Doha, Qatar", "Manama, Bahrain", "Muscat, Oman", "Beirut, Lebanon",
    "Amman, Jordan", "Baghdad, Iraq", "Tehran, Iran", "Istanbul, Turkey",
    "Ankara, Turkey", "Tel Aviv, Israel", "Jerusalem, Israel",
    # Asia
    "Tokyo, Japan", "Osaka, Japan", "Kyoto, Japan", "Yokohama, Japan",
    "Beijing, China", "Shanghai, China", "Shenzhen, China", "Guangzhou, China",
    "Chengdu, China", "Wuhan, China", "Hong Kong", "Macau",
    "Seoul, South Korea", "Busan, South Korea",
    "Singapore", "Kuala Lumpur, Malaysia", "Bangkok, Thailand",
    "Jakarta, Indonesia", "Manila, Philippines", "Hanoi, Vietnam",
    "Ho Chi Minh City, Vietnam", "Colombo, Sri Lanka", "Dhaka, Bangladesh",
    "Karachi, Pakistan", "Lahore, Pakistan", "Islamabad, Pakistan",
    "Kathmandu, Nepal", "Thimphu, Bhutan", "Kabul, Afghanistan",
    "Tashkent, Uzbekistan", "Almaty, Kazakhstan",
    # Africa
    "Cairo, Egypt", "Lagos, Nigeria", "Nairobi, Kenya", "Johannesburg, South Africa",
    "Cape Town, South Africa", "Durban, South Africa", "Casablanca, Morocco",
    "Accra, Ghana", "Addis Ababa, Ethiopia", "Dar es Salaam, Tanzania",
    "Kampala, Uganda", "Khartoum, Sudan", "Tunis, Tunisia",
    "Algiers, Algeria", "Tripoli, Libya",
    # Latin America
    "São Paulo, Brazil", "Rio de Janeiro, Brazil", "Brasília, Brazil",
    "Buenos Aires, Argentina", "Lima, Peru", "Bogotá, Colombia",
    "Santiago, Chile", "Caracas, Venezuela", "Quito, Ecuador",
    "Mexico City, Mexico", "Guadalajara, Mexico", "Monterrey, Mexico",
    "Havana, Cuba", "Santo Domingo, Dominican Republic",
    # Russia & CIS
    "Moscow, Russia", "Saint Petersburg, Russia", "Novosibirsk, Russia",
    "Yekaterinburg, Russia", "Kyiv, Ukraine", "Minsk, Belarus",
    "Tbilisi, Georgia", "Yerevan, Armenia", "Baku, Azerbaijan",
]

CITIES_SORTED = sorted(set(CITIES))


def search_places(query: str) -> list[str]:
    """Return up to 10 city matches for the given query string."""
    if not query or len(query.strip()) < 2:
        return []
    q = query.strip().lower()
    # Prefix matches first, then substring matches
    prefix = [c for c in CITIES_SORTED if c.lower().startswith(q)]
    substr = [c for c in CITIES_SORTED if q in c.lower() and c not in prefix]
    return (prefix + substr)[:12]


# ─────────────────────────────────────────────────────────────────────────────
# CSS — minimal, Apple-inspired
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; }

body, .gradio-container {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text",
                 "Helvetica Neue", Arial, sans-serif !important;
    background: #f5f5f7 !important;
    color: #1d1d1f !important;
}

.gradio-container {
    max-width: 1440px !important;
    margin: 0 auto !important;
    padding: 0 2rem 3rem !important;
}

/* ── Header ─────────────────────────────────────────────── */
.hdr {
    text-align: center;
    padding: 3rem 1rem 2rem;
}
.hdr h1 {
    font-size: 2.6rem;
    font-weight: 700;
    letter-spacing: -0.04em;
    color: #1d1d1f;
    margin: 0 0 0.45rem;
    line-height: 1.1;
}
.hdr p {
    font-size: 1rem;
    color: #6e6e73;
    margin: 0;
    letter-spacing: -0.01em;
}

/* ── Columns ────────────────────────────────────────────── */
.col-form  { background: #fff; border-radius: 16px; padding: 1.4rem 1.2rem; box-shadow: 0 1px 8px rgba(0,0,0,0.07); }
.col-right { background: #fff; border-radius: 16px; padding: 1.4rem 1.2rem; box-shadow: 0 1px 8px rgba(0,0,0,0.07); }

/* ── Section labels ─────────────────────────────────────── */
.sec-label {
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #aeaeb2;
    margin: 1.1rem 0 0.45rem;
    display: block;
    line-height: 1;
}
.sec-label:first-child { margin-top: 0; }

/* ── Inputs & Number fields ─────────────────────────────── */
label > span { font-size: 0.8rem !important; font-weight: 500 !important; color: #3a3a3c !important; margin-bottom: 4px !important; }
input[type=number], input[type=text], textarea {
    background: #f5f5f7 !important;
    border: 1.5px solid #e5e5ea !important;
    border-radius: 9px !important;
    font-size: 0.88rem !important;
    color: #1d1d1f !important;
    font-family: inherit !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
input[type=number]:focus, input[type=text]:focus, textarea:focus {
    background: #fff !important;
    border-color: #0071e3 !important;
    box-shadow: 0 0 0 3px rgba(0,113,227,0.12) !important;
    outline: none !important;
}
/* Dropdown */
.svelte-select {
    background: #f5f5f7 !important;
    border: 1.5px solid #e5e5ea !important;
    border-radius: 9px !important;
}

/* ── Primary button ─────────────────────────────────────── */
.btn-ask {
    background: #0071e3 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 980px !important;
    font-weight: 600 !important;
    font-size: 0.92rem !important;
    letter-spacing: -0.01em !important;
    min-height: 42px !important;
    padding: 0 1.4rem !important;
    box-shadow: none !important;
    font-family: inherit !important;
    transition: background 0.15s, transform 0.1s !important;
    white-space: nowrap !important;
}
.btn-ask:hover  { background: #0077ed !important; }
.btn-ask:active { background: #006edb !important; transform: scale(0.97) !important; }

/* ── Secondary button ───────────────────────────────────── */
.btn-clear {
    background: #e8e8ed !important;
    color: #1d1d1f !important;
    border: none !important;
    border-radius: 980px !important;
    font-weight: 500 !important;
    font-size: 0.82rem !important;
    min-height: 34px !important;
    padding: 0 1rem !important;
    font-family: inherit !important;
}
.btn-clear:hover { background: #d2d2d7 !important; }

/* ── Chat ───────────────────────────────────────────────── */
.chatbot { border: 1.5px solid #e5e5ea !important; border-radius: 14px !important; }
.chatbot .message { font-size: 0.9rem !important; line-height: 1.7 !important; }

/* ── Query textarea ─────────────────────────────────────── */
.query-box textarea {
    border-radius: 12px !important;
    border: 1.5px solid #e5e5ea !important;
    background: #f5f5f7 !important;
    font-size: 0.92rem !important;
    resize: none !important;
    min-height: 60px !important;
}
.query-box textarea:focus {
    background: #fff !important;
    border-color: #0071e3 !important;
    box-shadow: 0 0 0 3px rgba(0,113,227,0.12) !important;
}

/* ── Status line ────────────────────────────────────────── */
.status-line { font-size: 0.78rem !important; color: #aeaeb2 !important; text-align: center; padding: 2px 0; }
.status-line strong { color: #3a3a3c !important; }
.status-line p { margin: 0 !important; }

/* ── Tabs ───────────────────────────────────────────────── */
.tab-nav { border-bottom: 1px solid #e5e5ea !important; }
.tab-nav button {
    font-size: 0.79rem !important;
    font-weight: 500 !important;
    color: #6e6e73 !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    padding: 0.45rem 0.8rem !important;
    background: transparent !important;
    font-family: inherit !important;
    transition: color 0.15s, border-color 0.15s !important;
}
.tab-nav button.selected {
    color: #0071e3 !important;
    border-bottom-color: #0071e3 !important;
    font-weight: 600 !important;
}

/* ── Panel markdown ─────────────────────────────────────── */
.panel-md { font-size: 0.87rem !important; line-height: 1.75 !important; }
.panel-md h3 { font-size: 0.88rem !important; font-weight: 600 !important; color: #1d1d1f !important; margin: 0.9rem 0 0.2rem !important; }
.panel-md p  { margin: 0.3rem 0 !important; }
.panel-md blockquote {
    border-left: 2px solid #d2d2d7;
    margin: 0.4rem 0;
    padding: 0.25rem 0.7rem;
    color: #6e6e73;
    font-size: 0.83rem;
}
.panel-md code { background: #f5f5f7; padding: 1px 5px; border-radius: 4px; font-size: 0.83rem; }

/* ── BPHS rule items ────────────────────────────────────── */
.rule-pill {
    background: #f5f5f7;
    border-radius: 9px;
    padding: 0.5rem 0.8rem;
    margin: 0.3rem 0;
    font-size: 0.8rem;
    line-height: 1.55;
    color: #3a3a3c;
    display: block;
}
.rule-pill-label {
    font-size: 0.62rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #aeaeb2;
    display: block;
    margin-bottom: 0.15rem;
}

/* ── Score table ────────────────────────────────────────── */
.score-tbl table { font-size: 0.84rem !important; }
.score-tbl th { font-size: 0.72rem !important; font-weight: 700 !important; text-transform: uppercase !important; letter-spacing: 0.05em !important; color: #6e6e73 !important; }

/* ── Examples ───────────────────────────────────────────── */
.examples label { font-size: 0.78rem !important; color: #6e6e73 !important; font-weight: 600 !important; }

/* ── Section heading inside panels ─────────────────────── */
.sec-heading { font-size: 0.65rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #aeaeb2; margin: 0 0 0.8rem; }

footer, .built-with { display: none !important; }
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

# ─────────────────────────────────────────────────────────────────────────────
# Core handler
# ─────────────────────────────────────────────────────────────────────────────

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
        err = f"Error: {exc}"
        return (
            chat_history + [{"role": "user", "content": str(query)}, {"role": "assistant", "content": err}],
            session_state, "", "", "", "", "", _EMPTY_DF.copy(), "", {}, "", err,
        )

    _run_async(_save_session(session_state, birth, reading))

    response_md = reading.to_markdown() if hasattr(reading, "to_markdown") else str(reading.final_reading)
    new_history = chat_history + [
        {"role": "user",      "content": str(query)},
        {"role": "assistant", "content": response_md},
    ]

    score_val = reading.score.final_score if reading.score else 0
    interp = reading.score.interpretation.replace("_", " ").title() if reading.score else ""
    status = f"Domain · **{domain}** &nbsp;·&nbsp; Score · **{score_val:.2f}** &nbsp;·&nbsp; {interp}"

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


# ─────────────────────────────────────────────────────────────────────────────
# Renderers
# ─────────────────────────────────────────────────────────────────────────────

def _render_chart(r) -> str:
    if not r.natal_narrative:
        return "*No natal data.*"
    tail = f"\n\n---\n**Score** `{r.score.final_score:.2f}` · {r.score.interpretation.replace('_',' ').title()}" if r.score else ""
    return r.natal_narrative + tail

def _render_dasha(r) -> str:
    if not r.dasha_narrative:
        return "*No dasha data.*"
    tail = f"\n\n---\n**Dasha activation** `{r.score.dasha_activation:.2f}`" if r.score else ""
    return r.dasha_narrative + tail

def _render_transit(r) -> str:
    if not r.transit_narrative:
        return "*No transit data.*"
    tail = f"\n\n---\n**Transit trigger** `{r.score.transit_trigger:.2f}`" if r.score else ""
    return r.transit_narrative + tail

def _render_yogas(r) -> str:
    return r.yoga_narrative if r.yoga_narrative else "*No yoga data.*"

def _render_bphs_rules(r) -> str:
    rules = getattr(r, "retrieved_rules", {})
    if not rules:
        return "*No rules retrieved.*"
    lines = []
    for agent, rule_list in rules.items():
        if rule_list:
            lines.append(f"**{agent.title()}**")
            for rule in rule_list[:4]:
                lines.append(f"> {rule}\n")
    return "\n".join(lines) or "*No rules.*"

def _bphs_rule_html(r) -> str:
    rules = getattr(r, "retrieved_rules", {})
    flat = [(agent, rule) for agent, rl in rules.items() for rule in rl[:2]]
    if not flat:
        return '<p style="color:#aeaeb2;font-size:0.82rem;margin:0">No rules retrieved.</p>'
    html = ""
    for agent, rule in flat[:8]:
        html += (
            f'<span class="rule-pill">'
            f'<span class="rule-pill-label">{agent.title()}</span>'
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
        return f"✓ Passed · score {score:.2f}" + (" — high confidence" if score >= 0.65 else "")
    lines = [f"Score `{score:.2f}` · Revised: {'yes' if r.was_revised else 'no'}", ""]
    for note in r.critic_notes:
        lines.append(f"- {note}")
    return "\n".join(lines)

def handle_clear(session_state):
    return ([], session_state, "", "", "", "", "", _EMPTY_DF.copy(), "", {}, "", "")


# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────

def build_demo() -> gr.Blocks:

    with gr.Blocks(title="Vedic Astrology AI", css=CSS) as demo:

        session_state = gr.State({})

        # Header
        gr.HTML("""
        <div class="hdr">
          <h1>Vedic Astrology AI</h1>
          <p>Classical Parashari readings · Swiss Ephemeris · BPHS rules · Multi-agent AI</p>
        </div>
        """)

        with gr.Row(equal_height=False):

            # ── Left column: birth form ───────────────────────────────────
            with gr.Column(scale=1, min_width=240, elem_classes="col-form"):

                gr.HTML('<span class="sec-label">Date of birth</span>')
                with gr.Row():
                    day   = gr.Number(label="Day",   value=15,   precision=0, minimum=1,   maximum=31,   scale=1)
                    month = gr.Number(label="Month", value=6,    precision=0, minimum=1,   maximum=12,   scale=1)
                    year  = gr.Number(label="Year",  value=1990, precision=0, minimum=1800, maximum=2100, scale=2)

                gr.HTML('<span class="sec-label">Time of birth</span>')
                with gr.Row():
                    hour   = gr.Number(label="Hour (0–23)", value=14, precision=0, minimum=0, maximum=23, scale=1)
                    minute = gr.Number(label="Minute",      value=30, precision=0, minimum=0, maximum=59, scale=1)

                gr.HTML('<span class="sec-label">Place of birth</span>')
                place = gr.Dropdown(
                    choices=CITIES_SORTED[:20],
                    value=None,
                    allow_custom_value=True,
                    label="City, Country",
                    info="Type to search — any city worldwide",
                )

                with gr.Row():
                    lat_str = gr.Textbox(label="Latitude",  placeholder="19.076", scale=1)
                    lon_str = gr.Textbox(label="Longitude", placeholder="72.877", scale=1)

                gr.HTML('<span class="sec-label" style="margin-top:1.2rem">Query options</span>')
                domain_sel = gr.Dropdown(
                    choices=["auto", "general", "career", "marriage", "wealth",
                             "health", "spirituality", "children", "travel", "family", "social_standing"],
                    value="auto",
                    label="Life domain",
                    info="'auto' detects domain from your question",
                )
                query_date_str = gr.Textbox(
                    label="Transit date",
                    placeholder="YYYY-MM-DD  (blank = today)",
                )

                gr.HTML('<div style="margin-top:1rem"></div>')
                clear_btn = gr.Button("Clear", elem_classes="btn-clear", size="sm")

            # ── Centre column: chat ───────────────────────────────────────
            with gr.Column(scale=3):

                chatbot = gr.Chatbot(
                    label="",
                    height=460,
                    type="messages",
                    show_copy_button=True,
                    show_label=False,
                    elem_classes="chatbot",
                    placeholder=(
                        "**Ask anything about your chart**\n\n"
                        "Enter birth details on the left, then type your question — "
                        "career, relationships, wealth, health, timing of events, spiritual path.\n\n"
                        "*Try one of the examples below to get started.*"
                    ),
                )

                with gr.Row(equal_height=True):
                    query_input = gr.Textbox(
                        label="",
                        placeholder="What does my chart say about…",
                        lines=2,
                        scale=5,
                        show_label=False,
                        elem_classes="query-box",
                    )
                    ask_btn = gr.Button("Ask", variant="primary", scale=1,
                                        min_width=72, elem_classes="btn-ask")

                status_bar = gr.Markdown("", elem_classes="status-line")

                gr.HTML('<p class="sec-heading" style="margin-top:1.4rem">Classical rules applied to this reading</p>')
                bphs_highlights = gr.HTML(
                    '<p style="color:#aeaeb2;font-size:0.82rem;margin:0">Rules will appear after your first reading.</p>'
                )

            # ── Right column: analysis ────────────────────────────────────
            with gr.Column(scale=2, elem_classes="col-right"):

                gr.HTML('<p class="sec-heading">Analysis</p>')

                with gr.Tabs():
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
                            elem_classes="score-tbl",
                        )
                    with gr.TabItem("Critic"):
                        critic_panel = gr.Markdown("*—*", elem_classes="panel-md")
                    with gr.TabItem("Debug"):
                        debug_panel = gr.JSON(label="")

        # ── Examples ──────────────────────────────────────────────────────
        gr.HTML('<div style="height:1.2rem"></div>')
        gr.Examples(
            examples=[
                [15, 6,  1990, 14, 30, "Mumbai, India",    "", "", "What does my chart say about career this year?",               "career",   ""],
                [21, 3,  1985,  8,  0, "New Delhi, India", "", "", "When is a good time for marriage based on my dasha?",          "marriage", ""],
                [4,  8,  1994,  1, 50, "Delhi, India",     "", "", "What is my current dasha period and what does it mean?",       "general",  ""],
                [5,  11, 1975, 22, 15, "London, UK",       "", "", "What yogas do I have and how strong are they?",                "general",  ""],
                [12, 1,  1988, 10, 20, "Chennai, India",   "", "", "What does my chart say about health and longevity?",           "health",   ""],
                [7,  4,  1995, 18, 45, "Singapore",        "", "", "Will I settle abroad? What does my chart say about travel?",   "travel",   ""],
            ],
            inputs=[day, month, year, hour, minute, place, lat_str, lon_str,
                    query_input, domain_sel, query_date_str],
            label="Examples",
            examples_per_page=3,
        )

        # ── Wire events ───────────────────────────────────────────────────
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

        # Place autocomplete
        place.input(
            fn=lambda q: gr.Dropdown(choices=search_places(q) if q else CITIES_SORTED[:20]),
            inputs=[place],
            outputs=[place],
        )

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
