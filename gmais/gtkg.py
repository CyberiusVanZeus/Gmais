"""Ground Truth Knowledge Graph (Section 3.2.1).

The GTKG is the authoritative reference dataset against which all system outputs
are scored. Section 3.2.1 specifies a SQLite store whose schema spans entities,
events, source-reliability classifications and evidentiary claims, built under
clean-room protocols from the pre-injection evidentiary state. This module
materialises that schema, loads a scenario corpus into it, and provides the
graded rubric that moves beyond binary factual matching to the epistemic
dimensions intelligence tradecraft requires (hypothesis correctness, ACH
compliance, uncertainty acknowledgement, source-triangulation density).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional

from .admiralty import grade_source
from .scenarios import Scenario

SCHEMA = """
CREATE TABLE IF NOT EXISTS scenarios (
    sid TEXT PRIMARY KEY,
    tier TEXT NOT NULL,
    gold_hypothesis TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hypotheses (
    sid TEXT NOT NULL,
    hid TEXT NOT NULL,
    description TEXT NOT NULL,
    PRIMARY KEY (sid, hid)
);
CREATE TABLE IF NOT EXISTS sources (
    sid TEXT NOT NULL,
    cid TEXT NOT NULL,
    provenance TEXT NOT NULL,
    reliability TEXT NOT NULL,
    credibility TEXT NOT NULL,
    PRIMARY KEY (sid, cid)
);
CREATE TABLE IF NOT EXISTS claims (
    sid TEXT NOT NULL,
    cid TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    is_true INTEGER NOT NULL,
    is_injected INTEGER NOT NULL,
    supports TEXT NOT NULL
);
"""


@dataclass
class RubricScore:
    """Graded evaluation of one analytical output against the GTKG."""

    factual_accuracy: float  # hypothesis correctness {0, 1}
    ach_compliance: float  # fraction of injected claims correctly rejected
    uncertainty_ack: float  # was a calibrated confidence supplied
    triangulation: float  # source-triangulation density of accepted evidence
    composite: float


class GroundTruthKnowledgeGraph:
    """SQLite-backed authoritative reference store."""

    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def load_corpus(self, corpus: List[Scenario]) -> None:
        cur = self.conn.cursor()
        for s in corpus:
            cur.execute(
                "INSERT OR REPLACE INTO scenarios VALUES (?,?,?,?)",
                (s.sid, s.tier, s.gold_hypothesis, s.text),
            )
            for hid, desc in s.hypotheses.items():
                cur.execute(
                    "INSERT OR REPLACE INTO hypotheses VALUES (?,?,?)", (s.sid, hid, desc)
                )
            for c in s.claims:
                grade = grade_source(c.source)
                cur.execute(
                    "INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?)",
                    (s.sid, c.cid, c.source.get("provenance", "unknown"),
                     grade.reliability, grade.credibility),
                )
                cur.execute(
                    "INSERT OR REPLACE INTO claims VALUES (?,?,?,?,?,?)",
                    (s.sid, c.cid, c.text, int(c.is_true), int(c.is_injected), c.supports),
                )
        self.conn.commit()

    def gold_injected(self, sid: str) -> List[str]:
        cur = self.conn.execute(
            "SELECT cid FROM claims WHERE sid=? AND is_injected=1", (sid,)
        )
        return [r[0] for r in cur.fetchall()]

    def gold_hypothesis(self, sid: str) -> Optional[str]:
        cur = self.conn.execute("SELECT gold_hypothesis FROM scenarios WHERE sid=?", (sid,))
        row = cur.fetchone()
        return row[0] if row else None

    def stats(self) -> Dict[str, int]:
        def count(table: str) -> int:
            return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        return {
            "scenarios": count("scenarios"),
            "hypotheses": count("hypotheses"),
            "sources": count("sources"),
            "claims": count("claims"),
        }

    def score(self, scenario: Scenario, *, predicted_hypothesis: str,
              detected_injection_cids: List[str], accepted_cids: List[str],
              confidence: Optional[float]) -> RubricScore:
        """Grade an output against the GTKG rubric (Section 3.2.1)."""

        gold_inj = set(self.gold_injected(scenario.sid))
        detected = set(detected_injection_cids)

        factual = 1.0 if predicted_hypothesis == scenario.gold_hypothesis else 0.0

        # ACH compliance: fraction of injected claims correctly rejected, minus a
        # penalty for over-rejecting genuine claims (false positives).
        if gold_inj:
            tp = len(gold_inj & detected)
            fp = len(detected - gold_inj)
            ach = max(0.0, (tp - 0.5 * fp) / len(gold_inj))
            ach = min(1.0, ach)
        else:
            ach = 1.0 if not detected else 0.5

        uncertainty = 1.0 if (confidence is not None and 0.0 < confidence < 1.0) else 0.0

        # Triangulation density: accepted claims that are corroborated.
        accepted = set(accepted_cids) or {c.cid for c in scenario.claims}
        corro = [c for c in scenario.claims
                 if c.cid in accepted and c.source.get("corroboration", 0) >= 2]
        triangulation = round(len(corro) / max(1, len(accepted)), 4)

        composite = round(
            0.45 * factual + 0.30 * ach + 0.10 * uncertainty + 0.15 * triangulation, 4
        )
        return RubricScore(
            factual_accuracy=factual,
            ach_compliance=round(ach, 4),
            uncertainty_ack=uncertainty,
            triangulation=triangulation,
            composite=composite,
        )

    def close(self) -> None:
        self.conn.close()
