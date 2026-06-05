"""Command-line entry point for GMAIS.

Subcommands:

* ``run``        - execute the 2x2 factorial ablation and print the report
* ``analyze``    - run a single scenario through the Full GMAIS cell
* ``gtkg``       - build the Ground Truth Knowledge Graph and print its stats
* ``export``     - run the ablation and write the observation matrix to CSV/JSON

Examples::

    python -m gmais.cli run --per-tier 10
    python -m gmais.cli run --per-tier 45 --backend openai
    python -m gmais.cli export --per-tier 45 --out results.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict

from .ablation import run_ablation
from .analysis import build_report
from .config import CELLS, GMAISConfig
from .gtkg import GroundTruthKnowledgeGraph
from .llm import build_backend
from .orchestrator import GMAISOrchestrator
from .scenarios import generate_corpus


def _config_from_args(args: argparse.Namespace) -> GMAISConfig:
    kwargs = {}
    if getattr(args, "per_tier", None) is not None:
        kwargs["scenarios_per_tier"] = args.per_tier
    if getattr(args, "backend", None):
        kwargs["backend"] = args.backend
    if getattr(args, "seed", None) is not None:
        kwargs["seed"] = args.seed
    if getattr(args, "alpha", None) is not None:
        kwargs["st_alpha"] = args.alpha
        kwargs["st_beta"] = round(1.0 - args.alpha, 6)
    return GMAISConfig(**kwargs)


def cmd_run(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    result = run_ablation(config)
    print(build_report(result))
    return 0


def cmd_gtkg(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    corpus = generate_corpus(config.seed, config.scenarios_per_tier)
    gtkg = GroundTruthKnowledgeGraph(args.db or ":memory:")
    gtkg.load_corpus(corpus)
    print(json.dumps(gtkg.stats(), indent=2))
    gtkg.close()
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    corpus = generate_corpus(config.seed, config.scenarios_per_tier)
    scenario = next((s for s in corpus if s.sid == args.sid), corpus[0])
    backend = build_backend(config.backend, seed=config.seed, model=config.model)
    orch = GMAISOrchestrator(backend, config)
    full_cell = CELLS[-1]
    result = orch.analyze(scenario, full_cell)
    payload = asdict(result)
    if result.governance is not None:
        payload["governance"] = asdict(result.governance)
        payload["governance"].pop("redacted_messages", None)
    print(json.dumps(payload, indent=2, default=str))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    result = run_ablation(config)
    rows = result.observation_dicts()
    if args.out.endswith(".json"):
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2)
    else:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    print(f"Wrote {len(rows)} observations to {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gmais", description="GMAIS ablation harness")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--per-tier", type=int, default=None,
                       help="scenarios per complexity tier (thesis default 45)")
        p.add_argument("--backend", choices=["mock", "openai"], default=None)
        p.add_argument("--seed", type=int, default=None)
        p.add_argument("--alpha", type=float, default=None,
                       help="Security-Tax latency weight alpha (beta = 1 - alpha)")

    p_run = sub.add_parser("run", help="run the 2x2 factorial ablation")
    add_common(p_run)
    p_run.set_defaults(func=cmd_run)

    p_gtkg = sub.add_parser("gtkg", help="build the GTKG and print stats")
    add_common(p_gtkg)
    p_gtkg.add_argument("--db", default=None, help="SQLite path (default in-memory)")
    p_gtkg.set_defaults(func=cmd_gtkg)

    p_an = sub.add_parser("analyze", help="run one scenario through Full GMAIS")
    add_common(p_an)
    p_an.add_argument("--sid", default=None, help="scenario id (default first)")
    p_an.set_defaults(func=cmd_analyze)

    p_ex = sub.add_parser("export", help="run ablation and export observation matrix")
    add_common(p_ex)
    p_ex.add_argument("--out", default="gmais_observations.csv",
                      help="output file (.csv or .json)")
    p_ex.set_defaults(func=cmd_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
