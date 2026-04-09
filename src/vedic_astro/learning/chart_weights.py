"""
chart_weights.py — Per-chart-layer prediction weights.

Each layer of the multi-chart system (D1, D9, Dasha, Transit, Special Lagnas,
Arudha Padas, Jaimini) contributes a weighted prediction. Calibration adjusts
these weights so the model aligns with the user's lived experience.

Weights are normalised to sum=1.0 before use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# Default weights — tuned to classical Parashari emphasis:
#   D1 natal is foundational; D9 is the most-used divisional; Dasha timing
#   is the primary Vimshottari predictor; transit adds current activation.
#   Jaimini and special lagnas are secondary lenses.
_DEFAULTS: dict[str, float] = {
    "d1_natal":       0.20,  # Rasi chart foundational promise
    "d9_navamsha":    0.12,  # Soul/spouse/D9 confirmation
    "d10_dasamsa":    0.08,  # Career/profession specific
    "vimshottari":    0.18,  # Maha/Antar dasha timing
    "transit":        0.12,  # Current Gochara overlay
    "yogas":          0.08,  # Yoga / Dosha net effect
    "special_lagnas": 0.06,  # Hora/Ghati/Bhava lagnas group
    "arudha_padas":   0.06,  # AL, A7, UL, A10 group
    "jaimini":        0.06,  # Chara Karakas + Chara Dasha
    "other_vargas":   0.04,  # D2, D3, D4, D7, D12, D16... group
}


@dataclass
class ChartWeights:
    """
    Configurable weights for each predictive layer.

    All weights are normalised to sum=1.0 on first access via `normalised`.
    Calibration modifies weights in-place via `adjust`.
    """
    weights: dict[str, float] = field(default_factory=lambda: dict(_DEFAULTS))

    # ── Access ────────────────────────────────────────────────────────────────

    def get(self, layer: str) -> float:
        return self.weights.get(layer, 0.0)

    @property
    def normalised(self) -> dict[str, float]:
        total = sum(self.weights.values())
        if total == 0:
            return dict(self.weights)
        return {k: round(v / total, 6) for k, v in self.weights.items()}

    # ── Mutation ──────────────────────────────────────────────────────────────

    def adjust(self, layer: str, delta: float) -> None:
        """
        Adjust a single layer's weight by `delta` and clip to [0.02, 0.50].

        The floor of 0.02 prevents any layer from being completely silenced;
        the ceiling of 0.50 prevents one layer from dominating the reading.
        """
        if layer not in self.weights:
            return
        new = max(0.02, min(0.50, self.weights[layer] + delta))
        self.weights[layer] = round(new, 6)

    def reset(self) -> None:
        self.weights = dict(_DEFAULTS)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, float]:
        return dict(self.weights)

    @classmethod
    def from_dict(cls, d: dict[str, float]) -> "ChartWeights":
        cw = cls()
        for k, v in d.items():
            if k in cw.weights:
                cw.weights[k] = float(v)
        return cw


# ── Domain-specific starting weights ─────────────────────────────────────────

_DOMAIN_OVERRIDES: dict[str, dict[str, float]] = {
    "career": {
        "d10_dasamsa": 0.15,
        "d1_natal":    0.18,
        "arudha_padas": 0.08,   # A10 is career image
    },
    "marriage": {
        "d9_navamsha": 0.20,
        "arudha_padas": 0.10,   # UL / A7 for marriage reality
        "jaimini":     0.09,    # Darakaraka emphasis
    },
    "wealth": {
        "d2_hora":    0.10,
        "arudha_padas": 0.10,   # A2 for visible wealth
        "d1_natal":   0.20,
    },
    "health": {
        "d3_drekkana": 0.10,
        "d30_trimsamsa": 0.08,
        "transit":     0.15,
    },
    "spirituality": {
        "d9_navamsha": 0.16,
        "d20_vimshamsa": 0.10,
        "jaimini":     0.10,
    },
    "children": {
        "d7_saptamsa": 0.14,
        "jaimini":     0.09,    # Putrakaraka emphasis
    },
}


def weights_for_domain(domain: str) -> ChartWeights:
    """
    Return ChartWeights initialised with domain-appropriate starting values.

    Domain overrides are merged with global defaults; non-overridden layers
    keep their default values and everything is re-normalised.
    """
    cw = ChartWeights()
    overrides = _DOMAIN_OVERRIDES.get(domain, {})
    for layer, val in overrides.items():
        # Map domain-specific keys (e.g. "d2_hora") to weight dict keys
        canonical = _canonicalize(layer)
        if canonical in cw.weights:
            cw.weights[canonical] = val
        # If the key is new (e.g. "d2_hora"), add it to the weights dict
        else:
            cw.weights[layer] = val
    return cw


def _canonicalize(key: str) -> str:
    """Map domain override keys to weight dict canonical keys."""
    mapping = {
        "d2_hora":       "other_vargas",
        "d3_drekkana":   "other_vargas",
        "d7_saptamsa":   "other_vargas",
        "d20_vimshamsa": "other_vargas",
        "d30_trimsamsa": "other_vargas",
    }
    return mapping.get(key, key)
