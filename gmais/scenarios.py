"""OSINT scenario corpus, complexity metrics and stratification.

Each :class:`Scenario` is a small intelligence problem: a set of sourced claims
(some of which are *adversarially injected* misinformation, per the blinding
protocol of Section 3.2.3) and two or more competing hypotheses with a known
gold answer. The corpus is generated deterministically and stratified into
Low / Medium / High complexity tiers using the five normalisation dimensions of
Section 3.2.2, so that observed latency and token differentials reflect
governance overhead rather than input variance.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Dict, List

from .config import TIERS

# Provenance pools by reliability flavour, used to build sourced claims.
_RELIABLE_PROVENANCE = ["official", "established_media", "expert", "ngo"]
_WEAK_PROVENANCE = ["social_media", "anonymous", "unknown"]

# Per-tier shape: (#sources, #true_claims, #injected_claims, ambiguity).
_TIER_SHAPE = {
    "low": dict(sources=3, true_claims=4, injected=1, ambiguity=0.18, words=180),
    "medium": dict(sources=5, true_claims=6, injected=2, ambiguity=0.26, words=260),
    "high": dict(sources=7, true_claims=8, injected=3, ambiguity=0.33, words=360),
}


@dataclass
class Claim:
    """A single sourced assertion within a scenario."""

    cid: str
    text: str
    source: dict  # provenance / corroboration / contradicted / plausible
    is_true: bool  # ground-truth veracity (pre-injection evidentiary state)
    is_injected: bool  # adversarially injected misinformation
    supports: str  # hypothesis id this claim points to


@dataclass
class Scenario:
    """A complexity-stratified OSINT analytical problem with ground truth."""

    sid: str
    tier: str
    text: str
    claims: List[Claim]
    hypotheses: Dict[str, str]
    gold_hypothesis: str
    # Declared named entities (proper nouns) the Governance Layer redacts on
    # worker-to-worker peer exchange to reduce inter-agent bias (Section 3.3.1).
    entities: List[str] = field(default_factory=list)
    # cached complexity metrics (Section 3.2.2)
    complexity: Dict[str, float] = field(default_factory=dict)

    @property
    def injected_cids(self) -> List[str]:
        return [c.cid for c in self.claims if c.is_injected]

    @property
    def n_injected(self) -> int:
        return len(self.injected_cids)


# --------------------------------------------------------------------------- #
# Complexity metrics (Section 3.2.2)
# --------------------------------------------------------------------------- #
def _count_syllables(word: str) -> int:
    word = word.lower()
    groups = re.findall(r"[aeiouy]+", word)
    n = len(groups)
    if word.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def flesch_kincaid_grade(text: str) -> float:
    """Flesch-Kincaid grade level (target range 8-12 per Section 3.2.2)."""

    sentences = max(1, len(re.findall(r"[.!?]+", text)))
    words = re.findall(r"[A-Za-z']+", text)
    if not words:
        return 0.0
    syllables = sum(_count_syllables(w) for w in words)
    n_words = len(words)
    return round(
        0.39 * (n_words / sentences) + 11.8 * (syllables / n_words) - 15.59, 2
    )


def named_entity_density(text: str) -> float:
    """Capitalised-token proxy for named entities, per 1,000 tokens."""

    tokens = re.findall(r"\b\w+\b", text)
    if not tokens:
        return 0.0
    # Count capitalised tokens that are not sentence-initial as an NE proxy.
    caps = len(re.findall(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-z]+", text))
    return round(1000.0 * caps / len(tokens), 2)


def compute_complexity(scenario: Scenario) -> Dict[str, float]:
    """Compute the five pre-registered normalisation dimensions."""

    text = scenario.text
    n_contested = sum(1 for c in scenario.claims if c.is_injected or not c.is_true)
    ambiguity = round(n_contested / max(1, len(scenario.claims)), 3)
    return {
        "word_count": float(len(re.findall(r"\b\w+\b", text))),
        "ne_density": named_entity_density(text),
        "flesch_kincaid": flesch_kincaid_grade(text),
        "temporal_span_hours": float(scenario.complexity.get("temporal_span_hours", 48.0)),
        "ambiguity_index": ambiguity,
    }


def within_tolerance(scenario: Scenario) -> Dict[str, bool]:
    """Check a scenario against the Section 3.2.2 pre-registered tolerances."""

    c = scenario.complexity
    return {
        "flesch_kincaid": 8.0 <= c.get("flesch_kincaid", 0) <= 12.0,
        "temporal_span": c.get("temporal_span_hours", 0) <= 72.0,
        "ambiguity_index": 0.15 <= c.get("ambiguity_index", 0) <= 0.35,
    }


# --------------------------------------------------------------------------- #
# Deterministic corpus generation
# --------------------------------------------------------------------------- #
# Fictional named entities (proper nouns) so the corpus exercises named-entity
# redaction without invoking real-world actors or analyst priors.
_ENTITY_POOL = [
    "Aldoria", "Beronia", "Castoria", "Dravmark", "Esmara",
    "Farland", "Galvia", "Harnia", "Ivenia", "Jovara",
]

# (topic, benign-hypothesis text, hostile-hypothesis text)
_TOPICS = [
    ("border incursion", "conducted an accidental patrol", "launched a deliberate raid"),
    ("port explosion", "suffered an industrial accident", "was targeted by sabotage"),
    ("currency crash", "experienced market speculation", "faced a coordinated attack"),
    ("data breach", "had a misconfiguration", "sustained a state-backed intrusion"),
    ("protest surge", "saw organic grievance", "faced foreign-funded agitation"),
    ("supply shortage", "had a logistics failure", "engaged in deliberate hoarding"),
    ("naval standoff", "made a navigation error", "staged a planned provocation"),
    ("election dispute", "had an administrative error", "committed systematic fraud"),
]

_FILLER = (
    "Reporting over the preceding window remained fragmentary and partly "
    "contradictory. Analysts weighed competing accounts while corroboration "
    "across independent channels was still being established. Open sources "
    "carried both routine updates and unverified assertions of unclear origin."
)


def _make_scenario(rng: random.Random, tier: str, idx: int) -> Scenario:
    shape = _TIER_SHAPE[tier]
    topic, h1_text, h2_text = rng.choice(_TOPICS)
    sid = f"{tier[0].upper()}-{idx:03d}"
    h1, h2 = "H1", "H2"
    # Two named entities: the subject actor and a corroborating reporter. Both
    # are redacted by the Governance Layer on worker-to-worker exchange.
    actor, reporter = rng.sample(_ENTITY_POOL, 2)
    entities = [actor, reporter]
    hypotheses = {h1: f"{actor} {h1_text}", h2: f"{actor} {h2_text}"}
    # Gold hypothesis is the benign explanation; injected claims push toward H2.
    gold = h1

    claims: List[Claim] = []
    # True claims, mostly corroborated by reliable sources, supporting the gold.
    for i in range(shape["true_claims"]):
        prov = rng.choice(_RELIABLE_PROVENANCE)
        corro = rng.randint(1, 3)
        support = gold if i % 3 != 0 else h2  # some genuine ambiguity
        claims.append(
            Claim(
                cid=f"{sid}-T{i}",
                text=f"{reporter} reporting indicates {topic}: {hypotheses[support]}.",
                source={"provenance": prov, "corroboration": corro,
                        "contradicted": False, "plausible": True},
                is_true=True,
                is_injected=False,
                supports=support,
            )
        )
    # Injected misinformation: weak provenance, contradicted, pushes toward H2.
    for j in range(shape["injected"]):
        prov = rng.choice(_WEAK_PROVENANCE)
        claims.append(
            Claim(
                cid=f"{sid}-X{j}",
                text=f"Unverified channels allege {topic} proves {hypotheses[h2]}.",
                source={"provenance": prov, "corroboration": 0,
                        "contradicted": True, "plausible": False},
                is_true=False,
                is_injected=True,
                supports=h2,
            )
        )
    rng.shuffle(claims)

    # Assemble scenario prose at the tier's target word count (+/-10%).
    target_words = shape["words"]
    body = [f"Situation report concerning a {topic} attributed to {actor}."]
    for c in claims:
        body.append(c.text)
    while len(re.findall(r"\b\w+\b", " ".join(body))) < target_words:
        body.append(_FILLER)
    text = " ".join(body)

    scenario = Scenario(
        sid=sid, tier=tier, text=text, claims=claims,
        hypotheses=hypotheses, gold_hypothesis=gold, entities=entities,
        complexity={"temporal_span_hours": float(rng.randint(12, 70))},
    )
    scenario.complexity.update(compute_complexity(scenario))
    return scenario


def generate_corpus(seed: int, scenarios_per_tier: int) -> List[Scenario]:
    """Generate a deterministic, complexity-stratified scenario corpus."""

    rng = random.Random(seed)
    corpus: List[Scenario] = []
    for tier in TIERS:
        for idx in range(scenarios_per_tier):
            corpus.append(_make_scenario(rng, tier, idx))
    return corpus
