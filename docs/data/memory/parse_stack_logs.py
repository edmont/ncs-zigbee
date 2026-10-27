#!/usr/bin/env python3
"""Parse CI serial logs for thread-analyzer STACK lines (all threads).

Maps board serial logs to (board_id, sample_key) from log path and filename,
merges peak usage per thread, writes JSON per platform and one aggregate file.

Example:
  ./parse_stack_logs.py /path/to/333-archive -o ./ci_stack_build333
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_extensions"))
from stack_log_parse import filter_threads_for_docs, parse_stack_text

# test-fw platform slug (zip suffix) -> memory YAML board id
PLATFORM_TO_BOARD_ID: dict[str, str] = {
    "nrf52840dk_nrf52840": "nrf52840",
    "nrf52833dk_nrf52833": "nrf52833",
    "nrf52840dongle_nrf52840": "nrf52840_dongle",
    "nrf5340dk_nrf5340_cpuapp": "nrf5340",
    "nrf54l15dk_nrf54l15_cpuapp": "nrf54l15",
    "nrf54l15dk_nrf54l10_cpuapp": "nrf54l10",
    "nrf54l15dk_nrf54l05_cpuapp": "nrf54l05",
    "nrf54lm20dk_nrf54lm20a_cpuapp": "nrf54lm20",
    "nrf54lm20dk_nrf54lm20b_cpuapp": "nrf54lm20",
}

ROLE_TO_DOC_KEY: dict[str, str] = {
    "NetworkCoordinator": "network_coordinator",
    "LightBulb": "light_bulb",
    "LightSwitch": "light_switch",
    "LightSwitchWithNus": "light_switch_nus",
    "ZigbeeShell": "shell",
    "ZigbeeShellViaUsb": "shell_usb",
}

LOG_SAMPLE_RE = re.compile(
    r"(?:board|daylight|yoda)_\d+_(?P<role>[A-Za-z0-9]+)\.log(?:\.raw)?$"
)


def is_sample_serial_log_path(name: str) -> bool:
    base = Path(name).name
    return (
        base.endswith(".log")
        and not base.endswith(".log.raw")
        and base.startswith(("board_", "daylight_", "yoda_"))
    )

FAILS_PLATFORM_RE = re.compile(r"/fails/(?P<platform>[^/]+)/")


def doc_key_from_log_path(path: str) -> str | None:
    name = Path(path).name
    m = LOG_SAMPLE_RE.search(name)
    if not m:
        return None
    return ROLE_TO_DOC_KEY.get(m.group("role"))


def platform_from_fails_path(path: str) -> str | None:
    m = FAILS_PLATFORM_RE.search(path.replace("\\", "/"))
    if not m:
        return None
    return m.group("platform")


def board_id_from_platform_slug(slug: str) -> str | None:
    return PLATFORM_TO_BOARD_ID.get(slug)


def merge_sample_threads(
    aggregate: dict[str, Any],
    board_id: str,
    doc_key: str,
    threads: dict[str, dict[str, int]],
) -> None:
    threads = filter_threads_for_docs(threads)
    if not threads:
        return
    board_bucket = aggregate.setdefault(board_id, {})
    sample_bucket = board_bucket.setdefault(doc_key, {})
    for thread, stats in threads.items():
        current = sample_bucket.get(thread)
        if current is None or stats["used_b"] > current["used_b"]:
            sample_bucket[thread] = stats


def ingest_log_bytes(
    aggregate: dict[str, Any],
    board_id: str,
    log_inner_path: str,
    data: bytes,
) -> None:
    doc_key = doc_key_from_log_path(log_inner_path)
    if doc_key is None:
        return
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return
    if "STACK:" not in text:
        return
    threads = parse_stack_text(text)
    merge_sample_threads(aggregate, board_id, doc_key, threads)


def ingest_zip(aggregate: dict[str, Any], zip_path: Path) -> str | None:
    stem = zip_path.name
    if not stem.startswith("ncs-test-output-") or not stem.endswith(".zip"):
        return None
    platform_slug = stem[len("ncs-test-output-") : -len(".zip")]
    board_id = board_id_from_platform_slug(platform_slug)
    if board_id is None:
        return None
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if not is_sample_serial_log_path(name):
                continue
            ingest_log_bytes(aggregate, board_id, name, zf.read(info))
    return board_id


def ingest_fails_tree(aggregate: dict[str, Any], fails_root: Path) -> None:
    for log_path in fails_root.rglob("*.log"):
        if log_path.name.endswith(".log.raw"):
            continue
        rel = log_path.as_posix()
        platform = platform_from_fails_path(rel)
        if platform is None:
            continue
        board_id = board_id_from_platform_slug(platform)
        if board_id is None:
            board_id = PLATFORM_TO_BOARD_ID.get(platform, platform)
        ingest_log_bytes(aggregate, board_id, log_path.name, log_path.read_bytes())


def sort_aggregate(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for board_id in sorted(data.keys()):
        samples = data[board_id]
        if not isinstance(samples, dict):
            continue
        out[board_id] = {}
        for doc_key in sorted(samples.keys()):
            threads = filter_threads_for_docs(samples[doc_key])
            if not threads:
                continue
            out[board_id][doc_key] = {
                thread: threads[thread]
                for thread in sorted(
                    threads.keys(),
                    key=lambda t: (-int(threads[t]["size_b"]), t.lower()),
                )
            }
    return out


def write_outputs(
    aggregate: dict[str, Any],
    output_dir: Path,
    source_label: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    sorted_all = sort_aggregate(aggregate)

    meta_base = {
        "source": source_label,
        "format": "board_id -> sample_key -> thread_name -> {used_b, size_b, unused_b}",
        "excluded_threads": ["thread_analyzer (profiling only)"],
    }

    aggregate_path = output_dir / "stack_usage_full_aggregate.json"
    with aggregate_path.open("w", encoding="utf-8") as handle:
        json.dump({"meta": meta_base, "boards": sorted_all}, handle, indent=2)
        handle.write("\n")

    slug_by_board = {v: k for k, v in PLATFORM_TO_BOARD_ID.items()}
    for board_id, samples in sorted_all.items():
        platform_slug = slug_by_board.get(board_id, board_id)
        per_platform = output_dir / f"stack_usage_full_{platform_slug}.json"
        with per_platform.open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "meta": {**meta_base, "board_id": board_id, "platform": platform_slug},
                    "samples": samples,
                },
                handle,
                indent=2,
            )
            handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "archive_dir",
        type=Path,
        help="CI artifact directory (333-archive with ncs-test-output-*.zip and fails/)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).parent / "ci_stack_build333",
        help="Output directory for JSON files",
    )
    parser.add_argument(
        "--include-fails",
        action="store_true",
        help="Also parse fails/**/*.log (often noisier UART; default is zip logs only)",
    )
    args = parser.parse_args()
    archive = args.archive_dir.resolve()
    if not archive.is_dir():
        print(f"Not a directory: {archive}", file=sys.stderr)
        return 1

    aggregate: dict[str, Any] = {}

    for zip_path in sorted(archive.glob("ncs-test-output-*.zip")):
        board_id = ingest_zip(aggregate, zip_path)
        if board_id:
            print(f"zip {zip_path.name} -> {board_id}", flush=True)

    if args.include_fails:
        fails = archive / "fails"
        if fails.is_dir():
            ingest_fails_tree(aggregate, fails)
            print("fails/ merged", flush=True)

    if not aggregate:
        print("No stack data parsed.", file=sys.stderr)
        return 1

    write_outputs(aggregate, args.output.resolve(), str(archive))
    print(f"Wrote JSON under {args.output}", flush=True)
    for board_id, samples in sort_aggregate(aggregate).items():
        n_samples = len(samples)
        n_threads = sum(len(t) for t in samples.values())
        print(f"  {board_id}: {n_samples} samples, {n_threads} sample-thread peaks", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
