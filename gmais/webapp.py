"""Flask web interface for GMAIS.

Features exposed by this interface:

* a manual **number-of-runs** input the operator submits to launch a run (each
  run is one scenario taken through all four factorial cells);
* **multi-provider** LLM selection (Claude / OpenAI / local), used round-robin
  with local fallback;
* a Validator **web-search toggle** that corroborates claims against verified
  government/institution sources, plus a textarea for **analyst-supplied
  sources**;
* a live **operational activity feed** over Server-Sent Events showing the
  behind-the-scenes work of every architectural component as it happens; and
* a results view with the **Ground Truth Knowledge Graph** for each scenario, a
  per-cell factorial comparison, and an **academic analytics** description of
  what each cell row means.

The deterministic ``mock`` backend is intentionally *not* offered as a user
option; it is reserved for tests/CI. Real runs use the selected providers and
fall back to a local model.

**Demo mode.** Setting ``GMAIS_DEMO_MODE=1`` forces every run onto the
deterministic offline backend regardless of which providers the form selects,
and surfaces a banner saying so. This exists because the console is otherwise
unsafe to expose: every press of *Activate Run* issues billable API calls, and
a publicly reachable URL is a publicly reachable way to spend someone else's
credit. Demo mode makes the interface demonstrable at zero cost and with no key
present.
"""

from __future__ import annotations

import json
import math
import os
import threading
import uuid
from dataclasses import asdict
from typing import Dict, List, Optional

from flask import Flask, Response, render_template, request

from .admiralty import grade_source
from .activity import ActivityRecorder
from .analytics_text import cell_analytics
from .config import CELLS, GMAISConfig, TIERS
from .llm import USER_PROVIDERS, build_multi_backend
from .metrics import ConfusionMatrix, compute_security_tax
from .orchestrator import GMAISOrchestrator
from .scenarios import generate_corpus
from .web_search import VerifiedSourceSearch, parse_user_sources

# Templates live in the repository-root templates/ directory.
_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")

def demo_mode() -> bool:
    """Is the console pinned to the offline deterministic backend?"""

    return os.getenv("GMAIS_DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "on")


# Per-stream cancel events keyed by stream ID.
_cancel_events: Dict[str, threading.Event] = {}


class _StopRun(Exception):
    """Raised inside the pipeline thread when the user presses Stop."""


def _sample_scenarios(seed: int, n_runs: int, tier: str = "all") -> List:
    """Generate ``n_runs`` scenarios, optionally filtered to a single tier."""
    per_tier = max(1, math.ceil(n_runs / (1 if tier != "all" else len(TIERS))))
    corpus = generate_corpus(seed, per_tier)
    if tier != "all":
        corpus = [s for s in corpus if s.tier == tier]
    else:
        # Interleave low/medium/high so small run counts still span tiers.
        by_tier: Dict[str, List] = {t: [] for t in TIERS}
        for s in corpus:
            by_tier[s.tier].append(s)
        interleaved: List = []
        for i in range(per_tier):
            for t in TIERS:
                if i < len(by_tier[t]):
                    interleaved.append(by_tier[t][i])
        corpus = interleaved
    return corpus[:n_runs]


def _gtkg_claims(scenario) -> List[dict]:
    """Build the GTKG claim rows (with Admiralty grades) for display."""
    rows = []
    for c in scenario.claims:
        grade = grade_source(c.source)
        rows.append({
            "cid": c.cid, "text": c.text,
            "provenance": c.source.get("provenance", "unknown"),
            "corroboration": c.source.get("corroboration", 0),
            "admiralty": grade.code, "confidence": grade.confidence,
            "is_true": c.is_true, "is_injected": c.is_injected, "supports": c.supports,
        })
    return rows


def _build_results(config: GMAISConfig, n_runs: int, providers: List[str],
                   sources_raw: str, use_search: bool, recorder: ActivityRecorder,
                   api_keys: dict | None = None, tier: str = "all",
                   label: str = "",
                   cancel: Optional[threading.Event] = None) -> dict:
    """Execute the runs end-to-end, emitting activity, and assemble results."""

    emit = recorder.emit
    tag = f"[{label}] " if label else ""
    emit("init", f"{tag}Starting {n_runs} run(s) across {len(CELLS)} factorial cells"
         + (f" — tier: {tier}" if tier != "all" else ""))

    # 1. Construct the round-robin multi-provider backend (logs availability).
    if demo_mode():
        # Pinned offline: no provider is contacted and nothing is billed.
        from .llm import build_backend

        emit("init", "DEMO MODE - deterministic offline backend; no API calls, "
             "no cost", status="done", providers=["mock"])
        backend = build_backend("mock", seed=config.seed, model="gmais-demo")
        backend.available_providers = ["mock (demo mode)"]
    else:
        backend = build_multi_backend(providers, seed=config.seed, activity=emit,
                                      api_keys=api_keys or {})
    emit("init", f"Providers active: {', '.join(backend.available_providers)}", status="done",
         providers=backend.available_providers)

    # 2. Build the Validator's verified-source search client (+ analyst sources).
    user_hits = parse_user_sources(sources_raw)
    web_search = None
    if use_search or user_hits:
        web_search = VerifiedSourceSearch(user_hits)
        emit("init", f"Validator web search enabled - {web_search.n_verified_user_sources} "
             f"verified analyst source(s) supplied", status="done")

    orchestrator = GMAISOrchestrator(backend, config)
    scenarios = _sample_scenarios(config.seed, n_runs, tier)

    # 3. Run each scenario through all four cells, collecting observations.
    per_scenario: List[dict] = []
    observations: List[dict] = []          # for Security-Tax z-scoring
    cell_acc: Dict[str, ConfusionMatrix] = {c.name: ConfusionMatrix() for c in CELLS}
    cell_hits: Dict[str, List[int]] = {c.name: [] for c in CELLS}
    cell_lat: Dict[str, List[float]] = {c.name: [] for c in CELLS}
    cell_tok: Dict[str, List[int]] = {c.name: [] for c in CELLS}
    cell_bias: Dict[str, List[int]] = {c.name: [] for c in CELLS}

    for scenario in scenarios:
        if cancel and cancel.is_set():
            emit("stop", "Run stopped by user", status="warn")
            raise _StopRun()
        emit("run", f"=== Run for scenario {scenario.sid} ({scenario.tier} tier) ===")
        rows = []
        results_by_cell = {}
        for cell in CELLS:
            if cancel and cancel.is_set():
                emit("stop", "Run stopped by user", status="warn")
                raise _StopRun()
            res = orchestrator.analyze(scenario, cell, activity=emit, web_search=web_search)
            results_by_cell[cell.name] = res
            gov = asdict(res.governance) if res.governance else None
            if gov:
                gov.pop("redacted_messages", None)
            rows.append({
                "cell": cell.name, "validation": cell.validation, "governance": cell.governance,
                "predicted": res.predicted_hypothesis, "correct": res.correct,
                "detected": res.detected_injection_cids, "confidence": res.confidence,
                "latency_ms": res.latency_ms, "tokens": res.tokens,
                "audit_intact": None if gov is None else gov["audit_intact"],
                "events": None if gov is None else gov["events_total"],
                "redacted": None if gov is None else gov["events_redacted"],
                "peer_events": None if gov is None else gov["peer_events"],
                "entities_redacted": res.entities_redacted,
                "bias_exposure": res.peer_bias_exposure,
                "corroboration": res.verified_corroboration,
            })
            observations.append({"scenario_id": scenario.sid, "tier": scenario.tier,
                                 "cell": cell.name, "latency_ms": res.latency_ms,
                                 "tokens": res.tokens})
            # Accumulate aggregate metrics.
            for cid in (c.cid for c in scenario.claims):
                cell_acc[cell.name].add(cid in set(res.detected_injection_cids),
                                        cid in set(res.gold_injection_cids))
            cell_hits[cell.name].append(int(res.correct))
            cell_lat[cell.name].append(res.latency_ms)
            cell_tok[cell.name].append(res.tokens)
            cell_bias[cell.name].append(res.peer_bias_exposure)

        # Per-scenario differentials versus that scenario's Baseline.
        base = next(r for r in rows if r["cell"] == "Baseline")
        for r in rows:
            r["delta_latency"] = round(r["latency_ms"] - base["latency_ms"], 1)
            r["delta_tokens"] = r["tokens"] - base["tokens"]
            r["analytics"] = cell_analytics(r["cell"], r, base)
        per_scenario.append({
            "sid": scenario.sid, "tier": scenario.tier,
            "gold": scenario.gold_hypothesis, "injected": scenario.injected_cids,
            "entities": scenario.entities, "hypotheses": scenario.hypotheses,
            "text": scenario.text, "gtkg_claims": _gtkg_claims(scenario), "rows": rows,
        })

    # 4. Aggregate per-cell summary across all runs (+ Security Tax).
    emit("analyse", "Computing aggregate metrics and Security-Tax distribution")
    st_results = compute_security_tax(
        observations, alpha=config.st_alpha, beta=config.st_beta,
        band_low=config.st_band_low, band_high=config.st_band_high,
    )
    st_by_cell: Dict[str, List[float]] = {c.name: [] for c in CELLS}
    for st in st_results:
        st_by_cell[st.cell].append(st.security_tax)

    def _mean(xs):
        return round(sum(xs) / len(xs), 3) if xs else 0.0

    base_lat = _mean(cell_lat["Baseline"])
    base_tok = _mean(cell_tok["Baseline"])
    aggregate = []
    for c in CELLS:
        name = c.name
        agg = {
            "cell": name, "validation": c.validation, "governance": c.governance,
            "n": len(cell_hits[name]),
            "correct": _mean(cell_hits[name]),                 # accuracy rate
            "detection_f1": round(cell_acc[name].f1, 3),
            "latency_ms": _mean(cell_lat[name]),
            "tokens": _mean(cell_tok[name]),
            "delta_latency": round(_mean(cell_lat[name]) - base_lat, 1),
            "delta_tokens": round(_mean(cell_tok[name]) - base_tok, 1),
            "bias_exposure": _mean(cell_bias[name]),
            "security_tax": _mean(st_by_cell[name]),
        }
        agg["analytics"] = cell_analytics(name, agg, {"delta_latency": 0, "delta_tokens": 0})
        aggregate.append(agg)

    emit("done", "Run complete - rendering results", status="done")

    # 5. Render the results fragment (within app context, in the worker thread).
    html = render_template("_results.html", aggregate=aggregate, per_scenario=per_scenario,
                           n_runs=n_runs, providers=backend.available_providers,
                           web_search=web_search is not None, label=label, tier=tier)
    return {"html": html}


def create_app(config: GMAISConfig | None = None) -> Flask:
    """Application factory."""
    config = config or GMAISConfig()
    app = Flask(__name__, template_folder=_TEMPLATE_DIR)

    @app.route("/")
    def index():
        return render_template("gmais.html", providers=USER_PROVIDERS,
                               demo_mode=demo_mode())

    @app.route("/stop")
    def stop():
        sid = request.args.get("sid", "")
        ev = _cancel_events.get(sid)
        if ev:
            ev.set()
        return "", 204

    @app.route("/stream")
    def stream():
        # Parse the operator's run configuration from the query string.
        try:
            n_runs = max(1, min(540, int(request.args.get("runs", "3"))))
        except ValueError:
            n_runs = 3
        providers = [p for p in request.args.get("providers", "local").split(",") if p in USER_PROVIDERS]
        if not providers:
            providers = ["local"]
        sources_raw = request.args.get("sources", "")
        use_search = request.args.get("websearch", "0") == "1"
        tier = request.args.get("tier", "all")
        if tier not in ("all", "low", "medium", "high"):
            tier = "all"
        api_keys = {
            k: v for k, v in {
                "openai": request.args.get("openai_key", "").strip(),
                "claude": request.args.get("claude_key", "").strip(),
                "local_url": request.args.get("local_url", "").strip(),
            }.items() if v
        }

        # Build the list of pipeline runs:
        # - one run per individual provider (so user can compare)
        # - if multiple providers selected, one combined round-robin run too
        runs_plan: List[dict] = []
        for p in providers:
            runs_plan.append({"providers": [p], "label": p.capitalize()})
        if len(providers) > 1:
            runs_plan.append({"providers": providers,
                               "label": " + ".join(p.capitalize() for p in providers) + " (round-robin)"})

        stream_id = uuid.uuid4().hex[:10]
        cancel = threading.Event()
        _cancel_events[stream_id] = cancel

        recorder = ActivityRecorder()

        def run_pipeline():
            with app.app_context():
                try:
                    for plan in runs_plan:
                        if cancel.is_set():
                            break
                        result = _build_results(
                            config, n_runs, plan["providers"], sources_raw,
                            use_search, recorder, api_keys=api_keys,
                            tier=tier, label=plan["label"], cancel=cancel,
                        )
                        recorder.push_result(result)
                    recorder.finish({})
                except _StopRun:
                    recorder.finish({})
                except Exception as exc:
                    recorder.fail(f"Run failed: {exc}")
                finally:
                    _cancel_events.pop(stream_id, None)

        threading.Thread(target=run_pipeline, daemon=True).start()

        def generate():
            yield f"event: sid\ndata: {json.dumps({'sid': stream_id})}\n\n"
            yield "retry: 3000\n\n"
            for item in recorder.stream():
                if isinstance(item, tuple) and item[0] == "result":
                    yield f"event: result\ndata: {json.dumps(item[1])}\n\n"
                elif isinstance(item, tuple) and item[0] == "end":
                    pass
                else:
                    yield f"event: activity\ndata: {json.dumps(item.to_dict())}\n\n"
            yield "event: end\ndata: {}\n\n"

        return Response(generate(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


app = create_app(GMAISConfig(scenarios_per_tier=5))

if __name__ == "__main__":  # pragma: no cover
    # threaded=True so the SSE stream and the worker thread run concurrently.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), threaded=True)
