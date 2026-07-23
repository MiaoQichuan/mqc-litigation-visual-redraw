#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for the litigation-timeline renderers.

Design principle: the model only produces semantic-map.json; ALL spatial
work (coordinates, text wrapping, collision-free packing) happens here in
deterministic code, so output quality does not depend on model strength.
"""
import json, os, html
from datetime import date

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOKENS_PATH = os.path.join(_HERE, "..", "assets", "style-tokens.json")

with open(_TOKENS_PATH, encoding="utf-8") as _f:
    TOKENS = json.load(_f)

C = TOKENS["colors"]
FONT = TOKENS["font_stack"]
TITLE_FONT = TOKENS.get("title_font", FONT)
FS = TOKENS["type_scale"]
ARROW = TOKENS["arrow"]
RADIUS = TOKENS["radius"]
DASH = TOKENS["dash"]
STROKE = TOKENS["stroke"]


def arrow_marker(mid, color, size=None, refX=None):
    """Clean isosceles arrowhead at a FIXED pixel size (userSpaceOnUse), so it
    does not balloon with stroke-width. Kept small so the tip never overpowers
    the connector or collides with a node."""
    size = size or ARROW["size"]
    refX = refX or ARROW["refX"]
    return (f'<marker id="{mid}" viewBox="0 0 12 12" refX="{refX}" refY="6" '
            f'markerWidth="{size}" markerHeight="{size}" markerUnits="userSpaceOnUse" '
            f'orient="auto"><path d="{ARROW["path"]}" fill="{color}"/></marker>')


def esc(s: str) -> str:
    """Escape text for inclusion in SVG (keeps real <text>, never paths)."""
    return html.escape(s, quote=True)


def char_w(ch: str, fs: float) -> float:
    """Approximate glyph advance. CJK ~= 1em; latin/digits ~= 0.56em.
    Good enough for wrapping and fit-tests without a font engine."""
    return fs if ord(ch) > 0x2E7F else fs * 0.56


def text_w(s: str, fs: float) -> float:
    return sum(char_w(c, fs) for c in s)


# Chinese line-breaking rules (禁则处理 / kinsoku shori):
#   NO_START — punctuation that may not BEGIN a line (closing marks). If a break
#     would push one of these to a new line, we hang it on the current line
#     instead (小幅溢出, absorbed by the box's inner padding).
#   NO_END   — punctuation that may not END a line (opening marks). If a break
#     would leave one of these at a line end, we push it down with the next char.
# Both only move break positions; characters are never added, dropped, or edited.
NO_START = set("，。、；：！？）】》」』〕｝’”》〉…—·%‰℃，。！？；：")
NO_END = set("（【《「『〔｛‘“《〈#￥")


def wrap(text: str, fs: float, max_w: float):
    """Greedy character wrap to a max pixel width, honoring CJK 禁则 (no line may
    start with closing punctuation or end with opening punctuation). Returns a
    list of lines. Verbatim: only inserts line breaks, never edits characters."""
    lines, cur, acc = [], "", 0.0
    for ch in text:
        w = char_w(ch, fs)
        if acc + w > max_w and cur:
            # A break would put `ch` at the start of the next line.
            if ch in NO_START:
                # 避头: keep the closing mark on this line (hang past max_w a touch).
                cur += ch
                acc += w
                continue
            if cur[-1] in NO_END:
                # 避尾: don't leave an opening mark stranded at the line end —
                # send it down together with `ch`.
                opener = cur[-1]
                cur = cur[:-1]
                if cur:
                    lines.append(cur)
                cur, acc = opener + ch, char_w(opener, fs) + w
                continue
            lines.append(cur)
            cur, acc = ch, w
        else:
            cur += ch
            acc += w
    if cur:
        lines.append(cur)
    return lines or [""]


def parse_date(s: str) -> date:
    """Parse 'YYYY/M/D' (single or double digit month/day)."""
    y, m, d = (int(x) for x in s.strip().split("/"))
    return date(y, m, d)


def svg_open(width, height):
    # Body font is set as a presentation attribute on the root <svg> (inherited by
    # body <text>), NOT as a <style>text{...}</style> rule. A <style> rule outranks
    # the per-title font-family presentation attribute in the CSS cascade and would
    # silently override the Song title with the body sans everywhere. Root-level
    # inheritance lets each title's own font-family attribute win.
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(width)}" '
            f'height="{int(height)}" viewBox="0 0 {int(width)} {int(height)}" '
            f'font-family="{FONT}">'
            f'<rect width="{int(width)}" height="{int(height)}" fill="{C["bg"]}"/>')


def load_map(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


SCHEMA_VERSION = 1
_TOP_KEYS = {"schema_version", "diagram_type", "layout", "title_text", "visual_mode", "axis",
             "axis_unit", "events", "spans", "points", "nodes", "edges",
             "engine", "direction", "arrows", "tall_leaves", "columns", "rows",
             "provenance"}


def validate_map(m):
    """Structural pre-flight check with actionable, id-annotated messages. Raises
    RuntimeError listing every problem, so a malformed map fails clearly instead
    of deep in a renderer. Does not touch dates (render_spans checks those).

    If `jsonschema` is installed and schemas/semantic-map.schema.json is present,
    it is also validated against that schema (Archify-style optional dependency);
    otherwise these hand checks stand alone.
    """
    layout = m.get("layout", "")
    errs, warns = [], []

    sv = m.get("schema_version")
    if sv is None:
        warns.append('missing "schema_version" (expected 1)')
    elif sv != SCHEMA_VERSION:
        errs.append(f'unsupported schema_version {sv!r} (this build expects {SCHEMA_VERSION})')
    for k in m:
        if k not in _TOP_KEYS:
            warns.append(f'unknown top-level field "{k}" (ignored)')

    if not m.get("title_text"):
        errs.append('missing "title_text" (chart title)')
    if layout in ("graphviz_flow", "graphviz_relation", "relation_tree"):
        nodes = m.get("nodes") or []
        if not nodes:
            errs.append('"nodes" is empty')
        ids = set()
        for i, n in enumerate(nodes):
            nid = n.get("id")
            if not nid:
                errs.append(f"node #{i} has no id")
            if not n.get("title"):
                errs.append(f'node "{nid or i}" has no title')
            ids.add(nid)
        for e in m.get("edges") or []:
            if e.get("from") not in ids or e.get("to") not in ids:
                errs.append(f'edge {e.get("from")}->{e.get("to")} references a missing node id')
    elif layout in ("numbered_point_timeline", "dated_point_timeline"):
        evs = m.get("events") or []
        if not evs:
            errs.append('"events" is empty')
        for i, ev in enumerate(evs):
            if not ev.get("text"):
                errs.append(f'event "{ev.get("id", i)}" has no text')
        if layout == "dated_point_timeline":
            for i, ev in enumerate(evs):
                if not ev.get("date"):
                    errs.append(f'event "{ev.get("id", i)}" has no "date" '
                                '(dated_point_timeline needs YYYY/M/D; use numbered for undated)')
    elif layout == "proportional_gantt":
        ax = m.get("axis") or {}
        if not ax.get("start") or not ax.get("end"):
            errs.append('"axis" needs start and end')
        if not (m.get("spans") or []):
            errs.append('"spans" is empty')
        for i, s in enumerate(m.get("spans") or []):
            for k in ("from", "to", "label_text"):
                if not s.get(k):
                    errs.append(f'span "{s.get("id", i)}" missing "{k}"')
    elif layout == "comparison_table":
        cols = m.get("columns") or []
        if len(cols) != 2:
            errs.append(f'comparison_table needs exactly 2 columns (A vs B); got {len(cols)}')
        cids = set()
        for i, c in enumerate(cols):
            if not c.get("id"):
                errs.append(f"column #{i} has no id")
            if not c.get("title"):
                errs.append(f'column "{c.get("id", i)}" has no title')
            cids.add(c.get("id"))
        rows = m.get("rows") or []
        if not rows:
            errs.append('"rows" is empty')
        for i, r in enumerate(rows):
            if not r.get("dimension"):
                warns.append(f'row #{i} has no "dimension" label')
            cells = r.get("cells") or {}
            for cidk in cids:
                if cidk and not cells.get(cidk):
                    errs.append(f'row #{i} missing a cell for column "{cidk}"')
    else:
        errs.append(f'unknown layout "{layout}"')

    _schema_errors(m, errs)   # optional jsonschema pass (no-op if unavailable)

    if warns:
        print("  [validate] " + "; ".join(warns))
    if errs:
        raise RuntimeError("semantic map has problems: " + "; ".join(errs))
    return True


def _schema_errors(m, errs):
    """Best-effort JSON Schema validation; silently skipped if jsonschema or the
    schema file is absent (like Archify's optional ajv step)."""
    try:
        import jsonschema  # noqa
    except Exception:
        return
    path = os.path.join(_HERE, "..", "schemas", "semantic-map.schema.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            schema = json.load(f)
        v = jsonschema.Draft202012Validator(schema)
        for e in sorted(v.iter_errors(m), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in e.path) or "(root)"
            errs.append(f'schema: {loc}: {e.message}')
    except Exception as ex:
        errs.append(f'schema validator error: {ex}')
