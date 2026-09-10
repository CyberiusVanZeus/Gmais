"""Reproducible results package for the GMAIS campaign (Section 3.3).

One command turns a seed into everything a reviewer needs to check the claims:

``results/``
    ``observations.csv``        the full observation matrix, one row per (scenario, cell)
    ``security_tax.csv``        per-observation Security Tax, z-components and band
    ``results.json``            per-cell metrics and the complete H1-H4 inference
    ``MANIFEST.json``           seed, config, platform, library versions, SHA-256 of every artefact
    ``REPORT.txt``              the human-readable campaign report
    ``tables/*.md``, ``*.tex``  publication tables in Markdown and LaTeX (booktabs)
    ``figures/*.pdf``, ``*.png`` vector and 300 dpi raster figures

The manifest is the point of the package. It records the campaign seed, every
pre-registered constant, the platform the wall-clock figures were measured on,
and a SHA-256 digest of each output file -- so an independent reproduction can be
compared artefact by artefact rather than eyeballed against printed numbers.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import sys
import time as _time
from dataclasses import asdict
from typing import Dict, List, Optional

from .ablation import AblationResult, run_ablation
from .analysis import build_report
from .config import GMAISConfig
from .hypotheses import align, run_all, test_h4
from .stats import CELL_ORDER, _mean, _median
from .timing import environment_manifest


# --------------------------------------------------------------------------- #
# Table rendering
# --------------------------------------------------------------------------- #
def _fmt(value, spec: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return format(value, spec or ".4f")
    if isinstance(value, int):
        return format(value, spec or ",d") if spec else f"{value:,}"
    return str(value)


class Table:
    """A small table that can render itself as Markdown or LaTeX booktabs."""

    def __init__(self, number: str, caption: str, columns: List[str],
                 align_spec: Optional[str] = None, note: str = "") -> None:
        self.number = number
        self.caption = caption
        self.columns = columns
        self.align = align_spec or ("l" + "r" * (len(columns) - 1))
        self.note = note
        self.rows: List[List[str]] = []

    def add(self, *cells: object) -> None:
        self.rows.append([str(c) for c in cells])

    @staticmethod
    def _md_cell(text: str) -> str:
        """Escape a cell so an embedded pipe cannot split the row.

        Test names such as "H1 | G=0: Baseline -> V-only" carry a literal pipe;
        unescaped, it silently shifts every later column one place left.
        """

        return text.replace("|", "\\|")

    def to_markdown(self) -> str:
        out = [f"**Table {self.number}.** {self.caption}", ""]
        out.append("| " + " | ".join(self._md_cell(c) for c in self.columns) + " |")
        out.append("|" + "|".join(
            (":--" if a == "l" else "--:") for a in self.align) + "|")
        for row in self.rows:
            out.append("| " + " | ".join(self._md_cell(c) for c in row) + " |")
        if self.note:
            out += ["", f"*{self.note}*"]
        return "\n".join(out) + "\n"

    def to_latex(self) -> str:
        def esc(text: str) -> str:
            for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                         ("_", r"\_"), ("#", r"\#"), ("±", r"$\pm$"),
                         ("×", r"$\times$"), ("≥", r"$\geq$"), ("≤", r"$\leq$"),
                         ("α", r"$\alpha$"), ("β", r"$\beta$"), ("Δ", r"$\Delta$"),
                         ("χ²", r"$\chi^2$"), ("—", "---"), ("θ", r"$\theta$")):
                text = text.replace(a, b)
            return text

        lines = [
            r"\begin{table}[htbp]", r"\centering", r"\small",
            f"\\caption{{{esc(self.caption)}}}",
            f"\\label{{tab:gmais-{self.number.replace('.', '-')}}}",
            f"\\begin{{tabular}}{{{self.align}}}", r"\toprule",
            " & ".join(esc(c) for c in self.columns) + r" \\", r"\midrule",
        ]
        lines += [" & ".join(esc(c) for c in row) + r" \\" for row in self.rows]
        lines.append(r"\bottomrule")
        lines.append(r"\end{tabular}")
        if self.note:
            lines.append(rf"\par\vspace{{2pt}}\footnotesize\emph{{{esc(self.note)}}}")
        lines.append(r"\end{table}")
        return "\n".join(lines) + "\n"


def _p(value: Optional[float]) -> str:
    """Format a p-value the way a journal expects."""

    if value is None:
        return "—"
    if value < 1e-4:
        return "< .0001"
    return f"{value:.4f}".lstrip("0")


def build_tables(result: AblationResult, inference: Dict) -> List[Table]:
    """The publication tables, built from the campaign's own numbers."""

    cfg = result.config
    tables: List[Table] = []

    # --- Table 1: corpus and ground truth --------------------------------- #
    corpus = result.corpus_stats
    t1 = Table("1", "Ground-Truth Knowledge Graph and scenario corpus. Every "
               "scenario carries a known gold hypothesis and a known set of "
               "adversarially injected claims; the corpus is generated "
               "deterministically from the campaign seed.",
               ["Complexity tier", "Scenarios", "Claims", "Injected claims",
                "Injection rate"])
    for tier in ("low", "medium", "high"):
        claims = corpus["claims_per_tier"].get(tier, 0)
        injected = corpus["injected_per_tier"].get(tier, 0)
        t1.add(tier.capitalize(), f"{cfg.scenarios_per_tier:,}", f"{claims:,}",
               f"{injected:,}", f"{injected / claims:.3f}" if claims else "—")
    total_claims = sum(corpus["claims_per_tier"].values())
    total_injected = sum(corpus["injected_per_tier"].values())
    t1.add("**Total**", f"**{corpus['scenarios']:,}**", f"**{total_claims:,}**",
           f"**{total_injected:,}**",
           f"**{total_injected / total_claims:.3f}**" if total_claims else "—")
    conformance = corpus.get("tolerance_conformance", {})
    t1.note = ("Pre-registered Section 3.2.2 tolerance conformance — "
               + ", ".join(f"{k.replace('_', ' ')}: {v:.0%}"
                           for k, v in conformance.items()) + ".")
    tables.append(t1)

    # --- Table 2: per-cell performance ------------------------------------ #
    t2 = Table("2", "Per-cell performance across the 2×2 factorial ablation. "
               "Each cell contains one observation per scenario, so the four "
               "columns are matched within scenario.",
               ["Cell", "V", "G", "N", "Accuracy", "Rubric", "Brier",
                "Det. P", "Det. R", "Det. F1"])
    acc = align(result, "correct")
    rubric = align(result, "rubric_composite")
    for cell in CELL_ORDER:
        m = result.per_cell_metrics[cell]
        det = m["detection"]
        v = "1" if cell in ("V-only", "Full") else "0"
        g = "1" if cell in ("G-only", "Full") else "0"
        t2.add(cell, v, g, f"{m['n']:,}", f"{m['hypothesis_accuracy']:.4f}",
               f"{_mean(rubric[cell]):.4f}", f"{m['brier_score']:.4f}",
               f"{det['precision']:.4f}", f"{det['recall']:.4f}",
               f"{det['f1']:.4f}")
    t2.note = ("Detection metrics are claim-level over the whole corpus; accuracy "
               "and Brier are observation-level. Cells without a Validator emit no "
               "detections by construction and a fixed 0.5 confidence.")
    tables.append(t2)

    # --- Table 3: cost ---------------------------------------------------- #
    t3 = Table("3", "Cost per observation. Modelled latency combines the "
               "inference cost model with the deployment governance cost model; "
               "measured governance latency is real elapsed wall-clock time "
               "through the mediation path.",
               ["Cell", "Latency (ms)", "Δ vs baseline", "Tokens",
                "Δ vs baseline", "Measured governance (ms)"])
    lat = align(result, "latency_ms")
    tok = align(result, "tokens")
    gov = align(result, "measured_governance_ms")
    base_lat, base_tok = _mean(lat["Baseline"]), _mean(tok["Baseline"])
    for cell in CELL_ORDER:
        dl = _mean(lat[cell]) - base_lat
        dt = _mean(tok[cell]) - base_tok
        t3.add(cell, f"{_mean(lat[cell]):,.1f}",
               "—" if cell == "Baseline" else f"{dl:+,.1f}  ({dl / base_lat:+.1%})",
               f"{_mean(tok[cell]):,.1f}",
               "—" if cell == "Baseline" else f"{dt:+,.1f}  ({dt / base_tok:+.1%})",
               f"{_mean(gov[cell]):.4f}")
    tables.append(t3)

    # --- Table 4: confirmatory tests -------------------------------------- #
    t4 = Table("4", "Confirmatory tests of H1–H3 with Holm–Bonferroni "
               "adjustment across the six-test family. All tests are paired "
               "within scenario.",
               ["Hypothesis / contrast", "Test", "n", "Statistic", "p",
                "p (Holm)", "Effect size", "Estimate [95% CI]"],
               align_spec="llrrrrrl")
    for key in ("H1", "H2", "H3"):
        for test in inference[key]["tests"]:
            if test.get("p_adjusted") is None:
                continue
            shift = test.get("shift")
            estimate = (f"{shift['estimate']:+,.3f} "
                        f"[{shift['ci_low']:+,.3f}, {shift['ci_high']:+,.3f}]"
                        if shift else "—")
            t4.add(test["name"], test["test"], f"{test['n_pairs']:,}",
                   f"{test['statistic']:,.1f}", _p(test["p_value"]),
                   _p(test["p_adjusted"]),
                   f"{test['effect_name']} = {test['effect_size']:.3f}", estimate)
    t4.note = ("Estimate is the Hodges–Lehmann shift with the exact "
               "distribution-free signed-rank interval read off the Walsh "
               "averages; for McNemar the effect size is the discordant-pair "
               "odds ratio (Haldane–Anscombe corrected). A degenerate interval "
               "indicates a differential that is constant across scenarios by "
               "construction — see the note on the deployment cost model.")
    tables.append(t4)

    # --- Table 5: factorial effects --------------------------------------- #
    t5 = Table("5", "Factorial effect estimates with 95% bootstrap intervals, "
               "resampled over scenarios.",
               ["Hypothesis", "Quantity", "Estimate", "95% CI", "Excludes 0"])
    for key, label in (("H1", "Validation main effect"),
                       ("H2", "Governance main effect"),
                       ("H3", "V × G interaction")):
        for name, interval in inference[key]["intervals"].items():
            excludes = "yes" if (interval["ci_low"] > 0 or interval["ci_high"] < 0) else "no"
            t5.add(key, name.replace("_", " "),
                   f"{interval['estimate']:+,.4f}",
                   f"[{interval['ci_low']:+,.4f}, {interval['ci_high']:+,.4f}]",
                   excludes)
    tables.append(t5)

    # --- Table 6: Security Tax -------------------------------------------- #
    h4 = inference["H4"]
    dist = h4["extras"]["distribution"]
    t6 = Table("6", f"Security-Tax distribution and policy-band assignment "
               f"(α = {cfg.st_alpha:g}, β = {cfg.st_beta:g}; bands at "
               f"{cfg.st_band_low:g} and {cfg.st_band_high:g}).",
               ["Cell", "N", "Mean ST", "Median ST", "SD", "IQR",
                "Range", "Modal band", "% in modal band"])
    for cell in CELL_ORDER:
        d = dist.get(cell)
        if not d:
            continue
        counts = d["band_counts"]
        modal = max(counts, key=lambda b: counts[b])
        share = counts[modal] / d["n"]
        t6.add(cell, f"{d['n']:,}", f"{d['mean']:+.4f}", f"{d['median']:+.4f}",
               f"{d['sd']:.4f}", f"[{d['iqr'][0]:+.3f}, {d['iqr'][1]:+.3f}]",
               f"[{d['min']:+.3f}, {d['max']:+.3f}]",
               modal.replace("-", " "), f"{share:.1%}")
    tables.append(t6)

    # --- Table 7: alpha sensitivity --------------------------------------- #
    sweep = h4["extras"]["alpha_sensitivity"]
    t7 = Table("7", "Robustness of the H4 band assignment to the Security-Tax "
               "weighting. A recommendation that survives the full sweep does "
               "not depend on the pre-registered choice of α.",
               ["α (latency weight)"] + [f"{c} median ST → band" for c in CELL_ORDER])
    for key in sorted(sweep, key=lambda k: float(k.split("=")[1])):
        row = [key.split("=")[1]]
        for cell in CELL_ORDER:
            entry = sweep[key].get(cell)
            row.append(f"{entry['median_st']:+.3f} → {entry['band'].replace('-', ' ')}"
                       if entry else "—")
        t7.add(*row)
    tables.append(t7)

    # --- Table 8: measured governance breakdown --------------------------- #
    per_event = inference["H2"]["extras"].get("measured_per_event_us", {})
    if per_event:
        t8 = Table("8", "Measured wall-clock cost of governance mediation, "
                   "attributed by component. Timed with time.perf_counter_ns "
                   "over every mediated event in the campaign.",
                   ["Component", "Mean µs / event", "% of mediation cost"])
        total = per_event.get("governance_total_us", 0.0) or 1.0
        for label, key in (("Policy evaluation fG(e) + HMAC verify", "policy_eval_us"),
                           ("Audit chain SHA-256 append", "audit_record_us"),
                           ("Named-entity redaction", "redaction_us"),
                           ("Mediation-queue bookkeeping", "queue_us")):
            value = per_event.get(key, 0.0)
            t8.add(label, f"{value:.3f}", f"{value / total:.1%}")
        t8.add("**End-to-end mediation**", f"**{total:.3f}**", "**100.0%**")
        env = result.environment
        t8.note = (f"n = {per_event.get('n_mediated_events', 0):,} mediated events on "
                   f"{env.get('platform', 'the campaign host')}, "
                   f"{env.get('python_implementation', 'CPython')} "
                   f"{env.get('python_version', '')}; measured clock resolution "
                   f"{env.get('clock_resolution_ns', float('nan')):.0f} ns.")
        tables.append(t8)

    # --- Table 9: bias control -------------------------------------------- #
    t9 = Table("9", "Worker-to-worker need-to-know: named-entity redaction and "
               "the anchoring it interrupts.",
               ["Cell", "Entity mentions visible to peers",
                "Entity mentions redacted", "Workers anchored (mean)"])
    for cell in CELL_ORDER:
        m = result.per_cell_metrics[cell]
        exposure = m["mean_peer_bias_exposure"]
        redacted = _mean([o.entities_redacted for o in result.observations
                          if o.cell == cell])
        t9.add(cell, f"{exposure:,.1f}", f"{redacted:,.1f}",
               f"{m['mean_anchored_workers']:.3f}")
    t9.note = ("Anchoring is the pathway through which governance can move "
               "analytical accuracy: masking the actor's name removes the cue an "
               "unvalidating Worker herds on.")
    tables.append(t9)

    return tables


# --------------------------------------------------------------------------- #
# Package assembly
# --------------------------------------------------------------------------- #
def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _library_versions() -> Dict[str, str]:
    versions: Dict[str, str] = {}
    for name in ("numpy", "scipy", "matplotlib"):
        try:
            module = __import__(name)
            versions[name] = getattr(module, "__version__", "unknown")
        except Exception:
            versions[name] = "not installed"
    return versions


def run_campaign(config: GMAISConfig | None = None, *, outdir: str = "results",
                 with_figures: bool = True, verbose: bool = True) -> Dict[str, object]:
    """Run the campaign and write the complete reproducible results package.

    Against a paid backend the ablation is checkpointed row-by-row into
    ``<outdir>/observations_checkpoint.csv`` and API consumption is metered, so
    a run that fails partway leaves both its data and its spend accounted for.
    """

    config = config or GMAISConfig()
    say = (lambda m: print(m, flush=True)) if verbose else (lambda m: None)

    paid = config.backend not in ("mock",)
    from .llm.cost import reset_meter

    meter = reset_meter()

    os.makedirs(outdir, exist_ok=True)
    checkpoint_path = os.path.join(outdir, "observations_checkpoint.csv")

    say(f"[1/6] Running 2×2 factorial ablation "
        f"({config.scenarios_per_tier} scenarios/tier → "
        f"{config.total_observations} observations)"
        + (f" on backend '{config.backend}' [{config.model}]…" if paid else "…"))

    started = _time.time()

    def _progress(done: int, total: int, obs) -> None:
        # Report sparsely: a paid run is long, and a line per observation would
        # bury the cost figure that actually needs watching.
        if not verbose or (done % 20 and done != total):
            return
        elapsed = _time.time() - started
        rate = elapsed / done
        eta = rate * (total - done)
        line = (f"      {done:>4}/{total}  "
                f"({done / total:5.1%})  elapsed {elapsed / 60:5.1f}m  "
                f"eta {eta / 60:5.1f}m")
        if paid:
            cost = meter.cost_usd
            line += (f"  |  {meter.calls:,} calls"
                     + (f"  ${cost:.4f}" if cost is not None else ""))
        say(line)

    result = run_ablation(
        config,
        checkpoint_path=checkpoint_path if paid else None,
        progress=_progress if paid else None,
    )
    if paid:
        say(f"      API consumption: {meter.summary()}")

    say("[2/6] Testing H1–H4 with Holm–Bonferroni across the confirmatory family…")
    inference = run_all(result)

    os.makedirs(outdir, exist_ok=True)
    tables_dir = os.path.join(outdir, "tables")
    figures_dir = os.path.join(outdir, "figures")
    os.makedirs(tables_dir, exist_ok=True)

    # --- Observation matrix ------------------------------------------------ #
    say("[3/6] Writing the observation matrix…")
    obs_path = os.path.join(outdir, "observations.csv")
    rows = result.observation_dicts()
    with open(obs_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    tax_path = os.path.join(outdir, "security_tax.csv")
    tax_rows = [asdict(st) for st in result.security_tax]
    with open(tax_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(tax_rows[0].keys()))
        writer.writeheader()
        writer.writerows(tax_rows)

    # --- Tables ------------------------------------------------------------ #
    say("[4/6] Rendering publication tables (Markdown + LaTeX)…")
    tables = build_tables(result, inference)
    md_parts, tex_parts = [], []
    for table in tables:
        md_parts.append(table.to_markdown())
        tex_parts.append(table.to_latex())
        stem = f"table{table.number}"
        with open(os.path.join(tables_dir, f"{stem}.md"), "w", encoding="utf-8") as fh:
            fh.write(table.to_markdown())
        with open(os.path.join(tables_dir, f"{stem}.tex"), "w", encoding="utf-8") as fh:
            fh.write(table.to_latex())
    with open(os.path.join(tables_dir, "all_tables.md"), "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(md_parts))
    with open(os.path.join(tables_dir, "all_tables.tex"), "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(tex_parts))

    # --- Figures ----------------------------------------------------------- #
    figure_paths: List[str] = []
    if with_figures:
        say("[5/6] Rendering figures (vector PDF + 300 dpi PNG)…")
        try:
            from . import figures as _figures

            figure_paths = _figures.render_all(result, figures_dir)
        except ImportError as exc:  # pragma: no cover - matplotlib optional
            say(f"      matplotlib unavailable ({exc}); skipping figures.")
    else:
        say("[5/6] Figures skipped by request.")

    # --- JSON, report and manifest ----------------------------------------- #
    say("[6/6] Writing results.json, REPORT.txt and MANIFEST.json…")
    results_path = os.path.join(outdir, "results.json")
    with open(results_path, "w", encoding="utf-8") as fh:
        json.dump({
            "config": asdict(config),
            "corpus": result.corpus_stats,
            "noise_model": result.noise_manifest,
            "environment": result.environment,
            "per_cell_metrics": result.per_cell_metrics,
            "api_consumption": meter.as_dict() if paid else None,
            "inference": inference,
        }, fh, indent=2, default=str)

    report_path = os.path.join(outdir, "REPORT.txt")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(build_report(result))
        fh.write("\n\n")
        fh.write(_inference_report(inference))

    artefacts = [obs_path, tax_path, results_path, report_path]
    artefacts += [os.path.join(tables_dir, f) for f in sorted(os.listdir(tables_dir))]
    artefacts += sorted(figure_paths)

    manifest = {
        "campaign": {
            "seed": config.seed,
            "scenarios_per_tier": config.scenarios_per_tier,
            "observations": len(result.observations),
            "cells": [c for c in CELL_ORDER],
            "backend": config.backend,
            "model": config.model,
            "wall_clock_seconds": round(_time.time() - started, 1),
        },
        "api_consumption": meter.as_dict() if paid else None,
        "preregistered_constants": asdict(config),
        "noise_model": result.noise_manifest,
        "environment": {
            **result.environment,
            "executable": sys.executable,
            "platform_machine": platform.machine(),
            "libraries": _library_versions(),
        },
        "reproduce": {
            "command": (f"python -m gmais.cli campaign --per-tier "
                        f"{config.scenarios_per_tier} --seed {config.seed} "
                        f"--out {outdir}"),
            "determinism": ("Identical seed and configuration reproduce the "
                            "observation matrix bit for bit. Measured wall-clock "
                            "columns are hardware-dependent and are expected to "
                            "differ; every other column must match exactly."),
            "hardware_dependent_columns": [
                "measured_latency_ms", "measured_governance_ms", "measured_worker_ms",
                "measured_validator_ms", "measured_policy_ms", "measured_audit_ms",
                "measured_redaction_ms", "measured_queue_ms",
            ],
        },
        "artefacts": {
            os.path.relpath(path, outdir): {
                "sha256": _sha256(path),
                "bytes": os.path.getsize(path),
            }
            for path in artefacts if os.path.exists(path)
        },
    }
    manifest_path = os.path.join(outdir, "MANIFEST.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, default=str)

    if paid:
        say(f"\nAPI consumption: {meter.summary()}")
    say(f"\nResults package written to {os.path.abspath(outdir)}/")
    say(f"  {len(rows)} observations · {len(tables)} tables · "
        f"{len(figure_paths) // 2} figures")
    for key in ("H1", "H2", "H3", "H4"):
        say(f"  {key}: {inference[key]['verdict']}")

    return {
        "result": result,
        "inference": inference,
        "manifest": manifest,
        "outdir": os.path.abspath(outdir),
    }


def _inference_report(inference: Dict) -> str:
    """Human-readable rendering of the H1-H4 inference."""

    lines = ["=" * 78,
             "CONFIRMATORY INFERENCE:  H1-H4",
             "=" * 78,
             f"Observations: {inference['n_observations']}   "
             f"Scenarios: {inference['n_scenarios']}   "
             f"Confirmatory family: {inference['confirmatory_family_size']} tests   "
             f"Correction: {inference['multiplicity_correction']}",
             ""]

    for key in ("H1", "H2", "H3", "H4"):
        h = inference[key]
        lines.append(f"{key}  [{h['verdict']}]")
        lines.append("-" * 78)
        for chunk in _wrap(h["statement"], 74):
            lines.append(f"  {chunk}")
        lines.append("")
        for test in h["tests"]:
            marker = "*" if test.get("p_adjusted") is not None else " "
            lines.append(f"  {marker} {test['name']}")
            adjusted = (f"  p_holm={_p(test['p_adjusted'])}"
                        if test.get("p_adjusted") is not None else "")
            lines.append(f"      {test['test']}: statistic={test['statistic']:,.2f}  "
                         f"p={_p(test['p_value'])}{adjusted}")
            lines.append(f"      {test['effect_name']} = {test['effect_size']:.4f}")
            if test.get("shift"):
                s = test["shift"]
                lines.append(f"      shift = {s['estimate']:+,.4f} "
                             f"[{s['ci_low']:+,.4f}, {s['ci_high']:+,.4f}]")
        if h["intervals"]:
            lines.append("")
            for name, interval in h["intervals"].items():
                lines.append(f"      {name:<42} {interval['estimate']:+,.4f} "
                             f"[{interval['ci_low']:+,.4f}, {interval['ci_high']:+,.4f}]")
        lines.append("")

    lines.append("  * = member of the pre-registered confirmatory family "
                 "(Holm-adjusted); unmarked tests are exploratory.")
    lines.append("=" * 78)
    return "\n".join(lines)


def _wrap(text: str, width: int) -> List[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


# --------------------------------------------------------------------------- #
# Repeated timing measurement
# --------------------------------------------------------------------------- #
def measure_timing(config: GMAISConfig | None = None, *, repeats: int = 5,
                   verbose: bool = True) -> Dict[str, object]:
    """Aggregate the measured governance cost over several campaigns.

    A single campaign's microbenchmarks are not a defensible number. The
    per-event operations run in the tens of microseconds, where CPU frequency
    scaling, cache state and competing load move a measurement by a factor of
    two or more between otherwise identical runs -- an effect this project
    observed directly (end-to-end mediation ranged over 77-161 us/event across
    five runs of the same seed on one host).

    What survives that noise is the *ordering* of the components, which is the
    claim the manuscript actually rests on. This routine therefore reports the
    median and full range of each component across ``repeats`` campaigns, plus
    whether the ranking was stable, so a reader can see which part of the
    measurement is robust and which is not.

    The analytical columns are unaffected: they are deterministic in the seed
    and identical across every repeat.
    """

    config = config or GMAISConfig()
    say = (lambda m: print(m, flush=True)) if verbose else (lambda m: None)

    components = ("audit_record_us", "policy_eval_us", "redaction_us",
                  "queue_us", "governance_total_us")
    samples: List[Dict[str, float]] = []
    for i in range(repeats):
        say(f"  campaign {i + 1}/{repeats}…")
        result = run_ablation(config)
        from .hypotheses import _per_event_measured

        samples.append(_per_event_measured(result))

    def summarise(key: str) -> Dict[str, float]:
        values = sorted(s[key] for s in samples)
        return {
            "median": round(_median(values), 3),
            "min": round(values[0], 3),
            "max": round(values[-1], 3),
            "spread_ratio": round(values[-1] / values[0], 2) if values[0] else 0.0,
        }

    ranked = [tuple(sorted(components[:4], key=lambda k: -s[k])) for s in samples]
    stable = len(set(ranked)) == 1
    # The manuscript's claim is about which component *dominates*, not about the
    # full ordering: the lower-ranked components are separated by a few
    # microseconds and swap freely under load, whereas the dominant one does
    # not. Report the two facts separately rather than collapsing them.
    dominant_stable = len({r[0] for r in ranked}) == 1

    summary = {
        "repeats": repeats,
        "host": environment_manifest(),
        "per_event_us": {k: summarise(k) for k in components},
        "audit_share_of_mediation": [
            round(s["audit_record_us"] / s["governance_total_us"], 4)
            for s in samples
        ],
        "component_ranking_stable": stable,
        "dominant_component_stable": dominant_stable,
        "dominant_component": ranked[0][0] if dominant_stable else None,
        "ranking": list(ranked[0]),
        "note": ("Absolute magnitudes are host- and load-dependent; the "
                 "component ordering is the robust result."),
    }

    if verbose:
        say("")
        say(f"{'component':<22}{'median':>10}{'min':>10}{'max':>10}{'spread':>9}")
        for key in components:
            s = summary["per_event_us"][key]
            say(f"{key:<22}{s['median']:>10.2f}{s['min']:>10.2f}"
                f"{s['max']:>10.2f}{s['spread_ratio']:>8.1f}x")
        say("")
        say(f"Full ordering stable across all {repeats} runs: {stable}")
        say(f"Dominant component stable:                 {dominant_stable}"
            + (f"  ({ranked[0][0].replace('_us', '')})" if dominant_stable else ""))
        say(f"  run 1 ordering: "
            f"{' > '.join(k.replace('_us', '') for k in summary['ranking'])}")
    return summary
