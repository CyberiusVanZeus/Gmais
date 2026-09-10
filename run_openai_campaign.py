"""One-shot GMAIS campaign against the hosted OpenAI backend.

Produces the genuinely *measured* end-to-end latency and exact token counts that
Limitation L2 flags as missing from the deterministic-backend campaign. The
analytical columns (accuracy, detection, Brier, rubric) are unchanged by the
backend: the tradecraft logic is Python and does not consume model output, so
only the cost columns differ.

The run is checkpointed row-by-row and its API consumption is metered, so a
failure partway through loses neither the data nor the account of the spend.
"""

from dotenv import load_dotenv

load_dotenv("/root/Gmais/.env")

from gmais.campaign import run_campaign          # noqa: E402
from gmais.config import GMAISConfig             # noqa: E402

if __name__ == "__main__":
    config = GMAISConfig(
        scenarios_per_tier=45,      # the pre-registered 540-observation design
        backend="openai",
        model="gpt-4o-mini",        # recorded in the manifest
        seed=20260605,
    )
    run_campaign(config, outdir="results_openai", with_figures=True)
