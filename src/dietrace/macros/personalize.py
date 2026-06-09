"""Gemini-personalised macro plan with physiological safety bounds.

``personalize_plan(profile, base_targets, client=None) -> MacroPlan`` asks Gemini
for small adjustments to the formula-derived macro split, enforces physiological
bounds, and maintains Atwater consistency.

Mirrors ``parse_meal.py``: injected ``google.genai`` client, structured output via
``response_schema`` + ``response_mime_type="application/json"``, fail-soft on every
error axis — empty text, bad JSON, missing fields, client exception — returns the
base targets unchanged with a templated rationale rather than raising.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from dietrace.llm.config import GEMINI_MODEL
from dietrace.macros.models import MacroPlan, MacroProfile

# USDA nutrient number codes — same codes used across the whole stack.
_ENERGY = "208"
_PROTEIN = "203"
_FAT = "204"
_CARB = "205"

# Standard Atwater energy factors (kcal per gram).
_ATWATER_P = 4.0
_ATWATER_C = 4.0
_ATWATER_F = 9.0

# Physiological protein bounds (g per kg body weight).
_PROTEIN_MIN_PER_KG = 1.2
_PROTEIN_MAX_PER_KG = 2.4

# Fat bounds as a fraction of total kcal.
_FAT_MIN_FRAC = 0.15
_FAT_MAX_FRAC = 0.40

# Atwater drift tolerance (kcal) — pre-existing drift beyond this is recorded.
_DRIFT_TOLERANCE = 5.0


class _PersonalizeDelta(BaseModel):
    """Gemini structured-output response: small adjustments to the macro percentage split.

    Deltas are in percentage points of total kcal (e.g. ``protein_pct_delta=+2``
    means protein's share grows by 2% of kcal). The caller clamps the resulting
    grams to physiological bounds; carbohydrate is always derived from the
    remainder so Atwater consistency is guaranteed.
    """

    rationale: str
    # Reject non-finite deltas (json.loads admits the bare ``NaN``/``Infinity``
    # tokens a model can emit): a garbled delta would otherwise reach the
    # ``max(-10, min(10, x))`` clamp where a NaN coerces to the +10 pp bound,
    # silently applying a real, large macro shift. Failing validation here routes
    # it to the module's fail-soft-to-formula path instead (mirrors evals/schema.py).
    protein_pct_delta: float = Field(default=0.0, allow_inf_nan=False)
    fat_pct_delta: float = Field(default=0.0, allow_inf_nan=False)


def _clamp(value: float, lo: float, hi: float) -> tuple[float, bool]:
    """Return (clamped_value, was_clamped)."""
    if value < lo:
        return lo, True
    if value > hi:
        return hi, True
    return value, False


def _strip_fences(text: str) -> str:
    """Drop a surrounding markdown code fence if present (mirrors parse_meal.py)."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _build_prompt(profile: MacroProfile, base_targets: dict[str, float]) -> str:
    kcal = base_targets.get(_ENERGY, 0.0)
    protein_g = base_targets.get(_PROTEIN, 0.0)
    fat_g = base_targets.get(_FAT, 0.0)
    carb_g = base_targets.get(_CARB, 0.0)
    pref = f", preferences: {profile.preference}" if profile.preference else ""
    return (
        f"You are a registered dietitian assistant. Given a person's profile and "
        f"their formula-derived macro targets, suggest small adjustments to better "
        f"suit their individual characteristics. "
        f"Profile: age {profile.age}, sex {profile.sex}, "
        f"weight {profile.weight_kg}kg, height {profile.height_cm}cm, "
        f"activity {profile.activity}, goal {profile.goal}{pref}. "
        f"Formula targets: {kcal:.0f}kcal, protein {protein_g:.1f}g, "
        f"fat {fat_g:.1f}g, carb {carb_g:.1f}g. "
        f"Return protein_pct_delta and fat_pct_delta in percentage points "
        f"(range [-10, 10]). Carbohydrate is derived from the remainder. "
        f"Calories stay fixed."
    )


def _structured_config() -> Any:
    """Build the structured-output config — lazy import so module stays credential-free."""
    from google import genai

    return genai.types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=_PersonalizeDelta,
    )


def _default_client() -> Any:
    """Build a Vertex Gemini client — lazy so imports stay cheap."""
    from google import genai

    from dietrace.llm.config import GEMINI_LOCATION, GEMINI_PROJECT

    return genai.Client(vertexai=True, project=GEMINI_PROJECT, location=GEMINI_LOCATION)


def _fallback_rationale(profile: MacroProfile) -> str:
    return (
        f"Personalisation unavailable; using formula targets for a "
        f"{profile.age}-year-old {profile.sex} "
        f"({profile.activity} activity, {profile.goal} goal)."
    )


def personalize_plan(
    profile: MacroProfile,
    base_targets: dict[str, float],
    client: Any | None = None,
) -> MacroPlan:
    """Personalise *base_targets* via Gemini with physiological safety bounds.

    Calls Gemini for ``{rationale, protein_pct_delta, fat_pct_delta}`` deltas
    (percentage-point shifts, bounded in [-10, 10]). Applies them, then:

    * clamps protein to [1.2, 2.4] g/kg body weight
    * clamps fat to [0.15, 0.40] of kcal
    * derives carbohydrate from the remainder so 4P + 4C + 9F = kcal exactly
    * detects pre-existing Atwater drift in *base_targets* beyond tolerance

    Every override is recorded in ``MacroPlan.clamped``. Calories ("208") are
    never changed — they are the deterministic Mifflin–St Jeor / preset number.

    On any failure falls back to *base_targets* unchanged with ``source="formula"``
    and a templated rationale.
    """
    if client is None:
        try:
            client = _default_client()
        except Exception:
            return MacroPlan(
                targets=dict(base_targets),
                rationale=_fallback_rationale(profile),
                source="formula",
                steps=[],
                clamped=[],
            )

    kcal = base_targets.get(_ENERGY, 0.0)
    base_protein_g = base_targets.get(_PROTEIN, 0.0)
    base_fat_g = base_targets.get(_FAT, 0.0)
    base_carb_g = base_targets.get(_CARB, 0.0)

    clamped: list[str] = []

    # Detect pre-existing Atwater drift in the base targets.
    if kcal > 0:
        base_atwater = (
            _ATWATER_P * base_protein_g
            + _ATWATER_C * base_carb_g
            + _ATWATER_F * base_fat_g
        )
        if abs(base_atwater - kcal) > _DRIFT_TOLERANCE:
            clamped.append("drift")

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=_build_prompt(profile, base_targets),
            config=_structured_config(),
        )
        raw_text = getattr(response, "text", None)
        if not raw_text:
            raise ValueError("empty Gemini response")

        payload = json.loads(_strip_fences(raw_text))
        delta = _PersonalizeDelta.model_validate(payload)

        # Clamp deltas to [-10, 10] defensively (schema should enforce, but guard anyway).
        protein_pct_delta = max(-10.0, min(10.0, delta.protein_pct_delta))
        fat_pct_delta = max(-10.0, min(10.0, delta.fat_pct_delta))
        rationale = delta.rationale or ""

    except Exception:
        return MacroPlan(
            targets=dict(base_targets),
            rationale=_fallback_rationale(profile),
            source="formula",
            steps=[],
            clamped=clamped,
        )

    # Apply percentage-point deltas to the base split.
    base_protein_pct = (base_protein_g * _ATWATER_P / kcal) if kcal > 0 else 0.0
    base_fat_pct = (base_fat_g * _ATWATER_F / kcal) if kcal > 0 else 0.0

    new_protein_pct = base_protein_pct + protein_pct_delta / 100.0
    new_fat_pct = base_fat_pct + fat_pct_delta / 100.0

    protein_g_raw = (kcal * new_protein_pct / _ATWATER_P) if kcal > 0 else 0.0
    fat_g_raw = (kcal * new_fat_pct / _ATWATER_F) if kcal > 0 else 0.0

    # Clamp protein to [1.2, 2.4] g/kg body weight.
    protein_lo = profile.weight_kg * _PROTEIN_MIN_PER_KG
    protein_hi = profile.weight_kg * _PROTEIN_MAX_PER_KG
    protein_g, prot_clamped = _clamp(protein_g_raw, protein_lo, protein_hi)
    if prot_clamped:
        clamped.append("protein")

    # Clamp fat to [0.15, 0.40] of kcal.
    fat_lo = kcal * _FAT_MIN_FRAC / _ATWATER_F
    fat_hi = kcal * _FAT_MAX_FRAC / _ATWATER_F
    fat_g, fat_clamped = _clamp(fat_g_raw, fat_lo, fat_hi)
    if fat_clamped:
        clamped.append("fat")

    # Derive carbohydrate from the remainder (guarantees 4P + 4C + 9F = kcal).
    carb_kcal = kcal - protein_g * _ATWATER_P - fat_g * _ATWATER_F
    if carb_kcal < 0:
        # Protein + fat together exceed kcal; reduce fat until carb is non-negative.
        fat_g = max(0.0, (kcal - protein_g * _ATWATER_P) / _ATWATER_F)
        if "fat" not in clamped:
            clamped.append("fat")
        carb_kcal = 0.0

    carb_g = carb_kcal / _ATWATER_C

    return MacroPlan(
        targets={
            _ENERGY: kcal,
            _PROTEIN: round(protein_g, 1),
            _CARB: round(carb_g, 1),
            _FAT: round(fat_g, 1),
        },
        rationale=rationale,
        source="ai",
        steps=[],
        clamped=clamped,
    )
