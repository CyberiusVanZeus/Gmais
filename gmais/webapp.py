"""Flask web interface for GMAIS.

A lightweight UI for exploring the artefact: pick a complexity tier, run a
generated OSINT scenario through all four factorial cells, and see the
Security-Tax contrast alongside the validator's Admiralty grading, ACH outcome,
governance redactions and audit-chain attestation. This is a demonstration
surface over the same orchestrator the ablation drives -- it is not a
replacement for the pre-registered 540-observation campaign.
"""

from __future__ import annotations

import os
from dataclasses import asdict

from flask import Flask, render_template, request

# Templates live in the repository-root templates/ directory (shared with the
# legacy interface), not inside the package.
_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")

from .config import CELLS, GMAISConfig
from .gtkg import GroundTruthKnowledgeGraph
from .llm import build_backend
from .orchestrator import GMAISOrchestrator
from .scenarios import generate_corpus


def create_app(config: GMAISConfig | None = None) -> Flask:
    config = config or GMAISConfig(scenarios_per_tier=5)
    app = Flask(__name__, template_folder=_TEMPLATE_DIR)

    corpus = generate_corpus(config.seed, config.scenarios_per_tier)
    backend = build_backend(config.backend, seed=config.seed, model=config.model)
    orchestrator = GMAISOrchestrator(backend, config)

    @app.route("/", methods=["GET", "POST"])
    def index():
        sid = request.form.get("sid") or (corpus[0].sid if corpus else None)
        scenario = next((s for s in corpus if s.sid == sid), corpus[0])

        rows = []
        gtkg = GroundTruthKnowledgeGraph(":memory:")
        gtkg.load_corpus([scenario])
        for cell in CELLS:
            res = orchestrator.analyze(scenario, cell)
            gov = asdict(res.governance) if res.governance else None
            if gov:
                gov.pop("redacted_messages", None)
            rows.append({
                "cell": cell.name,
                "validation": cell.validation,
                "governance": cell.governance,
                "predicted": res.predicted_hypothesis,
                "correct": res.correct,
                "detected": res.detected_injection_cids,
                "confidence": res.confidence,
                "latency_ms": res.latency_ms,
                "tokens": res.tokens,
                "audit_intact": None if gov is None else gov["audit_intact"],
                "events": None if gov is None else gov["events_total"],
                "redacted": None if gov is None else gov["events_redacted"],
            })

        baseline = next(r for r in rows if r["cell"] == "Baseline")
        for r in rows:
            r["delta_latency"] = round(r["latency_ms"] - baseline["latency_ms"], 1)
            r["delta_tokens"] = r["tokens"] - baseline["tokens"]
        gtkg.close()

        return render_template(
            "gmais.html",
            scenarios=corpus,
            scenario=scenario,
            rows=rows,
            gold=scenario.gold_hypothesis,
            injected=scenario.injected_cids,
        )

    return app


app = create_app()

if __name__ == "__main__":  # pragma: no cover
    app.run(host="0.0.0.0", port=5000, debug=False)
