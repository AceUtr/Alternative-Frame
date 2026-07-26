from __future__ import annotations

import argparse
import sys
from pathlib import Path

from validation import ContributionValidator


PROJECT_ROOT = Path(__file__).resolve().parent
MANIFESTS = {
    ("domain", "software"): "software.json",
    ("domain", "research"): "research.json",
    ("runtime", "edge-cloud"): "edge-cloud.json",
    ("module", "evaluation"): "evaluation.json",
}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Validate a teammate contribution before merge.")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--domain", choices=("software", "research"))
    selector.add_argument("--runtime", choices=("edge-cloud",))
    selector.add_argument("--module", choices=("evaluation",))
    parser.add_argument("--skip-smoke", action="store_true", help="Run structure, imports, preflight and tests without the smoke demo.")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout for each test or smoke command in seconds.")
    parser.add_argument("--no-report", action="store_true", help="Do not write a JSON report.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    kind = "domain" if args.domain else "runtime" if args.runtime else "module"
    value = args.domain or args.runtime or args.module
    manifest = PROJECT_ROOT / "validation" / "manifests" / MANIFESTS[(kind, value)]
    validator = ContributionValidator(PROJECT_ROOT, timeout_seconds=args.timeout)
    try:
        report = validator.validate(manifest, run_smoke=not args.skip_smoke)
        if not args.no_report:
            try:
                path = validator.write_report(report, PROJECT_ROOT / "reports" / "contribution-validation")
                print(f"report={path}")
            except OSError as exc:
                print(f"report_warning={type(exc).__name__}: JSON report was not written", file=sys.stderr)
        print(f"target={report.target} status={report.status}")
        for item in report.checks:
            print(f"[{item.status.upper():7}] {item.category}/{item.name}: {item.detail}")
        return 0 if report.passed else 1
    except Exception as exc:
        print(f"validator_error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
