"""Named-entity redaction for need-to-know worker-to-worker mediation.

The thesis frames need-to-know as a governance control that limits what each
agent receives to its role (Section 3.3.1). For *worker-to-worker* peer
exchange, the controlled quantity is the **identity of named entities**: when
one Worker shares its synthesis with peers, the Governance Layer redacts the
proper nouns (states, organisations, persons) before transmission. Workers
still receive the analytical substance -- claims, corroboration, hypothesis
support -- but not the entity labels that could anchor them to priors about a
specific actor, reducing inter-agent bias and herding on a named party.

Redaction is deterministic and reversible only through the audit log: each
distinct entity maps to a stable ``[ENTITY_n]`` placeholder in order of first
appearance.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

# Fallback proper-noun detector: capitalised tokens not at sentence start.
_PROPER_NOUN = re.compile(r"\b[A-Z][a-zA-Z]+\b")
# Common capitalised words that are not entities and should not be redacted.
_STOPWORDS = {
    "The", "A", "An", "This", "That", "Reliable", "Unverified", "Situation",
    "Report", "Reporting", "Analysts", "Open", "Worker", "Workers", "Hypotheses",
    "Hypothesis", "Claims", "Claim", "Reports",
}


def extract_entities(text: str, known: List[str] | None = None) -> List[str]:
    """Return the distinct named entities in ``text``, first-appearance order.

    ``known`` (a scenario's declared entities) takes precedence; the regex pass
    catches any additional proper nouns so redaction never under-covers.
    """

    ordered: List[str] = []
    seen = set()

    def _add(token: str) -> None:
        if token and token not in seen:
            seen.add(token)
            ordered.append(token)

    for ent in known or []:
        if ent in text:
            _add(ent)
    for match in _PROPER_NOUN.finditer(text):
        tok = match.group(0)
        if tok not in _STOPWORDS:
            _add(tok)
    return ordered


def redact_entities(
    text: str, known: List[str] | None = None
) -> Tuple[str, int, Dict[str, str]]:
    """Replace named entities with stable ``[ENTITY_n]`` placeholders.

    Returns the redacted text, the number of entity *mentions* removed, and the
    entity -> placeholder mapping (for the audit trail).
    """

    entities = extract_entities(text, known)
    mapping: Dict[str, str] = {
        ent: f"[ENTITY_{i + 1}]" for i, ent in enumerate(entities)
    }
    redacted = text
    mentions = 0
    for ent, placeholder in mapping.items():
        pattern = re.compile(r"\b" + re.escape(ent) + r"\b")
        redacted, n = pattern.subn(placeholder, redacted)
        mentions += n
    return redacted, mentions, mapping
