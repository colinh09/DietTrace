"""Rule-based safety guardrail for free-text nutrition input.

DietTrace logs food in a "supportive, non-preachy" voice, and that
voice has to hold when the input is not an ordinary meal. ``safety_check`` is a
deterministic, keyword/pattern screen — no model call, no network — that catches
a small taxonomy of harmful phrasing and answers with a calm, non-judgmental
message that points toward help rather than shaming the person.

Three categories, checked most-serious first so a single result reflects the
gravest concern:

* ``disordered_eating`` — eating-disorder / dangerous-restriction phrasing
  (purging, pro-ED culture terms, "starve myself", laxatives to lose weight).
* ``extreme_deficit`` — requests to subsist on a dangerously low daily calorie
  target.
* ``allergen_conflict`` — the text both declares an allergy and logs eating the
  very thing the person is allergic to.

The overriding design constraint is **zero false positives on normal logs**: a
guardrail that fires on "two eggs and toast" trains users to ignore it. Patterns
are intentionally narrow (specific phrases, gated keywords) rather than broad.
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict

Category = Literal["disordered_eating", "extreme_deficit", "allergen_conflict"]


class SafetyResult(TypedDict):
    """Outcome of :func:`safety_check`.

    ``flagged`` is True when input matched a concern; ``category`` names which
    one (None when clear); ``message`` is the supportive reply to surface to the
    user (empty string when clear).
    """

    flagged: bool
    category: Category | None
    message: str


# Eating-disorder / dangerous-restriction phrasing. Deliberately specific action
# phrases — bare words like "starving" or "purge" (a recipe step) stay benign.
_DISORDERED_EATING_PATTERNS = (
    r"make\s+myself\s+(throw\s+up|sick|vomit)",
    r"force\s+myself\s+to\s+(throw\s+up|vomit)",
    r"throw\s+up\s+after",
    r"vomit(ing)?\s+after",
    r"binge\s+and\s+purge",
    r"\bthinspo\b",
    r"pro[\s-]?ana\b",
    r"pro[\s-]?mia\b",
    r"starv(e|ing)\s+myself",
    r"laxatives?\s+to\s+(lose|drop|cut)",
)

# "purge"/"purging" is benign in a kitchen ("purge the fridge"), so it only
# counts when it co-occurs with an eating/body-image context in the same input.
_PURGE = re.compile(r"\bpurg(e|es|ing|ed)\b")
_PURGE_CONTEXT = re.compile(
    r"\b(eat|eating|ate|meal|food|weight|calorie|binge|vomit|throw\s+up)"
)

# Extreme-deficit requests: a low daily calorie target framed as a plan/goal.
# Requires an explicit per-day cadence so one-off low days don't trip it. The
# ceiling is inclusive — 800 kcal/day and below is treated as dangerously low.
_DEFICIT_CALORIE_CEILING = 800
_DEFICIT_PATTERN = re.compile(
    r"(\d{2,4})\s*(?:k?cal(?:orie)?s?)\b[^.]*?\b(a\s+day|per\s+day|daily|each\s+day|/\s*day)",
)

# Major food allergens (singular stems). An allergen counts as a conflict only
# when an allergy is declared AND the allergen is also logged as eaten.
_ALLERGENS = (
    "peanut",
    "tree nut",
    "almond",
    "walnut",
    "cashew",
    "pecan",
    "milk",
    "dairy",
    "egg",
    "wheat",
    "gluten",
    "soy",
    "fish",
    "shellfish",
    "shrimp",
    "prawn",
    "crab",
    "lobster",
    "sesame",
)
_ALLERGY_DECLARED = re.compile(r"allerg(y|ic|ies)")
_EATING_VERB = re.compile(r"\b(ate|eat|eating|had|having|have|consumed|munch|devour)")

_MESSAGES: dict[Category, str] = {
    "disordered_eating": (
        "It sounds like food might feel really hard right now, and you deserve "
        "support with that. You're not alone — reaching out to someone you trust "
        "or a professional can help. In the US you can call or text the NEDA "
        "Helpline at 1-800-931-2237."
    ),
    "extreme_deficit": (
        "Eating that little each day can be tough on your body and is hard to "
        "sustain. A registered dietitian can help you find a target that meets "
        "your goals while keeping you well — you don't have to figure it out alone."
    ),
    "allergen_conflict": (
        "Heads up — this looks like it may include something you've mentioned "
        "you're allergic to. It's worth double-checking the ingredients, and "
        "please seek care right away if you notice any reaction."
    ),
}

_SAFE: SafetyResult = {"flagged": False, "category": None, "message": ""}


def _flag(category: Category) -> SafetyResult:
    return {"flagged": True, "category": category, "message": _MESSAGES[category]}


def _has_disordered_eating(text: str) -> bool:
    if any(re.search(pattern, text) for pattern in _DISORDERED_EATING_PATTERNS):
        return True
    return bool(_PURGE.search(text) and _PURGE_CONTEXT.search(text))


def _has_extreme_deficit(text: str) -> bool:
    for match in _DEFICIT_PATTERN.finditer(text):
        if int(match.group(1)) <= _DEFICIT_CALORIE_CEILING:
            return True
    return False


def _has_allergen_conflict(text: str) -> bool:
    if not _ALLERGY_DECLARED.search(text) or not _EATING_VERB.search(text):
        return False
    # A genuine conflict repeats the allergen: once declaring it, once eating it.
    for allergen in _ALLERGENS:
        stem = re.escape(allergen)
        # Exclude matches immediately followed by "-free" or " free" (e.g.
        # "egg-free", "gluten free") — safe compound product names, not the
        # allergen itself, and would otherwise produce false positives.
        if len(re.findall(rf"\b{stem}s?(?![\s-]free)\b", text)) >= 2:
            return True
    return False


def safety_check(text: str) -> SafetyResult:
    """Screen *text* for harmful phrasing, most-serious category first.

    Returns a :class:`SafetyResult`. When nothing matches — the common case for
    ordinary meal logs — the result is the all-clear ``{"flagged": False,
    "category": None, "message": ""}``. Matching is case-insensitive and purely
    rule-based, so it is deterministic and never makes a network call.
    """
    lowered = text.lower()

    if _has_disordered_eating(lowered):
        return _flag("disordered_eating")
    if _has_extreme_deficit(lowered):
        return _flag("extreme_deficit")
    if _has_allergen_conflict(lowered):
        return _flag("allergen_conflict")

    return dict(_SAFE)  # fresh copy so callers can't mutate the shared constant
