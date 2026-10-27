"""Parse Zephyr ``kernel stacks`` / thread-analyzer UART lines from CI serial logs."""

from __future__ import annotations

import re

# Threads that may appear in Zigbee integration profiling logs (docs + CI JSON).
KNOWN_SINGLE_WORD_THREADS = frozenset(
    {
        "zboss",
        "main",
        "idle",
        "ISR0",
        "sysworkq",
        "logging",
        "shell_uart",
        "usbd",
        "udc_nrfx",
        "bt_tx_processor",
    }
)

KNOWN_MULTI_WORD_THREADS = frozenset(
    {
        "MPSL Work",
        "BT RX WQ",
        "BT LW WQ",
    }
)

KNOWN_THREADS = KNOWN_SINGLE_WORD_THREADS | KNOWN_MULTI_WORD_THREADS

USBHS_THREAD_RE = re.compile(r"^usbhs@[0-9a-fA-F]+$")

# UART line wrap often drops the leading "MP" from ``MPSL Work``.
MPSL_WORK_FRAGMENT_NAMES = frozenset(
    {
        "L Work",
        "PSL Work",
        "SL Work",
        "Work",
    }
)

# Leftover UART/ANSI prompt fragments before the real thread name.
UART_ARTIFACT_PREFIX_RE = re.compile(
    r"^(?:(?:\d+m)?(?:ua|uar|uart|mua|muar|muart))\s+",
    re.IGNORECASE,
)

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9?0-9;]*[ -/]*[@-~]|\x1b\].*?(?:\x07|\x1b\\)")
LOG_PREFIX_RE = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2}[ T].*?)?(?:uart:~?\$\s*)+",
)

STACK_LINE_RE = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z0-9 @._@-]{0,40}?)\s+:\s+STACK:\s+"
    r"unused\s+(?P<unused>\d+)\s+usage\s+(?P<used>\d+)\s+/\s+(?P<size>\d+)"
)

# Longest suffix first so ``shell_uart`` wins over ``uart`` if both were known.
_SUFFIX_MATCH_MIN_LEN = 6


def strip_ansi(text: str) -> str:
    text = ANSI_ESCAPE_RE.sub("", text)
    text = re.sub(r"\[[0-9;]*[DJm]", "", text)
    return text


def normalize_log_text(text: str) -> str:
    lines_out: list[str] = []
    for line in text.splitlines():
        line = strip_ansi(line.strip())
        line = LOG_PREFIX_RE.sub("", line)
        if not line or "STACK:" not in line:
            continue
        if "\x1b" in line:
            continue
        lines_out.append(line)
    return "\n".join(lines_out)


def _strip_uart_artifact_prefixes(name: str) -> str:
    for _ in range(8):
        stripped = UART_ARTIFACT_PREFIX_RE.sub("", name, count=1).strip()
        if stripped == name:
            break
        name = stripped
    return name


def canonical_thread_name(raw: str) -> str:
    """Normalize UART corruption; may still be a fragment (see match_known_thread)."""
    name = re.sub(r"\s+", " ", raw.strip())
    if name.startswith("zcl "):
        name = name[4:].strip()

    name = _strip_uart_artifact_prefixes(name)

    if name in MPSL_WORK_FRAGMENT_NAMES:
        return "MPSL Work"

    if name in KNOWN_THREADS:
        return name

    if " " in name:
        parts = name.split()
        if parts[-1] == "Work":
            return "MPSL Work"
        if parts[-1] in KNOWN_SINGLE_WORD_THREADS:
            return parts[-1]
        if " ".join(parts[-2:]) in KNOWN_MULTI_WORD_THREADS:
            return " ".join(parts[-2:])

    return name.strip()


def match_known_thread(raw: str) -> str | None:
    """Map a log thread name to exactly one known thread, or drop it."""
    name = canonical_thread_name(raw)
    low = name.lower()

    if "analyzer" in low or "total cpu" in low:
        return None

    if name in KNOWN_THREADS:
        return name

    if USBHS_THREAD_RE.match(name):
        return name

    if " " in name:
        return None

    candidates: list[str] = []
    for known in KNOWN_SINGLE_WORD_THREADS:
        if name == known:
            return known
        if len(known) >= _SUFFIX_MATCH_MIN_LEN and name.endswith(known):
            candidates.append(known)
        elif len(name) >= _SUFFIX_MATCH_MIN_LEN and known.endswith(name):
            # truncated prefix (rare); only if unique
            candidates.append(known)

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return max(candidates, key=len)


def is_documented_thread(name: str) -> bool:
    return match_known_thread(name) is not None


def parse_stack_text(text: str) -> dict[str, dict[str, int]]:
    """Return peak stack stats per known thread name from log text."""
    normalized = normalize_log_text(text)
    peaks: dict[str, dict[str, int]] = {}
    for match in STACK_LINE_RE.finditer(normalized):
        name = match_known_thread(match.group("name"))
        if name is None:
            continue
        used_b = int(match.group("used"))
        size_b = int(match.group("size"))
        unused_b = int(match.group("unused"))
        slot = peaks.get(name)
        if slot is None or used_b > slot["used_b"]:
            peaks[name] = {
                "used_b": used_b,
                "size_b": size_b,
                "unused_b": unused_b,
            }
    return peaks


def filter_threads_for_docs(
    threads: dict[str, dict[str, int]],
) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for raw_name, stats in threads.items():
        name = match_known_thread(raw_name)
        if name is None:
            continue
        slot = out.get(name)
        if slot is None or stats["used_b"] > slot["used_b"]:
            out[name] = stats
    return out


def parse_stack_line(line: str) -> tuple[str, dict[str, int]] | None:
    match = STACK_LINE_RE.search(line)
    if not match:
        return None
    name = match_known_thread(match.group("name"))
    if name is None:
        return None
    return name, {
        "used_b": int(match.group("used")),
        "size_b": int(match.group("size")),
        "unused_b": int(match.group("unused")),
    }
