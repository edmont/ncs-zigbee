"""
Copyright (c) 2026 Nordic Semiconductor ASA

SPDX-License-Identifier: LicenseRef-Nordic-5-Clause

Sphinx extension for stack usage bar charts in Zigbee documentation.
"""

from __future__ import annotations

import html
from typing import Any

from docutils import nodes
from docutils.parsers.rst import directives
from docutils.statemachine import StringList
from memory_data import (
    EMPTY_CELL,
    SampleStackMatrix,
    board_display_name,
    build_sample_stack_matrix,
    load_board_data,
    note_stack_aggregate_dependency,
    stack_samples,
    stack_thread_sizes,
)
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective

__version__ = "0.1.0"

RESOURCES_DIR = __import__("pathlib").Path(__file__).parent / "static"

THREAD_COLORS = {
    "main": ("#2563eb", "#93c5fd"),
    "zboss": ("#0891b2", "#a5f3fc"),
}

THREAD_COLOR_FALLBACKS = (
    ("#7c3aed", "#c4b5fd"),
    ("#059669", "#6ee7b7"),
    ("#d97706", "#fcd34d"),
    ("#dc2626", "#fca5a5"),
    ("#64748b", "#cbd5e1"),
    ("#0d9488", "#99f6e4"),
)


def _b_label(value_b: int) -> str:
    # Narrow no-break space before B avoids doc theme byte→kB auto-formatting (e.g. "1280 B" → "12 kB B").
    return f"{value_b}\u202fB"


def _render_thread_empty() -> str:
    return (
        '<div class="memory-viz-bar-wrap stack-viz-thread-empty" '
        f'aria-hidden="true">{EMPTY_CELL}</div>'
    )


def _thread_colors(thread_name: str, column_index: int) -> tuple[str, str]:
    if thread_name in THREAD_COLORS:
        return THREAD_COLORS[thread_name]
    pair = THREAD_COLOR_FALLBACKS[column_index % len(THREAD_COLOR_FALLBACKS)]
    return pair


def _thread_css_class(thread_name: str) -> str:
    slug = thread_name.lower().replace(" ", "-").replace("@", "-")
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-_"
    slug = "".join(ch if ch in allowed else "-" for ch in slug)
    return slug or "thread"


def _render_thread_bar(
    thread_name: str,
    label: str,
    used_b: int,
    size_b: int,
    max_size_b: int,
    column_index: int = 0,
) -> str:
    """Render a stack bar on a board-wide byte scale (max_size_b per thread column)."""
    used_color, free_color = _thread_colors(thread_name, column_index)
    thread_id = _thread_css_class(thread_name)
    scale_b = max_size_b if max_size_b > 0 else size_b
    bar_width_pct = min(100.0, 100.0 * size_b / scale_b) if scale_b else 100.0
    used_pct = min(100.0, 100.0 * used_b / size_b) if size_b else 0.0
    free_pct = 100.0 - used_pct
    free_b = max(size_b - used_b, 0)
    title = (
        f"{label}: {_b_label(size_b)} "
        f"({_b_label(used_b)} used, {_b_label(free_b)} free)"
    )
    inner = (
        f'<span class="memory-viz-fill memory-viz-fill-used" '
        f'style="width:{used_pct:.2f}%;background:{used_color}"></span>'
        f'<span class="memory-viz-fill memory-viz-fill-free" '
        f'style="width:{free_pct:.2f}%;background:{free_color}"></span>'
    )
    return (
        f'<div class="memory-viz-bar stack-viz-thread-bar" role="img" '
        f'aria-label="{html.escape(label, quote=True)}" '
        f'style="width:{bar_width_pct:.4f}%">'
        f'<div class="memory-viz-segment memory-viz-segment-{thread_id}" '
        f'style="flex:1 1 100%" '
        f'data-tooltip="{html.escape(title, quote=True)}">'
        f"{inner}</div></div>"
    )


def _parse_rst_label(directive: SphinxDirective, text: str) -> nodes.Element:
    label = nodes.paragraph()
    label["classes"] = ["memory-viz-sample-label"]
    content = StringList([text], "<stack_viz>")
    directive.state.nested_parse(content, 0, label)
    if len(label) == 1 and isinstance(label[0], nodes.paragraph):
        inner = label[0]
        label.remove(inner)
        label.extend(inner.children)
    return label


def _legend_swatch(color: str) -> str:
    return f'<span class="memory-viz-swatch" style="background:{color}"></span>'


def _legend_items_used_free(thread_id: str, label_base: str) -> str:
    used_color, free_color = THREAD_COLORS[thread_id]
    items: list[str] = []
    for suffix, color in (("used", used_color), ("free", free_color)):
        items.append(
            f'<span class="memory-viz-legend-item">'
            f"{_legend_swatch(color)}"
            f"{label_base} ({suffix})"
            f"</span>"
        )
    return "".join(items)


def _render_board_header(main_size_b: int, zboss_size_b: int) -> str:
    return (
        f'<div class="stack-viz-chart-header">'
        f'<div class="memory-viz-panel-title memory-viz-panel-title-sample">Sample</div>'
        f'<div class="stack-viz-header-thread">'
        f'<div class="memory-viz-panel-title">'
        f'main thread ({_b_label(main_size_b)})</div>'
        f'<div class="memory-viz-legend">{_legend_items_used_free("main", "main")}</div>'
        f"</div>"
        f'<div class="stack-viz-header-thread">'
        f'<div class="memory-viz-panel-title">'
        f'zboss thread ({_b_label(zboss_size_b)})</div>'
        f'<div class="memory-viz-legend">{_legend_items_used_free("zboss", "zboss")}</div>'
        f"</div>"
        f"</div>"
    )


def _grid_style(main_size_b: int, zboss_size_b: int) -> str:
    return (
        f"--stack-viz-main-fr:{main_size_b}fr;"
        f"--stack-viz-zboss-fr:{zboss_size_b}fr"
    )


def _build_board_nodes(directive: SphinxDirective, board: str) -> nodes.Element:
    data = load_board_data(board)
    samples = stack_samples(data)
    if not samples:
        paragraph = nodes.paragraph()
        paragraph += nodes.Text(f"No stack measurements for board {board}.")
        return paragraph

    main_size_b, zboss_size_b = stack_thread_sizes(samples)
    style = _grid_style(main_size_b, zboss_size_b)

    wrapper = nodes.container()
    wrapper["classes"] = ["stack-viz-board-outer"]
    wrapper += nodes.raw(
        "",
        f'<div class="stack-viz-board" data-board="{board}" style="{style}">',
        format="html",
    )

    board_node = nodes.container()
    board_node["classes"] = ["stack-viz-board-inner"]
    board_node += nodes.raw(
        "",
        _render_board_header(main_size_b, zboss_size_b),
        format="html",
    )

    samples_node = nodes.container()
    samples_node["classes"] = ["stack-viz-samples"]

    for sample in samples:
        stack = sample["stack"]
        row = nodes.container()
        row["classes"] = ["stack-viz-sample-row"]
        row += _parse_rst_label(directive, sample["label"])
        main_data = stack.get("main")
        if main_data:
            main_html = (
                '<div class="memory-viz-bar-wrap">'
                + _render_thread_bar(
                    "main",
                    "main thread",
                    int(main_data["used_b"]),
                    int(main_data["size_b"]),
                    main_size_b,
                    0,
                )
                + "</div>"
            )
        else:
            main_html = _render_thread_empty()
        row += nodes.raw("", main_html, format="html")

        zboss_data = stack.get("zboss")
        if zboss_data:
            zboss_html = (
                '<div class="memory-viz-bar-wrap">'
                + _render_thread_bar(
                    "zboss",
                    "zboss thread",
                    int(zboss_data["used_b"]),
                    int(zboss_data["size_b"]),
                    zboss_size_b,
                    1,
                )
                + "</div>"
            )
        else:
            zboss_html = _render_thread_empty()
        row += nodes.raw("", zboss_html, format="html")
        samples_node += row

    board_node += samples_node
    wrapper += board_node
    wrapper += nodes.raw("", "</div>", format="html")
    return wrapper


def _sample_matrix_grid_style(matrix: SampleStackMatrix) -> str:
    parts = ["12rem"]
    for thread in matrix.threads:
        weight = matrix.thread_max_size_b.get(thread, 1024)
        parts.append(f"minmax(0, {weight}fr)")
    cols = " ".join(parts)
    return f"--stack-sample-cols:{cols};"


def _render_sample_matrix_html(matrix: SampleStackMatrix, sample_key: str) -> str:
    """Single flat grid: header and data rows share identical column tracks."""
    style = _sample_matrix_grid_style(matrix)
    chunks: list[str] = [
        '<div class="stack-viz-board-outer stack-sample-matrix-outer">',
        f'<div class="stack-viz-board stack-sample-matrix" '
        f'data-sample="{html.escape(sample_key, quote=True)}" style="{style}">',
        '<div class="stack-sample-grid">',
        '<div class="stack-sample-cell stack-sample-head stack-sample-platform-col">'
        "Platform</div>",
    ]
    for thread in matrix.threads:
        max_b = matrix.thread_max_size_b[thread]
        title = (
            f"{html.escape(thread, quote=True)}<br>"
            f'<span class="stack-sample-head-size">{_b_label(max_b)} max</span>'
        )
        chunks.append(
            f'<div class="stack-sample-cell stack-sample-head stack-sample-thread-col">'
            f"{title}</div>"
        )

    for board_id in matrix.platforms:
        chunks.append(
            '<div class="stack-sample-cell stack-sample-platform-col stack-sample-data-row">'
            f"{html.escape(board_display_name(board_id), quote=True)}</div>"
        )
        for idx, thread in enumerate(matrix.threads):
            stats = matrix.cells.get((board_id, thread))
            max_b = matrix.thread_max_size_b[thread]
            if stats:
                bar_inner = _render_thread_bar(
                    thread,
                    thread,
                    int(stats["used_b"]),
                    int(stats["size_b"]),
                    max_b,
                    idx,
                )
                cell = (
                    '<div class="stack-sample-cell stack-sample-bar-col stack-sample-data-row">'
                    f'<div class="memory-viz-bar-wrap stack-sample-bar-wrap">{bar_inner}</div>'
                    "</div>"
                )
            else:
                cell = (
                    '<div class="stack-sample-cell stack-sample-bar-col stack-sample-data-row">'
                    f"{_render_thread_empty()}</div>"
                )
            chunks.append(cell)

    chunks.extend(["</div>", "</div>", "</div>"])
    return "".join(chunks)


def _build_sample_matrix_nodes(
    directive: SphinxDirective, sample_key: str
) -> nodes.Element:
    matrix = build_sample_stack_matrix(sample_key)
    if matrix is None:
        paragraph = nodes.paragraph()
        paragraph += nodes.Text(f"No stack measurements for sample {sample_key}.")
        return paragraph

    wrapper = nodes.container()
    wrapper["classes"] = ["stack-sample-matrix-docutils"]
    wrapper += nodes.raw("", _render_sample_matrix_html(matrix, sample_key), format="html")
    return wrapper


class StackSampleBoard(SphinxDirective):
    """Stack chart: platforms as rows, threads as columns (CI full aggregate)."""

    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = True
    has_content = False
    option_spec = {
        "sample": directives.unchanged_required,
    }

    def run(self) -> list[nodes.Node]:
        note_stack_aggregate_dependency(self.env)
        return [_build_sample_matrix_nodes(self, self.options["sample"])]


class StackBoard(SphinxDirective):
    """Render stack usage charts for a board defined in docs/data/memory/."""

    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = True
    has_content = False
    option_spec = {
        "board": directives.unchanged_required,
    }

    def run(self) -> list[nodes.Node]:
        return [_build_board_nodes(self, self.options["board"])]


def add_stack_viz_resources(app: Sphinx) -> None:
    static_path = RESOURCES_DIR.as_posix()
    if static_path not in app.config.html_static_path:
        app.config.html_static_path.append(static_path)
    app.add_css_file("stack_viz.css")


def setup(app: Sphinx) -> dict[str, Any]:
    app.add_directive("stack-board", StackBoard)
    app.add_directive("stack-sample-board", StackSampleBoard)
    app.connect("builder-inited", add_stack_viz_resources)
    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
