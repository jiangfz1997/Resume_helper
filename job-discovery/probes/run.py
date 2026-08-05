"""Phase 0 CLI: run the reachability probe, or diff two reports.

Usage:
    python -m probes.run --env local            --out reports/local.json
    python -m probes.run --env aws-cloudshell   --out reports/aws.json
    python -m probes.run --compare reports/local.json reports/aws.json
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from probes.aggregators import JobSpyProber, jobspy_version
from probes.ats import GreenhouseProber, LeverProber, WorkdayProber
from probes.base import Prober, request_json
from probes.models import (
    EgressInfo,
    ProbeOutcome,
    ProbeReport,
    ProbeResult,
    ProbeTarget,
    ProbeTier,
    TargetSet,
)

PROBERS: dict[str, Prober] = {
    WorkdayProber.kind: WorkdayProber(),
    GreenhouseProber.kind: GreenhouseProber(),
    LeverProber.kind: LeverProber(),
    JobSpyProber.kind: JobSpyProber(),
}

DEFAULT_TARGETS = Path(__file__).parent / "targets.yaml"

SYMBOL: dict[ProbeOutcome, str] = {
    ProbeOutcome.OK: "OK      ",
    ProbeOutcome.EMPTY: "EMPTY   ",
    ProbeOutcome.BLOCKED: "BLOCKED ",
    ProbeOutcome.NOT_FOUND: "NOTFOUND",
    ProbeOutcome.ERROR: "ERROR   ",
    ProbeOutcome.SKIPPED: "SKIPPED ",
}


def load_targets(path: Path) -> TargetSet:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return TargetSet.model_validate(data)


def detect_egress() -> EgressInfo:
    response = request_json("https://ipinfo.io/json", timeout=10)
    if response.status != 200:
        return EgressInfo()
    try:
        body = response.json()
    except Exception:
        return EgressInfo()
    return EgressInfo(ip=body.get("ip"), org=body.get("org"), region=body.get("region"))


def run_probes(targets: list[ProbeTarget], delay_seconds: float) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    for index, target in enumerate(targets, start=1):
        prober = PROBERS[target.kind]
        print(f"  [{index}/{len(targets)}] {target.kind:<11} {target.name} ... ", end="", flush=True)
        result = prober.probe(target)
        results.append(result)
        print(f"{result.outcome.value} ({result.item_count} items, {result.elapsed_ms} ms)")
        if index < len(targets) and delay_seconds > 0:
            time.sleep(delay_seconds)
    return results


def print_report(report: ProbeReport) -> None:
    print()
    print("=" * 78)
    print(f"environment : {report.environment}")
    print(f"egress ip   : {report.egress.ip or 'unknown'}  org={report.egress.org or 'unknown'}")
    print(f"on aws      : {report.egress.looks_like_aws}")
    print("=" * 78)
    print(f"{'STATUS':<9} {'KIND':<11} {'TARGET':<20} {'ITEMS':>6} {'HTTP':>5}  DETAIL")
    print("-" * 78)
    for result in report.results:
        detail = (result.detail or result.sample_title or "")[:60]
        print(
            f"{SYMBOL[result.outcome]} {result.kind:<11} {result.name[:20]:<20} "
            f"{result.item_count:>6} {str(result.http_status or '-'):>5}  {detail}"
        )
    print("-" * 78)
    print("counts:", json.dumps(report.outcome_counts()))


def compare(baseline_path: Path, candidate_path: Path) -> int:
    baseline = ProbeReport.model_validate_json(baseline_path.read_text(encoding="utf-8"))
    candidate = ProbeReport.model_validate_json(candidate_path.read_text(encoding="utf-8"))
    baseline_by_key = {r.key: r for r in baseline.results}

    print()
    print(f"baseline  : {baseline.environment}  ({baseline.egress.org or 'unknown'})")
    print(f"candidate : {candidate.environment}  ({candidate.egress.org or 'unknown'})")
    print("=" * 78)
    print(f"{'TARGET':<22} {'BASELINE':<16} {'CANDIDATE':<16} VERDICT")
    print("-" * 78)

    blocked_by_ip: list[str] = []
    for result in candidate.results:
        base = baseline_by_key.get(result.key)
        if base is None:
            verdict = "no baseline"
        elif base.outcome is ProbeOutcome.OK and result.outcome is ProbeOutcome.OK:
            verdict = "reachable"
        elif base.outcome is ProbeOutcome.OK and result.outcome is not ProbeOutcome.OK:
            verdict = "IP-BLOCKED <<<"
            blocked_by_ip.append(result.name)
        elif base.outcome is not ProbeOutcome.OK and result.outcome is ProbeOutcome.OK:
            verdict = "better on candidate"
        else:
            verdict = "inconclusive (fails in both, fix target/query)"

        base_cell = f"{base.outcome.value}/{base.item_count}" if base else "-"
        cand_cell = f"{result.outcome.value}/{result.item_count}"
        print(f"{result.name[:22]:<22} {base_cell:<16} {cand_cell:<16} {verdict}")

    print("-" * 78)
    if blocked_by_ip:
        print(f"blocked only from the candidate egress: {', '.join(blocked_by_ip)}")
    else:
        print("no source degraded on the candidate egress")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 source reachability probe")
    parser.add_argument("--env", default="local", help="label recorded in the report")
    parser.add_argument("--tier", choices=["ats", "aggregator", "all"], default="all")
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--delay", type=float, default=1.5, help="seconds between probes")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BASELINE", "CANDIDATE"))
    args = parser.parse_args()

    if args.compare:
        return compare(args.compare[0], args.compare[1])

    target_set = load_targets(args.targets)
    if args.tier == "all":
        targets = target_set.all_targets()
    else:
        targets = target_set.by_tier(ProbeTier(args.tier))

    print(f"probing {len(targets)} targets as environment={args.env}")
    egress = detect_egress()
    print(f"egress: {egress.ip or 'unknown'} org={egress.org or 'unknown'} aws={egress.looks_like_aws}")

    report = ProbeReport(
        environment=args.env,
        egress=egress,
        started_at=datetime.now(timezone.utc),
        python_version=platform.python_version(),
        jobspy_version=jobspy_version(),
        results=run_probes(targets, args.delay),
    )
    print_report(report)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
