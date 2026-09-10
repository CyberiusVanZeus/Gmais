"""Academic analytics narration for each factorial cell.

For every row in the per-cell results table the web interface shows a short,
scholarly description of what that cell's numbers mean within the study's
design-science / factorial-ablation frame: which hypothesis the cell informs,
how to read its accuracy and detection figures, and how its latency/token
differentials feed the Security Tax. The text is generated from the cell's
actual measured values so the narration matches the displayed result.
"""

from __future__ import annotations

from typing import Dict


def _fmt_delta(value: float, unit: str) -> str:
    """Format a differential with an explicit sign and unit."""
    if value == 0:
        return f"no change in {unit} versus baseline"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:g} {unit} versus baseline"


def cell_analytics(cell: str, row: Dict, baseline: Dict) -> str:
    """Return an academic description of one cell's result row."""

    acc = row.get("correct")
    # Per-run rows carry booleans; aggregate rows carry rates. Normalise to text.
    acc_txt = (
        f"{acc:.0%}" if isinstance(acc, (int, float)) and not isinstance(acc, bool)
        else ("correct" if acc else "incorrect")
    )
    d_lat = row.get("delta_latency", 0)
    d_tok = row.get("delta_tokens", 0)
    bias = row.get("bias_exposure", 0)

    if cell == "Baseline":
        return (
            "Control condition (V=0, G=0). Concurrent Worker synthesis with no "
            "validation and no governance, providing the reference distribution "
            "against which every Security-Tax differential is computed. Its "
            f"analytical outcome here is {acc_txt} and it detects no adversarial "
            "injections by construction; unredacted entity names circulate among "
            f"peers ({bias} mentions), the maximal bias-exposure baseline. This "
            "cell isolates the unscaffolded multi-agent pipeline."
        )
    if cell == "V-only":
        return (
            "Validation main-effect condition (V=1, G=0), informing H1. The "
            "Validator applies Admiralty source grading and ACH diagnosticity, so "
            "the change in analytical accuracy and the injection-detection F1 "
            "relative to Baseline estimate the validation effect uncontaminated by "
            f"governance overhead. Outcome here is {acc_txt}. The token cost rises "
            f"({_fmt_delta(d_tok, 'tokens')}) from the critique loop, but without "
            "the governance layer no audit trail or need-to-know redaction is "
            "applied."
        )
    if cell == "G-only":
        return (
            "Governance main-effect condition (V=0, G=1), informing H2. Analytical "
            "logic is identical to Baseline, so accuracy is expected to be "
            f"unchanged ({acc_txt}); the contrast of interest is computational "
            f"overhead ({_fmt_delta(d_lat, 'ms')}, {_fmt_delta(d_tok, 'tokens')}), "
            "the latency and token tax of authenticated delegation, fG(e) policy "
            "checks, hash-chained auditing and worker-to-worker entity redaction "
            f"(bias exposure driven to {bias}). This row operationalises the "
            "Security Tax in isolation from validation."
        )
    if cell == "Full":
        return (
            "Full GMAIS condition (V=1, G=1), informing the H3 interaction. It "
            "combines validation accuracy with the governed overhead, and because "
            "the Governance Layer also mediates the Validator's traffic, its cost "
            "is expected to exceed the additive sum of the two main effects "
            "(super-additivity). Outcome here is "
            f"{acc_txt} with {_fmt_delta(d_lat, 'ms')} and "
            f"{_fmt_delta(d_tok, 'tokens')}; entity bias exposure is {bias}. This "
            "is the deployable governed architecture whose Security-Tax band sets "
            "the policy regime (Section 3.3.7)."
        )
    return "Unrecognised cell."
