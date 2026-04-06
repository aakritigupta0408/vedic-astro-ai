"""
rule_selector.py — Selects the most relevant hardcoded BPHS rules for a
given chart, domain, and dasha state.

Called by the pipeline before agent execution — injects classical aphorisms
directly into each specialist agent's prompt without requiring a vector DB.
"""

from __future__ import annotations

from typing import Any

from vedic_astro.rules.bphs_rules import (
    ADDITIONAL_YOGA_RULES,
    ANTARDASHA_RULES,
    ANTARDASHA_RULES_FULL,
    ASPECT_RULES,
    ASHTAKAVARGA_RULES,
    DASHA_HOUSE_LORD_EFFECTS,
    DASHA_LORD_RULES,
    DEBILITATION_SIGN,
    DIGNITY_RULES,
    DOMAIN_RULES,
    EXALTATION_SIGN,
    GOCHARA_PLANET_IN_HOUSE,
    GRAHA_DRISHTI_RULES,
    HOUSE_LORD_IN_HOUSE,
    HOUSE_SIGNIFICATIONS,
    JAIMINI_RULES,
    KALA_SARPA_YOGA_RULES,
    KARAKA_RULES,
    LAGNA_RESULTS,
    MANGAL_DOSHA_RULES,
    MOOLATRIKONA,
    MUHURTA_RULES,
    NABHASA_YOGA_RULES,
    NAKSHATRA_RULES,
    NAVAMSHA_RULES,
    NEECHA_BHANGA_RULES,
    OWN_SIGNS,
    PLANET_IN_HOUSE,
    PLANET_IN_SIGN,
    PLANETARY_KARAKATWAS,
    SANYASA_YOGA_RULES,
    SPECIAL_LAGNAS,
    TRANSIT_RULES,
    VIMSHOPAKA_RULES,
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

    # 1. Lagna result
    lagna_sign = lagna.split("(")[0].strip() if "(" in lagna else lagna.strip()
    if lagna_sign in LAGNA_RESULTS:
        rules.append(f"Lagna ({lagna_sign}): {LAGNA_RESULTS[lagna_sign]}")

    # 2. Planet-in-house AND planet-in-sign rules
    for planet, pdata in positions.items():
        if not isinstance(pdata, dict):
            continue
        house = pdata.get("house") or pdata.get("house_number")
        sign  = pdata.get("sign", "")
        if not house:
            continue

        # Planet-in-house
        rule = PLANET_IN_HOUSE.get(planet, {}).get(int(house))
        if rule:
            rules.append(rule)

        # Planet-in-sign
        sign_rule = PLANET_IN_SIGN.get(planet, {}).get(sign)
        if sign_rule:
            rules.append(sign_rule)

        # Dignity rule
        dignity = _planet_dignity(planet, sign)
        if dignity in DIGNITY_RULES and dignity != "neutral":
            rules.append(f"{planet} ({sign}) — {DIGNITY_RULES[dignity]}")

        # Neecha Bhanga if debilitated
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

    # 5. House significations for key houses
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

    # 6. Nakshatra of Moon and Lagna lord
    moon_nakshatra = chart_data.get("moon_nakshatra")
    if moon_nakshatra and moon_nakshatra in NAKSHATRA_RULES:
        nak = NAKSHATRA_RULES[moon_nakshatra]
        rules.append(
            f"Moon nakshatra {moon_nakshatra} (lord: {nak['lord']}, nature: {nak['nature']}): "
            f"deity {nak['deity']}, symbol {nak['symbol']}."
        )

    # 7. Planetary karakattwa for query-relevant planets
    for planet in list(positions.keys())[:3]:
        pk = PLANETARY_KARAKATWAS.get(planet)
        if pk:
            rules.append(f"{planet} karaka: {pk['primary'][:100]}")

    # 8. Graha drishti for key planets
    for planet in ("Saturn", "Jupiter", "Mars"):
        gd = GRAHA_DRISHTI_RULES.get(planet)
        if gd and "special_aspects" in gd:
            sa = ", ".join(str(h) for h in gd["special_aspects"])
            rules.append(f"{planet} special aspects: {sa}th house(s) from its position.")

    # 9. Ashtakavarga reminder
    rules.append(ASHTAKAVARGA_RULES[0])

    return _deduplicate(rules)[:top_k]


def select_dasha_rules(dasha_data: dict[str, Any], domain: str, top_k: int = 6) -> list[str]:
    """Select BPHS rules for Vimshottari Dasha interpretation."""
    rules: list[str] = []

    maha  = dasha_data.get("maha_lord") or dasha_data.get("mahadasha", "")
    antar = dasha_data.get("antar_lord") or dasha_data.get("antardasha", "")

    if maha and maha in DASHA_LORD_RULES:
        rules.append(DASHA_LORD_RULES[maha])

    # Use ANTARDASHA_RULES_FULL (full 9×9 matrix) first, fall back to legacy ANTARDASHA_RULES
    if antar and maha in ANTARDASHA_RULES_FULL:
        sub_full = ANTARDASHA_RULES_FULL[maha].get(antar)
        if sub_full:
            fav = "; ".join(sub_full.get("favorable", [])[:2])
            unfav = "; ".join(sub_full.get("unfavorable", [])[:1])
            rules.append(f"{maha}-{antar} antardasha (favorable): {fav}")
            if unfav:
                rules.append(f"{maha}-{antar} antardasha (challenges): {unfav}")
    elif antar and maha in ANTARDASHA_RULES:
        sub = ANTARDASHA_RULES[maha].get(antar)
        if sub:
            rules.append(f"{maha}-{antar} antardasha: {sub}")

    # House lord dasha effects
    maha_house_lord = dasha_data.get("maha_lord_house_ruled")
    if maha_house_lord and int(maha_house_lord) in DASHA_HOUSE_LORD_EFFECTS:
        eff = DASHA_HOUSE_LORD_EFFECTS[int(maha_house_lord)]
        fav = "; ".join(eff.get("favorable", [])[:1])
        if fav:
            rules.append(f"Dasha of {maha_house_lord}th lord: {fav}")

    rules.append(
        "The Mahadasha lord's natal house, sign dignity, and house rulership determine the flavour of the dasha period. "
        "If the Mahadasha lord rules a kendra or trikona and is strong, the period is beneficial; if it rules a trik house (6,8,12) or is weak, challenges arise."
    )
    rules.append(
        "The Antardasha lord modifies the Mahadasha's theme — a benefic antardasha lord within a difficult mahadasha brings relief; "
        "a malefic antardasha within a beneficial mahadasha brings temporary obstacles."
    )
    # Muhurta timing rules for event prediction
    rules.extend(MUHURTA_RULES[:2])

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


def select_transit_rules(transit_data: dict[str, Any], domain: str, top_k: int = 6) -> list[str]:
    """Select BPHS gochara rules relevant to current transits."""
    rules: list[str] = list(TRANSIT_RULES[:4]) + ASHTAKAVARGA_RULES[:1]

    sade_sati = transit_data.get("sade_sati", False)
    if sade_sati:
        rules.append(
            "Sade Sati is active: Saturn transiting around natal Moon brings a 7.5-year period of pressure, "
            "restructuring, hard lessons, and eventual transformation. Results depend on Saturn's natal strength."
        )

    # Jupiter gochara — full GOCHARA_PLANET_IN_HOUSE lookup
    jup_from_moon = transit_data.get("jupiter_from_moon")
    if isinstance(jup_from_moon, int):
        gochara_rule = GOCHARA_PLANET_IN_HOUSE.get("Jupiter", {}).get(jup_from_moon)
        if gochara_rule:
            rules.append(f"Jupiter from Moon ({jup_from_moon}th): {gochara_rule}")

    # Saturn gochara
    sat_from_moon = transit_data.get("saturn_from_moon")
    if isinstance(sat_from_moon, int):
        gochara_rule = GOCHARA_PLANET_IN_HOUSE.get("Saturn", {}).get(sat_from_moon)
        if gochara_rule:
            rules.append(f"Saturn from Moon ({sat_from_moon}th): {gochara_rule}")

    # Rahu/Ketu gochara
    rahu_from_moon = transit_data.get("rahu_from_moon")
    if isinstance(rahu_from_moon, int):
        gochara_rule = GOCHARA_PLANET_IN_HOUSE.get("Rahu", {}).get(rahu_from_moon)
        if gochara_rule:
            rules.append(f"Rahu from Moon ({rahu_from_moon}th): {gochara_rule}")

    rules.extend(DOMAIN_RULES.get(domain, [])[:2])
    return _deduplicate(rules)[:top_k]


def select_yoga_rules(yoga_data: dict[str, Any], domain: str, top_k: int = 8) -> list[str]:
    """Select BPHS yoga and dosha rules relevant to the chart's active yogas."""
    rules: list[str] = []

    active_yogas  = yoga_data.get("active_yogas",  [])
    active_doshas = yoga_data.get("active_doshas", [])

    # Combined yoga lookup: YOGA_RULES (legacy) + ADDITIONAL_YOGA_RULES (new)
    for yoga in active_yogas[:6]:
        name = yoga if isinstance(yoga, str) else yoga.get("name", "")
        matched = False
        for key, rule in YOGA_RULES.items():
            if key.lower() in name.lower() or name.lower() in key.lower():
                rules.append(f"{key}: {rule}")
                matched = True
                break
        if not matched:
            for key, info in ADDITIONAL_YOGA_RULES.items():
                if key.lower() in name.lower() or name.lower() in key.lower():
                    formation = "; ".join(info.get("formation", [])[:1])
                    effect = "; ".join(info.get("effects", [])[:1])
                    rules.append(f"{key}: {formation} → {effect}")
                    break

        # Nabhasa yogas
        for key, info in NABHASA_YOGA_RULES.items():
            if key.lower() in name.lower() or name.lower() in key.lower():
                effect = info.get("effects", "")[:120]
                rules.append(f"{key} (Nabhasa): {effect}")
                break

    for dosha in active_doshas[:4]:
        name = dosha if isinstance(dosha, str) else dosha.get("name", "")
        name_lower = name.lower()
        if "mangal" in name_lower or "kuja" in name_lower:
            effects = "; ".join(MANGAL_DOSHA_RULES.get("effects", [])[:2])
            rules.append(f"Mangal Dosha: {effects}")
            cancellation = MANGAL_DOSHA_RULES.get("cancellation_conditions", [])
            if cancellation:
                rules.append(f"Mangal Dosha cancellation: {cancellation[0]}")
        elif "kala_sarpa" in name_lower or "kala sarpa" in name_lower:
            effects = "; ".join(KALA_SARPA_YOGA_RULES.get("effects", [])[:2])
            rules.append(f"Kala Sarpa Yoga: {effects}")
        else:
            for key, rule in YOGA_RULES.items():
                if key.lower() in name_lower:
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
    moon_nakshatra = natal_data.get("moon_nakshatra", "")
    return {
        "natal":      select_natal_rules(natal_data,   domain, top_k=10),
        "dasha":      select_dasha_rules(dasha_data,   domain, top_k=8),
        "transit":    select_transit_rules(transit_data, domain, top_k=6),
        "divisional": _divisional_rules(domain),
        "yoga":       select_yoga_rules(yoga_data,     domain, top_k=8),
        "nakshatra":  select_nakshatra_rules(moon_nakshatra, top_k=4),
        "jaimini":    select_jaimini_rules(domain, top_k=3),
    }


def select_nakshatra_rules(nakshatra_name: str, top_k: int = 4) -> list[str]:
    """Return classical rules for a given nakshatra by name."""
    rules: list[str] = []
    nak = NAKSHATRA_RULES.get(nakshatra_name)
    if not nak:
        # fuzzy match on prefix
        for k, v in NAKSHATRA_RULES.items():
            if nakshatra_name.lower() in k.lower():
                nak = v
                break
    if nak:
        rules.append(
            f"{nakshatra_name}: lord {nak['lord']}, sign {nak['sign']}, "
            f"nature {nak['nature']}, deity {nak['deity']}, symbol {nak['symbol']}."
        )
        pk = PLANETARY_KARAKATWAS.get(nak["lord"])
        if pk:
            rules.append(f"{nak['lord']} (nakshatra lord) governs: {pk['primary'][:120]}")
    return rules[:top_k]


def select_jaimini_rules(domain: str, top_k: int = 3) -> list[str]:
    """Return relevant Jaimini sutras for the given domain."""
    rules: list[str] = []
    domain_map = {
        "marriage":    "Karakamsha",
        "career":      "Rashi_Dasha",
        "spirituality": "Chara_Karakas",
        "general":     "Aspects",
    }
    section = domain_map.get(domain, "Aspects")
    rules.extend(JAIMINI_RULES.get(section, [])[:top_k])
    if not rules:
        rules.extend(JAIMINI_RULES.get("Chara_Karakas", [])[:top_k])
    return rules


def _divisional_rules(domain: str) -> list[str]:
    base = list(NAVAMSHA_RULES[:4]) + [
        f"Special Lagnas — {k}: {v[:120]}…" for k, v in list(SPECIAL_LAGNAS.items())[:2]
    ] + VIMSHOPAKA_RULES[:1]
    if domain in ("career", "social_standing"):
        base.append("The Dashamsha (D10) chart governs career specifics — the D10 lagna lord and 10th lord reveal professional strength.")
    if domain == "wealth":
        base.append("The Hora chart (D2) determines wealth — Sun's Hora gives political/father wealth; Moon's Hora gives maternal/business wealth.")
    if domain == "marriage":
        base.append(SPECIAL_LAGNAS.get("Upapada Lagna (UL)", "")[:200])
    base += [f"Karaka: {k} — {v[:100]}…" for k, v in list(KARAKA_RULES.items())[:2]]
    return _deduplicate(base)[:6]


def _deduplicate(rules: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for r in rules:
        key = r[:60]
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out
