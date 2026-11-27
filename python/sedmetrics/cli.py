"""Command line entry point: evaluate predictions and write a JSON report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import adapters, report

__all__ = ["main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sedmetrics",
        description="Evaluate Sound Event Detection predictions against a dataset.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate = subparsers.add_parser(
        "evaluate", help="evaluate a predictions table and write a JSON report"
    )
    evaluate.add_argument(
        "--dataset",
        required=True,
        choices=("urban-sed", "audioset-strong"),
        help="reference dataset format",
    )
    evaluate.add_argument(
        "--root",
        required=True,
        type=Path,
        help="dataset directory, archive or parquet directory",
    )
    evaluate.add_argument(
        "--split",
        default="test",
        help="URBAN-SED split: train, test, validate or all (default: test)",
    )
    evaluate.add_argument(
        "--limit",
        type=int,
        default=None,
        help="load only the first N recordings (smoke tests)",
    )
    evaluate.add_argument(
        "--predictions",
        required=True,
        type=Path,
        help="TSV/CSV with recording, class, onset, offset columns",
    )
    evaluate.add_argument("--segment-length", type=float, default=1.0)
    evaluate.add_argument("--average", default="micro", choices=("micro", "macro"))
    evaluate.add_argument(
        "--metrics",
        nargs="+",
        default=list(report.METRICS),
        choices=list(report.METRICS),
    )
    evaluate.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the report here instead of stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    arguments = build_parser().parse_args(argv)

    if arguments.command == "evaluate":
        if arguments.dataset == "urban-sed":
            dataset = adapters.load_urban_sed(
                arguments.root, split=arguments.split, limit=arguments.limit
            )
        else:
            dataset = adapters.load_audioset_strong(
                arguments.root, limit=arguments.limit
            )

        result = report.evaluate_file(
            dataset,
            arguments.predictions,
            metrics=arguments.metrics,
            event_f1_kwargs={"average": arguments.average},
            segment_f1_kwargs={
                "average": arguments.average,
                "segment_length": arguments.segment_length,
            },
        )
        if arguments.out is None:
            json.dump(result, sys.stdout, indent=2, sort_keys=True, allow_nan=False)
            sys.stdout.write("\n")
        else:
            report.write_report(result, arguments.out)
        return 0

    raise AssertionError(f"unhandled command {arguments.command!r}")
