"""One-shot GMAIS campaign against the hosted OpenAI backend.

Produces the genuinely *measured* end-to-end latency and exact token counts that
Limitation L2 flags as missing from the deterministic-backend campaign. The
analytical columns (accuracy, detection, Brier, rubric) are unchanged by the
backend: the tradecraft logic is Python and does not consume model output, so
only the cost columns differ.

The run is checkpointed row-by-row and its API consumption is metered, so a
failure partway through loses neither the data nor the account of the spend.
"""

import os

from dotenv import load_dotenv

load_dotenv("/root/Gmais/.env")

from gmais.campaign import run_campaign          # noqa: E402
from gmais.config import GMAISConfig             # noqa: E402

#: Spend guard. The 540-observation campaign issues 2,700 billable calls
#: (~$0.59 at gpt-4o-mini prices). The completed run is already recorded in
#: results_openai/ and does not need repeating, so an accidental
#: `python run_openai_campaign.py` must not silently re-spend. Re-running is
#: deliberate and requires GMAIS_CONFIRM_SPEND=yes.
def _require_confirmation() -> None:
    import sys

    if os.getenv("GMAIS_CONFIRM_SPEND", "").strip().lower() != "yes":
        sys.exit(
            "REFUSING TO RUN: this issues ~2,700 billable OpenAI calls (~$0.59).\n"
            "The completed campaign is already in results_openai/.\n"
            "To re-run deliberately:  GMAIS_CONFIRM_SPEND=yes python run_openai_campaign.py"
        )


if __name__ == "__main__":
    _require_confirmation()
    config = GMAISConfig(
        scenarios_per_tier=45,      # the pre-registered 540-observation design
        backend="openai",
        model="gpt-4o-mini",        # recorded in the manifest
        seed=20260605,
    )
    run_campaign(config, outdir="results_openai", with_figures=True)
