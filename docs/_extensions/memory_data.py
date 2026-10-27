"""
Copyright (c) 2026 Nordic Semiconductor ASA

SPDX-License-Identifier: LicenseRef-Nordic-5-Clause

Shared memory requirement data for Zigbee documentation tables and charts.

Board data lives in docs/data/memory/<board>.yaml.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from docutils import nodes
from docutils.parsers.rst import directives
from docutils.statemachine import StringList
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective

from stack_log_parse import filter_threads_for_docs

__version__ = "0.1.0"

RESOURCES_DIR = Path(__file__).parent / "static"
DATA_DIR = Path(__file__).parents[1] / "data" / "memory"
FULL_STACK_AGGREGATE_PATH = DATA_DIR / "ci_stack_build333" / "stack_usage_full_aggregate.json"

# Row order for sample-centric stack tables (platforms).
STACK_PLATFORM_ORDER: tuple[str, ...] = (
    "nrf52840",
    "nrf5340",
    "nrf54l10",
    "nrf54l15",
    "nrf54lm20",
    "nrf52840_dongle",
)

# Tab order for stack views (sample keys in CI aggregate JSON).
STACK_SAMPLE_KEY_ORDER: tuple[str, ...] = (
    "network_coordinator",
    "light_bulb",
    "light_switch",
    "light_switch_nus",
    "shell",
    "shell_usb",
)

INTERNAL_NVM_COLUMNS = (
    ("boot", "MCUboot (used / free)"),
    ("slot0", "Application (used / free)"),
    ("slot1", "Upgrade slot (used / free)"),
    ("factory_data", "Factory data"),
    ("storage", "Storage"),
    ("zboss_nvram", "ZBOSS NVRAM"),
    ("zboss_product_config", "ZBOSS product config"),
)

EXTERNAL_NVM_COLUMN_ORDER = ("slot1_ext", "slot3_ext")

RAM_SUBHEAD = "used / free"
EMPTY_CELL = "--"

DEFAULT_MAIN_STACK_SIZE_B = 1280
DEFAULT_ZBOSS_STACK_SIZE_B = 2944

STACK_MAIN_SUBHEADS = ("stack usage", "stack size")
STACK_ZBOSS_SUBHEADS = ("stack usage", "stack size")

PADDING_LABEL = "Unused"


def _sample_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    entries = data.get("samples")
    if not entries:
        return []
    return entries


def applicable_samples(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        sample for sample in _sample_entries(data) if not sample.get("not_applicable")
    ]


def stack_samples(data: dict[str, Any]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for sample in _sample_entries(data):
        if sample.get("not_applicable"):
            continue
        stack = sample.get("stack")
        if not stack:
            continue
        if "main" in stack or "zboss" in stack:
            samples.append(sample)
    return samples


def stack_thread_sizes(samples: list[dict[str, Any]]) -> tuple[int, int]:
    main_sizes = [
        int(sample["stack"]["main"]["size_b"])
        for sample in samples
        if sample.get("stack", {}).get("main")
    ]
    zboss_sizes = [
        int(sample["stack"]["zboss"]["size_b"])
        for sample in samples
        if sample.get("stack", {}).get("zboss")
    ]
    main_max = max(main_sizes) if main_sizes else DEFAULT_MAIN_STACK_SIZE_B
    zboss_max = max(zboss_sizes) if zboss_sizes else DEFAULT_ZBOSS_STACK_SIZE_B
    return main_max, zboss_max


def _stack_cell(stack: dict[str, Any], thread: str, field: str) -> str:
    thread_data = stack.get(thread)
    if not thread_data or field not in thread_data:
        return EMPTY_CELL
    return str(int(thread_data[field]))


def sample_stack_table_cells(sample: dict[str, Any]) -> list[str]:
    stack = sample["stack"]
    return [
        _stack_cell(stack, "main", "used_b"),
        _stack_cell(stack, "main", "size_b"),
        _stack_cell(stack, "zboss", "used_b"),
        _stack_cell(stack, "zboss", "size_b"),
    ]


def load_board_data(board: str) -> dict[str, Any]:
    path = DATA_DIR / f"{board}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Memory data file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _part_size_bytes(part: dict[str, Any]) -> int:
    size_kb = float(part["size_kb"])
    return round(size_kb * 1024)


def _padding_part(offset: int, size_bytes: int) -> dict[str, Any]:
    return {
        "id": "padding",
        "label": PADDING_LABEL,
        "size_kb": round(size_bytes / 1024),
        "offset": offset,
    }


def _sort_partitions(partitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    real = [part for part in partitions if part.get("id") != "padding"]
    if real and all("offset" in part for part in real):
        return sorted(partitions, key=lambda part: (part.get("offset", 0), part["order"]))
    return sorted(partitions, key=lambda part: part["order"])


def expand_partition_gaps(
    partitions: list[dict[str, Any]],
    flash_total_kb: float | None,
) -> list[dict[str, Any]]:
    real = [
        part
        for part in partitions
        if part.get("id") != "padding" and part.get("memory") != "ram"
    ]
    if not real:
        return []

    if all("offset" in part for part in real):
        ordered = sorted(real, key=lambda part: part["offset"])
        expanded: list[dict[str, Any]] = []
        cursor = 0
        flash_end = round(float(flash_total_kb) * 1024) if flash_total_kb is not None else None

        for part in ordered:
            offset = int(part["offset"])
            if offset > cursor:
                gap_bytes = offset - cursor
                if gap_bytes > 0:
                    expanded.append(_padding_part(cursor, gap_bytes))
            expanded.append(dict(part))
            cursor = max(cursor, offset + _part_size_bytes(part))

        if flash_end is not None and cursor < flash_end:
            gap_bytes = flash_end - cursor
            if gap_bytes > 0:
                expanded.append(_padding_part(cursor, gap_bytes))

        for order, part in enumerate(expanded):
            part["order"] = order
        return expanded

    ordered = sorted(real, key=lambda part: part["order"])
    if flash_total_kb is None:
        return ordered

    used_kb = sum(float(part["size_kb"]) for part in ordered)
    if flash_total_kb <= used_kb:
        return ordered

    padding_kb = flash_total_kb - used_kb
    expanded = list(ordered)
    expanded.append(
        {
            "id": "padding",
            "label": PADDING_LABEL,
            "size_kb": padding_kb,
            "order": len(expanded),
        }
    )
    return expanded


def resolve_layout_raw(data: dict[str, Any], layout_name: str) -> dict[str, Any]:
    layouts = data["layouts"]
    layout = layouts[layout_name]
    if "extends" in layout:
        base = resolve_layout_raw(data, layout["extends"])
        own = layout.get("partitions", [])
        own_ids = {part["id"] for part in own}

        merged: dict[str, dict[str, Any]] = {
            part["id"]: dict(part) for part in own
        }
        for part in base["partitions"]:
            if part["id"] not in own_ids and part["id"] != "padding":
                merged[part["id"]] = dict(part)

        partitions = _sort_partitions(list(merged.values()))
        external = layout.get("external", base.get("external"))
        return {"partitions": partitions, "external": external}
    return {
        "partitions": _sort_partitions(list(layout["partitions"])),
        "external": layout.get("external"),
    }


def _apply_layout_gaps(data: dict[str, Any], layout: dict[str, Any]) -> dict[str, Any]:
    partitions = expand_partition_gaps(
        layout["partitions"],
        board_nvm_total_kb(data),
    )
    external = layout.get("external")
    if external is not None:
        external = {
            **external,
            "partitions": expand_partition_gaps(
                external["partitions"],
                float(external["nvm_total_kb"]),
            ),
        }
    return {"partitions": partitions, "external": external}


def resolve_layout(data: dict[str, Any], layout_name: str) -> dict[str, Any]:
    return _apply_layout_gaps(data, resolve_layout_raw(data, layout_name))


def layout_nvm_total_kb(layout: dict[str, Any]) -> float:
    real = [
        part
        for part in layout["partitions"]
        if part.get("memory") != "ram" and part.get("id") != "padding"
    ]
    if real and all("offset" in part for part in real):
        end = max(int(part["offset"]) + _part_size_bytes(part) for part in real)
        return end / 1024
    return float(sum(part["size_kb"] for part in real))


def board_nvm_total_kb(data: dict[str, Any]) -> float:
    board_total = data.get("board", {}).get("nvm_total_kb")
    if board_total is not None:
        return float(board_total)
    return layout_nvm_total_kb(resolve_layout_raw(data, "base"))


def sample_layout(data: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any] | None:
    layout_name = sample.get("layout")
    if layout_name is None:
        return None
    return resolve_layout(data, layout_name)


def table_constants(data: dict[str, Any]) -> dict[str, int]:
    board_table = data.get("board", {}).get("table")
    if board_table:
        constants = {
            "zboss_nvram_kb": int(board_table["zboss_nvram_kb"]),
            "zboss_product_config_kb": int(board_table["zboss_product_config_kb"]),
        }
        if "storage_kb" in board_table:
            constants["storage_kb"] = int(board_table["storage_kb"])
        return constants

    if "layouts" not in data:
        raise KeyError(
            f"Board data must define board.table or layouts for table generation: {data.get('board')}"
        )

    layout = resolve_layout(data, "base")
    by_id = {part["id"]: part for part in layout["partitions"]}
    return {
        "zboss_nvram_kb": int(by_id["zboss_nvram"]["size_kb"]),
        "zboss_product_config_kb": int(by_id["zboss_product_config"]["size_kb"]),
        "storage_kb": int(by_id["storage"]["size_kb"]),
    }


def board_external_nvm_columns(data: dict[str, Any]) -> list[tuple[str, str]]:
    """External NVM table columns when any layout defines external upgrade slots."""
    labels: dict[str, str] = {}
    order: dict[str, int] = {}
    for layout in data.get("layouts", {}).values():
        external = layout.get("external")
        if not external:
            continue
        for part in external["partitions"]:
            if part["id"] == "padding":
                continue
            labels.setdefault(part["id"], part["label"])
            order.setdefault(part["id"], int(part["order"]))

    if not labels:
        return []

    column_order = {
        part_id: index for index, part_id in enumerate(EXTERNAL_NVM_COLUMN_ORDER)
    }
    return sorted(
        labels.items(),
        key=lambda item: (column_order.get(item[0], len(EXTERNAL_NVM_COLUMN_ORDER)), order[item[0]]),
    )


def board_has_external_nvm(data: dict[str, Any]) -> bool:
    return bool(board_external_nvm_columns(data))


def board_external_total_kb(data: dict[str, Any]) -> float | None:
    """Return external NVM capacity when any layout defines external flash."""
    for layout in data.get("layouts", {}).values():
        external = layout.get("external")
        if external:
            return float(external["nvm_total_kb"])
    return None


def _partition_map(layout: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if layout is None:
        return {}
    parts = {
        part["id"]: part
        for part in layout["partitions"]
        if part.get("id") != "padding"
    }
    external = layout.get("external")
    if external:
        for part in external["partitions"]:
            if part.get("id") != "padding":
                parts[part["id"]] = part
    return parts


def _fmt_kb(value: int | float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.1f}"


def _used_free(used: int, total: int | None) -> str:
    if total is None:
        return _fmt_kb(used)
    free = max(int(total) - used, 0)
    return f"{_fmt_kb(used)} / {_fmt_kb(free)}"


def _partition_size(
    parts: dict[str, dict[str, Any]],
    part_id: str,
    constants: dict[str, int],
) -> int | None:
    if part_id in parts:
        return int(parts[part_id]["size_kb"])
    if part_id == "storage":
        return constants.get("storage_kb")
    if part_id == "zboss_nvram":
        return constants["zboss_nvram_kb"]
    if part_id == "zboss_product_config":
        return constants["zboss_product_config_kb"]
    return None


def sample_table_cells(
    data: dict[str, Any],
    sample: dict[str, Any],
    *,
    include_external: bool,
) -> list[str]:
    constants = table_constants(data)
    usage = sample.get("usage", {})
    nvm = usage.get("nvm", {})
    layout = sample_layout(data, sample)
    parts = _partition_map(layout)
    ram_total = data.get("board", {}).get("ram_total_kb")

    cells: list[str] = []

    # MCUboot — used / free within boot partition when present.
    if "boot" in parts or nvm.get("boot"):
        boot_used = int(nvm.get("boot", 0))
        boot_total = _partition_size(parts, "boot", constants)
        cells.append(_used_free(boot_used, boot_total))
    else:
        cells.append(EMPTY_CELL)

    # Application — used / free within slot0.
    app_used = int(nvm.get("slot0", 0))
    app_total = _partition_size(parts, "slot0", constants)
    cells.append(_used_free(app_used, app_total))

    external_usage = usage.get("external", {})

    # Reserved internal NVM partitions — used/free when measured, else size or --.
    for part_id, _ in INTERNAL_NVM_COLUMNS[2:]:
        size = _partition_size(parts, part_id, constants)
        used = nvm.get(part_id)
        if used is not None and size is not None:
            cells.append(_used_free(int(used), size))
        elif size is not None:
            cells.append(_fmt_kb(size))
        else:
            cells.append(EMPTY_CELL)

    if include_external:
        for part_id, _ in board_external_nvm_columns(data):
            ext_size = _partition_size(parts, part_id, constants)
            ext_used = external_usage.get(part_id)
            if ext_used is not None and ext_size is not None:
                cells.append(_used_free(int(ext_used), ext_size))
            elif ext_size is not None:
                cells.append(_fmt_kb(ext_size))
            else:
                cells.append(EMPTY_CELL)

    ram_used = int(usage.get("ram_used_kb", 0))
    cells.append(_used_free(ram_used, int(ram_total) if ram_total is not None else None))

    return cells


def _header_label(data: dict[str, Any], kind: str) -> str:
    board = data.get("board", {})
    if kind == "nvm":
        total = board_nvm_total_kb(data)
        return f"Internal NVM ({_fmt_kb(total)} kB)"
    if kind == "external":
        for sample in applicable_samples(data):
            if "layout" not in sample:
                continue
            external = resolve_layout(data, sample["layout"]).get("external")
            if external:
                total = external["nvm_total_kb"]
                return f"External NVM ({_fmt_kb(total)} kB)"
        return "External NVM"
    total = board.get("ram_total_kb")
    return f"RAM ({_fmt_kb(total)} kB)" if total is not None else "RAM"


def _append_rst_cell(state, entry: nodes.entry, rst_text: str) -> None:
    paragraph = nodes.paragraph()
    content = StringList([rst_text], "<memory_table>")
    state.nested_parse(content, 0, paragraph)
    if len(paragraph) == 1 and isinstance(paragraph[0], nodes.paragraph):
        inner = paragraph[0]
        paragraph.remove(inner)
        paragraph.extend(inner.children)
    entry += paragraph


def _append_text_cell(row: nodes.row, text: str, *, css_class: str = "memory-req-value") -> None:
    entry = nodes.entry()
    entry["classes"] = [css_class]
    entry += nodes.Text(text)
    row += entry


def build_memory_table_nodes(directive: SphinxDirective, data: dict[str, Any]) -> nodes.table:
    external_columns = board_external_nvm_columns(data)
    include_external = bool(external_columns)
    internal_count = len(INTERNAL_NVM_COLUMNS)
    external_count = len(external_columns)
    total_cols = 1 + internal_count + external_count + 1

    table = nodes.table()
    table["classes"] = ["memory-req-table"]

    tgroup = nodes.tgroup(cols=total_cols)
    table += tgroup

    colspecs = [nodes.colspec(colwidth=28)] + [nodes.colspec(colwidth=10)] * (total_cols - 1)
    tgroup.extend(colspecs)

    thead = nodes.thead()
    tgroup += thead

    group_row = nodes.row()
    thead += group_row

    sample_group = nodes.entry()
    sample_group["morerows"] = 1
    sample_group += nodes.Text("Sample")
    group_row += sample_group

    nvm_group = nodes.entry()
    nvm_group["morecols"] = internal_count - 1
    nvm_group["classes"] = ["memory-req-group-nvm"]
    nvm_group += nodes.Text(_header_label(data, "nvm"))
    group_row += nvm_group

    if include_external:
        external_group = nodes.entry()
        if external_count > 1:
            external_group["morecols"] = external_count - 1
        external_group["classes"] = ["memory-req-group-external"]
        external_group += nodes.Text(_header_label(data, "external"))
        group_row += external_group

    ram_group = nodes.entry()
    ram_group["classes"] = ["memory-req-group-ram"]
    ram_group += nodes.Text(_header_label(data, "ram"))
    group_row += ram_group

    sub_row = nodes.row()
    thead += sub_row

    for _, label in INTERNAL_NVM_COLUMNS:
        entry = nodes.entry()
        entry["classes"] = ["memory-req-subhead"]
        entry += nodes.Text(label)
        sub_row += entry

    for part_id, label in external_columns:
        entry = nodes.entry()
        entry["classes"] = ["memory-req-subhead"]
        if part_id in ("slot1_ext", "slot3_ext"):
            label = f"{label} (used / free)"
        entry += nodes.Text(label)
        sub_row += entry

    ram_sub = nodes.entry()
    ram_sub["classes"] = ["memory-req-subhead"]
    ram_sub += nodes.Text(RAM_SUBHEAD)
    sub_row += ram_sub

    tbody = nodes.tbody()
    tgroup += tbody

    for sample in applicable_samples(data):
        row = nodes.row()
        tbody += row

        sample_entry = nodes.entry()
        sample_entry["classes"] = ["memory-req-sample"]
        _append_rst_cell(directive.state, sample_entry, sample["label"])
        row += sample_entry

        cells = sample_table_cells(data, sample, include_external=include_external)
        for value in cells:
            css = "memory-req-empty" if value == EMPTY_CELL else "memory-req-value"
            _append_text_cell(row, value, css_class=css)

    return table


def build_stack_table_nodes(
    directive: SphinxDirective, data: dict[str, Any]
) -> nodes.table | nodes.paragraph:
    samples = stack_samples(data)
    if not samples:
        board_name = data.get("board", {}).get("name", "unknown")
        paragraph = nodes.paragraph()
        paragraph += nodes.Text(f"No stack measurements for {board_name}.")
        return paragraph

    table = nodes.table()
    table["classes"] = ["memory-req-table", "stack-req-table"]

    tgroup = nodes.tgroup(cols=5)
    table += tgroup
    tgroup.extend([nodes.colspec(colwidth=28)] + [nodes.colspec(colwidth=10)] * 4)

    thead = nodes.thead()
    tgroup += thead

    group_row = nodes.row()
    thead += group_row

    sample_group = nodes.entry()
    sample_group["morerows"] = 1
    sample_group += nodes.Text("Sample")
    group_row += sample_group

    main_group = nodes.entry()
    main_group["morecols"] = 1
    main_group["classes"] = ["memory-req-group-main"]
    main_group += nodes.Text("main thread")
    group_row += main_group

    zboss_group = nodes.entry()
    zboss_group["morecols"] = 1
    zboss_group["classes"] = ["memory-req-group-zboss"]
    zboss_group += nodes.Text("zboss thread")
    group_row += zboss_group

    sub_row = nodes.row()
    thead += sub_row

    for label in STACK_MAIN_SUBHEADS + STACK_ZBOSS_SUBHEADS:
        entry = nodes.entry()
        entry["classes"] = ["memory-req-subhead"]
        entry += nodes.Text(label)
        sub_row += entry

    tbody = nodes.tbody()
    tgroup += tbody

    for sample in samples:
        row = nodes.row()
        tbody += row

        sample_entry = nodes.entry()
        sample_entry["classes"] = ["memory-req-sample"]
        _append_rst_cell(directive.state, sample_entry, sample["label"])
        row += sample_entry

        for value in sample_stack_table_cells(sample):
            css = "memory-req-empty" if value == EMPTY_CELL else "memory-req-value"
            _append_text_cell(row, value, css_class=css)

    return table


@dataclass(frozen=True)
class SampleStackMatrix:
    sample_key: str
    platforms: tuple[str, ...]
    threads: tuple[str, ...]
    thread_max_size_b: dict[str, int]
    cells: dict[tuple[str, str], dict[str, int]]


def note_stack_aggregate_dependency(env: Any) -> None:
    """Ensure memory.rst is rebuilt when CI stack JSON changes (incremental Sphinx)."""
    path = FULL_STACK_AGGREGATE_PATH
    if path.is_file():
        env.note_dependency(path.resolve().as_posix())


@lru_cache(maxsize=4)
def load_full_stack_aggregate(_mtime_ns: int) -> dict[str, dict[str, dict[str, dict[str, int]]]]:
    """board_id -> sample_key -> thread -> {used_b, size_b, ...}"""
    path = FULL_STACK_AGGREGATE_PATH
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    boards = payload.get("boards")
    if not isinstance(boards, dict):
        return {}
    return boards


def _load_full_stack_aggregate_boards() -> dict[str, dict[str, dict[str, dict[str, int]]]]:
    path = FULL_STACK_AGGREGATE_PATH
    if not path.is_file():
        return {}
    return load_full_stack_aggregate(path.stat().st_mtime_ns)


def stack_sample_keys_with_data() -> list[str]:
    boards = _load_full_stack_aggregate_boards()
    present = {key for samples in boards.values() for key in samples}
    return [key for key in STACK_SAMPLE_KEY_ORDER if key in present]


@lru_cache(maxsize=None)
def board_display_name(board_id: str) -> str:
    path = DATA_DIR / f"{board_id}.yaml"
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        name = (data.get("board") or {}).get("name")
        if name:
            return str(name)
    return board_id


def build_sample_stack_matrix(sample_key: str) -> SampleStackMatrix | None:
    boards = _load_full_stack_aggregate_boards()
    platform_data: dict[str, dict[str, dict[str, int]]] = {}
    for board_id in STACK_PLATFORM_ORDER:
        sample_threads = boards.get(board_id, {}).get(sample_key)
        if sample_threads:
            filtered = filter_threads_for_docs(sample_threads)
            if filtered:
                platform_data[board_id] = filtered
    if not platform_data:
        return None

    all_threads: set[str] = set()
    for threads in platform_data.values():
        all_threads.update(threads.keys())

    def max_size_b(thread: str) -> int:
        sizes = [
            int(platform_data[plat][thread]["size_b"])
            for plat in platform_data
            if thread in platform_data[plat]
        ]
        return max(sizes) if sizes else 0

    threads_ordered = tuple(
        sorted(all_threads, key=lambda name: (-max_size_b(name), name.lower()))
    )
    thread_max_size_b = {name: max_size_b(name) for name in threads_ordered}

    cells: dict[tuple[str, str], dict[str, int]] = {}
    for board_id, thread_map in platform_data.items():
        for thread in threads_ordered:
            stats = thread_map.get(thread)
            if stats:
                cells[(board_id, thread)] = {
                    "used_b": int(stats["used_b"]),
                    "size_b": int(stats["size_b"]),
                }

    return SampleStackMatrix(
        sample_key=sample_key,
        platforms=tuple(platform_data.keys()),
        threads=threads_ordered,
        thread_max_size_b=thread_max_size_b,
        cells=cells,
    )


def _thread_header_label(thread: str, max_size_b: int) -> str:
    return f"{thread} ({max_size_b}\u202fB max)"


def build_stack_sample_table_nodes(matrix: SampleStackMatrix) -> nodes.table | nodes.paragraph:
    if not matrix.platforms or not matrix.threads:
        paragraph = nodes.paragraph()
        paragraph += nodes.Text(f"No stack data for sample {matrix.sample_key}.")
        return paragraph

    n_thread_cols = len(matrix.threads)
    table = nodes.table()
    table["classes"] = ["memory-req-table", "stack-req-table", "stack-sample-table"]

    total_cols = 1 + n_thread_cols * 2
    tgroup = nodes.tgroup(cols=total_cols)
    table += tgroup
    tgroup.extend([nodes.colspec(colwidth=16)] + [nodes.colspec(colwidth=8)] * (total_cols - 1))

    thead = nodes.thead()
    tgroup += thead

    group_row = nodes.row()
    thead += group_row

    platform_group = nodes.entry()
    platform_group["morerows"] = 1
    platform_group += nodes.Text("Platform")
    group_row += platform_group

    for thread in matrix.threads:
        thread_group = nodes.entry()
        thread_group["morecols"] = 1
        thread_group["classes"] = ["memory-req-group-stack-thread"]
        thread_group += nodes.Text(_thread_header_label(thread, matrix.thread_max_size_b[thread]))
        group_row += thread_group

    sub_row = nodes.row()
    thead += sub_row

    for _thread in matrix.threads:
        for label in STACK_MAIN_SUBHEADS:
            entry = nodes.entry()
            entry["classes"] = ["memory-req-subhead"]
            entry += nodes.Text(label)
            sub_row += entry

    tbody = nodes.tbody()
    tgroup += tbody

    for board_id in matrix.platforms:
        row = nodes.row()
        tbody += row

        platform_entry = nodes.entry()
        platform_entry["classes"] = ["memory-req-sample"]
        platform_entry += nodes.Text(board_display_name(board_id))
        row += platform_entry

        for thread in matrix.threads:
            stats = matrix.cells.get((board_id, thread))
            if stats:
                values = (str(stats["used_b"]), str(stats["size_b"]))
            else:
                values = (EMPTY_CELL, EMPTY_CELL)
            for value in values:
                css = "memory-req-empty" if value == EMPTY_CELL else "memory-req-value"
                _append_text_cell(row, value, css_class=css)

    return table


class StackSampleTable(SphinxDirective):
    """Stack usage table: platforms as rows, threads as columns (CI full aggregate)."""

    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = True
    has_content = False
    option_spec = {
        "sample": directives.unchanged_required,
    }

    def run(self) -> list[nodes.Node]:
        note_stack_aggregate_dependency(self.env)
        matrix = build_sample_stack_matrix(self.options["sample"])
        if matrix is None:
            paragraph = nodes.paragraph()
            paragraph += nodes.Text(
                f"No stack measurements for sample {self.options['sample']}."
            )
            return [paragraph]
        return [build_stack_sample_table_nodes(matrix)]


class StackTable(SphinxDirective):
    """Render stack usage table from docs/data/memory/."""

    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = True
    has_content = False
    option_spec = {
        "board": directives.unchanged_required,
    }

    def run(self) -> list[nodes.Node]:
        data = load_board_data(self.options["board"])
        return [build_stack_table_nodes(self, data)]


class MemoryTable(SphinxDirective):
    """Render memory requirements table from docs/data/memory/."""

    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = True
    has_content = False
    option_spec = {
        "board": directives.unchanged_required,
    }

    def run(self) -> list[nodes.Node]:
        data = load_board_data(self.options["board"])
        return [build_memory_table_nodes(self, data)]


def add_memory_table_resources(app: Sphinx) -> None:
    static_path = RESOURCES_DIR.as_posix()
    if static_path not in app.config.html_static_path:
        app.config.html_static_path.append(static_path)
    app.add_css_file("memory_table.css")


def setup(app: Sphinx) -> dict[str, Any]:
    app.add_directive("memory-table", MemoryTable)
    app.add_directive("stack-table", StackTable)
    app.add_directive("stack-sample-table", StackSampleTable)
    app.connect("builder-inited", add_memory_table_resources)
    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
