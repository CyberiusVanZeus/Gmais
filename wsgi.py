"""WSGI entry point for hosting the GMAIS web app on a cloud server.

No Docker required. Run behind any WSGI server, e.g. gunicorn:

    gunicorn -w 2 -b 0.0.0.0:5000 wsgi:app

or for a quick start with Flask's built-in server (development only):

    python -m gmais.webapp

Configure the corpus size or LLM backend with environment variables read by
``create_app`` defaults, or edit the GMAISConfig passed below.
"""

from __future__ import annotations

import os

from gmais.config import GMAISConfig
from gmais.webapp import create_app

# Corpus size for the interactive demo (kept small for snappy page loads).
# The web interface chooses LLM providers per-run from the form (Claude / OpenAI
# / local, round-robin with local fallback), so no backend is fixed here.
_per_tier = int(os.getenv("GMAIS_WEB_PER_TIER", "5"))

app = create_app(GMAISConfig(scenarios_per_tier=_per_tier))

if __name__ == "__main__":  # pragma: no cover
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
