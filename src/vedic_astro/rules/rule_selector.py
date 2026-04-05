"""
rule_selector.py — Selects the most relevant hardcoded BPHS rules for a
given chart, domain, and dasha state.

Called by the pipeline before agent execution — injects classical aphorisms
directly into each specialist agent's prompt without requiring a vector DB.
"""

from __future__ import annotations

from typing import Any

from vedic_astro.rules.bphs_rules import (
    ASPECT_RULES,
    DASHA_LORD_RULES,
    ANTARDASHA_RULES,
    DEBILITATION_SIGN,
    DIGNITY_RULES,
    DOMAIN_RULES,
    EXALTATION_SIGN,
    HOUSE_LORD_IN_HOUSE,
    HOUSE_SIGNIFICATIONS,
    MOOLATRIKONA,
    NEECHA_BHANGA_RULES,
    OWN_SIGNS,
    PLANET_IN_HOUSE,
    TRANSIT_RULES,
    YOGA_RULES,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _planet_dignity(planet: str, sign: str) -> str:
    if sign == EXALTATION_SIGN.get(planet):
        return "exalted"
    if sign == DEBILITATION_SIGN.get(planet):
        return "debilitated"
    if sign == MOOLATRIKONA.get(planet):
        return "moolatrikona"
    if sign in OWN_SIGNS.get(planet, []):
        return "own_sign"
    return "neutral"


# ─────────────────────────────────────────────────────────────────────────────
# Per-agent selectors
# ─────────────────────────────────────────────────────────────────────────────

def select_natal_rules(chart_data: dict[str, Any], domain: str, top_k: int = 8) -> list[str]:
    """
    Select BPHS rules relevant to natal chart interpretation.
    Includes: planet-in-house, dignity rules, yogas, domain rules.
    """
    rules: list[str] = []

    positions = chart_data.get("planets", chart_data.get("positions", {}))
    yogas     = chart_data.get("yogas", [])
    lagna     = chart_data.get("lagna", "")

    # 1. Planet-in-house rules for each planet
    for planet, pdata in positions.items():
        if not isinstance(pdata, dict):
            continue
        house = pdata.get("house") or pdata.get("house_number")
        sign  = pdata.get("sign", "")
        if not house:
            continue
        planet_rules = PLANET_IN_HOUSE.get(planet, {})
        rule = planet_rules.get(int(house))
        if rule:
            rules.append(rule)

        # 2. Dignity rule
        dignity = _planet_dignity(planet, sign)
        if dignity in DIGNITY_RULES and dignity != "neutral":
            rules.append(f"{planet} ({sign}) — {DIGNITY_RULES[dignity]}")

        # 3. Neecha Bhanga if debilitated
        if dignity == "debilitated":
            rules.extend(NEECHA_BHANGA_RULES)

    # 3. Yoga rules
    for yoga in yogas[:6]:
        yoga_name = yoga if isinstance(yoga, str) else yoga.get("name", "")
        for key, rule in YOGA_RULES.items():
            if key.lower() in yoga_name.lower() or yoga_name.lower() in key.lower():
                rules.append(f"{key}: {rule}")
                break

    # 4. Domain rules
    rules.extend(DOMAIN_RULES.get(domain, DOMAIN_RULES["general"])[:4])

    # 5. Foundation rule: always include house significations for key houses
    key_houses = {1, 7, 10, 5, 9}
    if domain == "marriage":
        key_houses = {1, 2, 7, 11}
    elif domain in ("career", "social_standing"):
        key_houses = {1, 10, 9, 2, 11}
    elif domain == "wealth":
        key_houses = {2, 11, 1, 9}
    elif domain == "health":
        key_houses = {1, 6, 8}

    for h in key_houses:
        info = HOUSE_SIGNIFICATIONS[h]
        rules.append(
            f"House {h} ({info['name']}): governs {', '.join(info['governs'][:4])}. Karaka: {info['karaka']}."
        )

    return _deduplicate(rules)[:top_k]


def select_dasha_rules(dasha_data: dict[str, Any], domain: str, top_k: int = 6) -> list[str]:
    """Select BPHS rules for Vimshottari Dasha interpretation."""
    rules: list[str] = []

    maha  = dasha_data.get("maha_lord") or dasha_data.get("mahadasha", "")
    antar = dasha_data.get("antar_lord") or dasha_data.get("antardasha", "")

    if maha and maha in DASHA_LORD_RULES:
        rules.append(DASHA_LORD_RULES[maha])

    if antar and maha in ANTARDASHA_RULES:
        sub = ANTARDASHA_RULES[maha].get(antar)
        if sub:
            rules.append(f"{maha}-{antar} antardasha: {sub}")

    # General dasha aphorism
    rules.append(
        "The Mahadasha lord's natal house, sign dignity, and house rulership determine the flavour of the dasha period. "
        "If the Mahadasha lord rules a kendra or trikona and is strong, the period is beneficial; if it rules a trik house (6,8,12) or is weak, challenges arise."
    )
    rules.append(
        "The Antardasha lord modifies the Mahadasha's theme — a benefic antardasha lord within a difficult mahadasha brings relief; "
        "a malefic antardasha within a beneficial mahadasha brings temporary obstacles."
    )

    # Domain-specific dasha timing rules
    domain_timing = {
        "marriage":       "Marriage timing: look for Mahadasha/Antardasha of 7th lord, Venus, or planets in 7th.",
        "career":         "Career timing: peak during Mahadasha/Antardasha of 10th lord, Sun, or planets in 10th.",
        "wealth":         "Wealth timing: major gains in Mahadasha/Antardasha of 2nd/11th lords or Jupiter.",
        "health":         "Health challenges arise in Mahadasha of 6th lord, 8th lord, or their antardasha.",
        "children":       "Children: most likely in Mahadasha/Antardasha of 5th lord or Jupiter.",
        "spirituality":   "Spiritual breakthroughs: in Mahadasha of 9th lord, Jupiter, or Ketu.",
        "travel":         "Travel abroad: in Mahadasha of 3rd, 9th, or 12th lord; or Rahu.",
    }
    if domain in domain_timing:
        rules.append(domain_timing[domain])

    return _deduplicate(rules)[:top_k]


def select_transit_rules(transit_data: dict[str, Any], domain: str, top_k: int = 5) -> list[str]:
    """Select BPHS gochara rules relevant to current transits."""
    rules: list[str] = list(TRANSIT_RULES[:4])

    sade_sati = transit_data.get("sade_sati", False)
    if sade_sati:
        rules.append(
            "Sade Sati is active: Saturn transiting around natal Moon brings a 7.5-year period of pressure, "
            "restructuring, hard lessons, and eventual transformation. Results depend on Saturn's natal strength."
        )

    # Jupiter gochara
    jup_from_moon = transit_data.get("jupiter_from_moon")
    if jup_from_moon in (5, 7, 9):
        rules.append(f"Jupiter transiting the {jup_from_moon}th from natal Moon — Gurubala active: highly auspicious period for growth, opportunity, and auspicious events.")
    elif jup_from_moon in (4, 8, 12):
        rules.append(f"Jupiter transiting the {jup_from_moon}th from natal Moon — Guru is weak: exercise caution in expansion; results are delayed.")

    rules.extend(DOMAIN_RULES.get(domain, [])[:2])
    return _deduplicate(rules)[:top_k]


def select_yoga_rules(yoga_data: dict[str, Any], domain: str, top_k: int = 6) -> list[str]:
    """Select BPHS yoga and dosha rules relevant to the chart's active yogas."""
    rules: list[str] = []

    active_yogas  = yoga_data.get("active_yogas",  [])
    active_doshas = yoga_data.get("active_doshas", [])

    for yoga in active_yogas[:5]:
        name = yoga if isinstance(yoga, str) else yoga.get("name", "")
        for key, rule in YOGA_RULES.items():
            if key.lower() in name.lower() or name.lower() in key.lower():
                rules.append(f"{key}: {rule}")
                break

    for dosha in active_doshas[:3]:
        name = dosha if isinstance(dosha, str) else dosha.get("name", "")
        for key, rule in YOGA_RULES.items():
            if key.lower() in name.lower():
                rules.append(f"{key} (dosha): {rule}")
                break

    # Add domain rules for yoga context
    rules.extend(DOMAIN_RULES.get(domain, DOMAIN_RULES["general"])[:3])

    # Include key aspect rules
    rules.extend(ASPECT_RULES[:2])

    return _deduplicate(rules)[:top_k]


# ─────────────────────────────────────────────────────────────────────────────
# Master selector — called by pipeline for all agents at once
# ─────────────────────────────────────────────────────────────────────────────

def select_all_rules(
    natal_data:   dict[str, Any],
    dasha_data:   dict[str, Any],
    transit_data: dict[str, Any],
    yoga_data:    dict[str, Any],
    domain:       str,
) -> dict[str, list[str]]:
    """
    Return a dict of agent_name → list[rule_string] for all five agents.
    Call once per pipeline run.
    """
    return {
        "natal":      select_natal_rules(natal_data,   domain, top_k=8),
        "dasha":      select_dasha_rules(dasha_data,   domain, top_k=6),
        "transit":    select_transit_rules(transit_data, domain, top_k=5),
        "divisional": _divisional_rules(domain),
        "yoga":       select_yoga_rules(yoga_data,     domain, top_k=6),
    }


def _divisional_rules(domain: str) -> list[str]:
    base = [
        "The Navamsha (D9) is the most important divisional chart — it reveals the soul's deeper nature and confirms Rashi chart results.",
        "A planet that is weak in D1 but strong in D9 (Vargottama or exalted in D9) will give better results than its D1 position suggests.",
        "Vargottama planets (same sign in D1 and D9) are extremely powerful and give consistent, reliable results.",
        "The D9 7th house and its lord confirm marriage quality — a strong D9 7th overrides a weak D1 7th.",
    ]
    if domain in ("career", "social_standing"):
        base.append("The Dashamsha (D10) chart governs career specifics — the D10 lagna lord and 10th lord reveal professional strength.")
    if domain in ("wealth",):
        base.append("The Hora chart (D2) determines wealth — Sun's Hora gives political/father wealth; Moon's Hora gives maternal/business wealth.")
    return base[:5]


def _deduplicate(rules: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for r in rules:
        key = r[:60]
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out
