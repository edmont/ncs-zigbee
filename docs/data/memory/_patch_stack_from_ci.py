#!/usr/bin/env python3
"""Patch docs/data/memory/*.yaml stack blocks from CI log (line-preserving)."""

from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parent
LOG_PREFIX = re.compile(r"Stack usage updated for (\S+) / (\S+) from ")

# Configured stack sizes (Kconfig targets, 128-byte aligned).
SIZE_MAIN = 1280
SIZE_ZBOSS_BULB = 3328
SIZE_ZBOSS_SWITCH = 3200
SIZE_ZBOSS_DEFAULT = 2944

BULB = "zigbee_light_bulb_sample"
SWITCH = "zigbee_light_switch_sample"
NUS = "zigbee_light_switch_sample_nus"
FOTA = "lib_zigbee_fota"
NCP = "zigbee_ncp_sample"
TEMPLATE = "zigbee_template_sample"
SHELL = "zigbee_shell_sample"


def zboss_size_for_label(label: str) -> int:
    if BULB in label:
        return SIZE_ZBOSS_BULB
    if SWITCH in label:
        return SIZE_ZBOSS_SWITCH
    return SIZE_ZBOSS_DEFAULT


def ci_key_for_label(label: str, board: str) -> str | None:
    if TEMPLATE in label or NCP in label:
        return None
    if SHELL in label:
        return "shell_usb" if "USB transport" in label or "over USB" in label else "shell"
    if SWITCH in label and NUS in label and FOTA in label:
        return None
    if SWITCH in label and NUS in label:
        return "light_switch_nus" if board == "nrf52840" else None
    if SWITCH in label and FOTA in label:
        return "light_switch_fota"
    if SWITCH in label:
        return "light_switch"
    if "Network coordinator" in label:
        return "network_coordinator"
    if BULB in label:
        return "light_bulb"
    return None


def parse_log(path: Path) -> dict[tuple[str, str], dict[str, dict[str, int]]]:
    peaks: dict[tuple[str, str], dict[str, dict[str, int]]] = defaultdict(dict)
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LOG_PREFIX.search(line)
        if not m:
            continue
        payload_at = line.find(": {", m.end())
        if payload_at < 0:
            continue
        board, sample = m.group(1), m.group(2)
        payload = line[payload_at + 2 :].strip()
        try:
            data = ast.literal_eval(payload)
        except (SyntaxError, ValueError):
            continue
        slot = peaks[(board, sample)]
        for thread, vals in data.items():
            used = int(vals["used_b"])
            prev = slot.get(thread, {}).get("used_b", 0)
            if used >= prev:
                slot[thread] = {"used_b": used}
    return peaks


def stack_lines(label: str, threads: dict[str, dict[str, int]]) -> list[str]:
    if "main" not in threads or "zboss" not in threads:
        return []
    zboss_size = zboss_size_for_label(label)
    lines = [
        "    stack:",
        "      main:",
        f"        used_b: {threads['main']['used_b']}",
        f"        size_b: {SIZE_MAIN}",
        "      zboss:",
        f"        used_b: {threads['zboss']['used_b']}",
        f"        size_b: {zboss_size}",
    ]
    return lines


def patch_file(path: Path, peaks: dict[tuple[str, str], dict[str, dict[str, int]]]) -> bool:
    board = path.stem
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    i = 0
    changed = False
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^  - label: (.+)$", line)
        if not m:
            out.append(line)
            i += 1
            continue
        label_raw = m.group(1)
        label = ast.literal_eval(label_raw) if label_raw.startswith("'") else label_raw.strip("'")
        block_start = i
        i += 1
        while i < len(lines) and not lines[i].startswith("  - label:"):
            i += 1
        block = lines[block_start:i]
        ci_key = ci_key_for_label(label, board)
        new_stack: list[str] = []
        if ci_key is not None:
            thread_peaks = peaks.get((board, ci_key), {})
            new_stack = stack_lines(label, thread_peaks)
        # Drop existing stack block from sample
        filtered: list[str] = []
        j = 0
        while j < len(block):
            if block[j].strip() == "stack:":
                j += 1
                while j < len(block) and (
                    block[j].startswith("      ") or block[j].strip() == "stack:"
                ):
                    j += 1
                changed = True
                continue
            filtered.append(block[j])
            j += 1
        if new_stack:
            # Insert stack before not_applicable or at end of block
            insert_at = len(filtered)
            for k, bl in enumerate(filtered):
                if bl.strip().startswith("not_applicable:"):
                    insert_at = k
                    break
            filtered = filtered[:insert_at] + new_stack + filtered[insert_at:]
            changed = True
        out.extend(filtered)
    if changed:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not log_path or not log_path.is_file():
        print("Usage: _patch_stack_from_ci.py <jenkins-console.txt>", file=sys.stderr)
        return 1
    peaks = parse_log(log_path)
    for yaml_path in sorted(DATA_DIR.glob("*.yaml")):
        if yaml_path.name.startswith("_"):
            continue
        if patch_file(yaml_path, peaks):
            print(yaml_path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
