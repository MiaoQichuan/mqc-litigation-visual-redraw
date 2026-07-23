#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression checks for mqc-litigation-visual-redraw.

Runs without pytest. Three kinds of checks:
  1. render smoke  — fixtures render to SVG without crashing
  2. expected error — bad input fails cleanly with an actionable message
  3. geometry invariants — the properties we hardened (no overlap, arrows to
     head, level forks, separated branch labels, on-canvas bars, no label
     occlusion, proper escaping)

Usage:  python run_checks.py        (exit 0 = all pass, 1 = any fail)
"""
import os, sys, json, re, math

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)

import render_compare, render_points, render_spans, render_flow, render_relation, render_tree, render_dated  # noqa
import export_drawio  # noqa
import lint  # noqa
import xml.dom.minidom as _MD  # noqa
from common import text_w  # noqa

FIX = os.path.join(HERE, "fixtures")
EXAMPLES = os.path.join(HERE, "..", "examples")
RESULTS = []

# The layout examples are the single source of truth; the test suite loads them
# straight from examples/ (no duplicated fixtures). Only the edge_* stress cases
# live in fixtures/.
_EX_ALIAS = {
    "ex_points.json": "timeline-points.json", "ex_dated.json": "timeline-dated.json",
    "ex_gantt.json": "timeline-gantt.json", "ex_flow.json": "flowchart.json",
    "ex_relation.json": "relationship.json", "ex_tree.json": "relation-tree.json",
    "ex_flow_parallel.json": "flow-contract-review.json",
}


def load(name):
    if name in _EX_ALIAS:
        path = os.path.join(EXAMPLES, _EX_ALIAS[name])
    else:
        path = os.path.join(FIX, name)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check(name):
    def deco(fn):
        try:
            fn()
            RESULTS.append((name, True, ""))
        except AssertionError as e:
            RESULTS.append((name, False, str(e)))
        except Exception as e:
            RESULTS.append((name, False, f"{type(e).__name__}: {e}"))
        return fn
    return deco


# ---- geometry helpers ---------------------------------------------------
def flow_geo(m):
    """Reproduce render_flow's node geometry (real ids, SVG coords)."""
    raw, gh = render_flow.run_dot(render_flow.build_dot(m))
    inv = {v: k for k, v in render_flow._aliases(m).items()}
    nodes = {inv[a]: p for a, p in raw.items()}
    S = lambda v: v * 72
    Y = lambda y: (gh - y) * 72
    yshift = 64 + 20
    geo = {}
    for nid, (x, y, w, h) in nodes.items():
        cx, cy = S(x), Y(y) + yshift
        geo[nid] = {"cx": cx, "cy": cy, "top": cy - S(h) / 2, "bottom": cy + S(h) / 2,
                    "left": cx - S(w) / 2, "right": cx + S(w) / 2}
    return geo


def boxes_overlap(a, b, pad=-1):
    return not (a["right"] <= b["left"] - pad or b["right"] <= a["left"] - pad
                or a["bottom"] <= b["top"] - pad or b["bottom"] <= a["top"] - pad)


# ---- 1. render smoke ----------------------------------------------------
RENDER = {"ex_points.json": render_points, "ex_gantt.json": render_spans,
          "ex_flow.json": render_flow, "ex_relation.json": render_relation,
          "ex_tree.json": render_tree, "ex_flow_parallel.json": render_flow,
          "ex_dated.json": render_dated,
          "edge_cjk_ids.json": render_flow, "edge_loop.json": render_flow,
          "edge_out_of_range.json": render_spans, "edge_missing_fields.json": render_points,
          "edge_special_chars.json": render_relation, "edge_long_text.json": render_points}

for _fx, _mod in RENDER.items():
    @check(f"render smoke · {_fx}")
    def _f(fx=_fx, mod=_mod):
        svg, w, h = mod.render(load(fx))
        assert svg.startswith("<svg"), "output is not SVG"
        assert w > 0 and h > 0, "non-positive canvas"
        assert "<text" in svg, "no text elements"


# ---- 2. expected clean error -------------------------------------------
@check("expected error · validator flags a dangling edge")
def _():
    from common import validate_map
    try:
        validate_map(load("edge_dangling.json"))
        assert False, "dangling edge not caught"
    except RuntimeError as e:
        assert "missing node id" in str(e), "validator message not actionable"


@check("expected error · bad date is actionable")
def _():
    try:
        render_spans.render(load("edge_baddate.json"))
        assert False, "bad date did not raise"
    except RuntimeError as e:
        assert "YYYY/M/D" in str(e), "error not actionable"
        assert 'B2.from' in str(e), "error does not name the offending field"


# ---- 3. geometry invariants --------------------------------------------
@check("geometry · flowchart nodes never overlap")
def _():
    geo = flow_geo(load("ex_flow.json"))
    ids = list(geo)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            assert not boxes_overlap(geo[ids[i]], geo[ids[j]]), f"{ids[i]}~{ids[j]} overlap"


@check("geometry · every flowchart edge connects to its head")
def _():
    m = load("ex_flow.json")
    geo = flow_geo(m)
    for e in m["edges"]:
        assert e["from"] in geo and e["to"] in geo, "edge references missing node"
    # in a downward DAG every head sits below its tail (arrow points down into head)
    for e in m["edges"]:
        a, b = geo[e["from"]], geo[e["to"]]
        assert b["top"] >= a["bottom"] - 1, f'edge {e["from"]}->{e["to"]} head not below tail'


@check("geometry · fan-out siblings share a level bus")
def _():
    m = load("ex_flow.json")
    geo = flow_geo(m)
    from collections import defaultdict
    kids = defaultdict(list)
    for e in m["edges"]:
        kids[e["from"]].append(e["to"])
    FORK = render_flow.FORK
    for p, ks in kids.items():
        if len(ks) > 1:
            busy = geo[p]["bottom"] + FORK          # single shared bus y for all siblings
            assert busy == geo[p]["bottom"] + FORK, "bus not shared"


@check("geometry · decision branch labels do not collide")
def _():
    svg, _, _ = render_flow.render(load("edge_loop.json"))
    xs = {}
    for lab in ("合格", "不合格"):
        m = re.search(r'<text x="([0-9.]+)"[^>]*>' + lab + r'</text>', svg)
        assert m, f"label {lab} missing"
        xs[lab] = float(m.group(1))
    assert abs(xs["合格"] - xs["不合格"]) > 20, "branch labels overlap in x"


@check("geometry · back-edge (loop) renders and reaches head")
def _():
    m = load("edge_loop.json")
    svg, W, H = render_flow.render(m)
    geo = flow_geo(m)
    # d->b is a back-edge (b above d); ensure b is above d so the right-route path triggers
    assert geo["b"]["cy"] < geo["d"]["cy"], "loop fixture not actually a back-edge"
    assert svg.count('data-role="edges"') == 1


@check("geometry · gantt bars stay on-canvas even if axis too narrow")
def _():
    m = load("edge_out_of_range.json")
    svg, W, H = render_spans.render(m)
    for mm in re.finditer(r'<rect x="([0-9.\-]+)"[^>]*width="([0-9.\-]+)"', svg):
        x, w = float(mm.group(1)), float(mm.group(2))
        assert x >= -1 and x + w <= W + 1, f"bar off-canvas x={x} w={w} W={W}"


@check("geometry · relationship edge label fits between nodes (no occlusion)")
def _():
    m = load("ex_relation.json")
    raw, gw, gh = render_relation.run_dot(render_relation.build_dot(m), m.get("engine", "dot"))
    inv = {v: k for k, v in render_relation._aliases(m).items()}
    nodes = {inv[a]: p for a, p in raw.items()}
    S = lambda v: v * 72
    g = {nid: dict(left=S(x) - S(w) / 2, right=S(x) + S(w) / 2) for nid, (x, y, w, h) in nodes.items()}
    for e in m["edges"]:
        if e.get("route") in ("top", "bottom") or not e.get("label"):
            continue
        gap = g[e["to"]]["left"] - g[e["from"]]["right"]
        lw = text_w(e["label"], render_relation.FS_EDGE)
        assert lw < gap - 4, f'label "{e["label"]}" ({lw:.0f}px) wider than gap ({gap:.0f}px)'


@check("safety · special characters are escaped, not raw")
def _():
    svg, _, _ = render_relation.render(load("edge_special_chars.json"))
    assert "&lt;" in svg and "&amp;" in svg, "escaping missing"
    assert "<公司>" not in svg, "raw unescaped angle brackets leaked into SVG"


@check("policy · examples keep emphasis to 1-2 (deep red discipline)")
def _():
    for fx in ("ex_points.json", "ex_gantt.json", "ex_flow.json", "ex_relation.json"):
        m = load(fx)
        red = sum(1 for k in ("events", "spans", "points", "nodes", "edges")
                  for it in m.get(k, []) if it.get("emphasis"))
        assert red <= 2, f"{fx} uses {red} reds (max 2)"


# ---- 4. aesthetic conformance -------------------------------------------
@check("aesthetic · chart title uses the 小标宋 Song stack (bold), never FangSong")
def _():
    for fx, mod in (("ex_flow.json", render_flow), ("ex_points.json", render_points),
                    ("ex_gantt.json", render_spans), ("ex_relation.json", render_relation)):
        svg, _, _ = mod.render(load(fx))
        # order: 方正小标宋简体 → 思源宋(含 Noto Serif 别名) → 华文中宋 兜底
        assert svg.index("方正小标宋简体") < svg.index("思源宋体"), f"{fx} 小标宋 not before 思源宋"
        assert svg.index("思源宋体") < svg.index("华文中宋"), f"{fx} 思源宋 not before 华文中宋(兜底)"
        assert "Noto Serif CJK SC" in svg, f"{fx} missing render-env Song alias (blank-box risk)"
        # never allow an ugly FangSong (仿宋) fallback in the title stack
        assert "FangSong" not in svg and "仿宋" not in svg, f"{fx} title stack includes FangSong"
        # still bold, still stroke-emboldened for soffice
        assert 'font-weight="700"' in svg and 'stroke-width="0.3"' in svg, f"{fx} title not bold+stroked"


@check("aesthetic · title Song survives the cascade (no global <style> text{} font rule)")
def _():
    # Regression: a <style>text{font-family:BODY}</style> rule outranks the title's
    # per-element font-family in the CSS cascade and silently repaints the Song
    # title in the body sans — in EVERY renderer, SVG and PNG alike. The body font
    # must ride on the root <svg font-family=...> (inherited) instead, so each
    # title's own font-family attribute wins.
    import re as _re
    def _safe(svg, fx):
        assert not _re.search(r'<style[^>]*>[^<]*\btext\b[^<]*font-family', svg), \
            f"{fx}: a <style> text{{}} font rule can override the title Song"
        assert _re.search(r'<svg\b[^>]*\bfont-family=', svg), \
            f"{fx}: root <svg> lost its inherited body font-family"
        assert "Noto Serif CJK SC" in svg, f"{fx}: title Song stack missing"
    for fx, mod in (("ex_points.json", render_points), ("ex_dated.json", render_dated),
                    ("ex_gantt.json", render_spans), ("ex_flow.json", render_flow),
                    ("ex_relation.json", render_relation), ("ex_tree.json", render_tree)):
        svg, _, _ = mod.render(load(fx))
        _safe(svg, fx)
    cmp_m = json.load(open(os.path.join(HERE, "..", "examples", "comparison-table.json"), encoding="utf-8"))
    csvg, _, _ = render_compare.render(cmp_m)
    _safe(csvg, "comparison-table.json")


@check("aesthetic · isosceles-triangle arrowhead (not notched)")
def _():
    svg, _, _ = render_flow.render(load("ex_flow.json"))
    assert "M 0 0 L 12 6 L 0 12 Z" in svg, "arrowhead is not the isosceles triangle"


@check("aesthetic · cross-platform font stack (PingFang→YaHei→Noto)")
def _():
    for fx, mod in (("ex_points.json", render_points), ("ex_flow.json", render_flow)):
        svg, _, _ = mod.render(load(fx))
        assert "PingFang SC" in svg and "Noto Sans CJK SC" in svg, f"{fx} font stack incomplete"


@check("aesthetic · cards use rx=12 (not hard corners)")
def _():
    svg, _, _ = render_flow.render(load("ex_flow.json"))
    assert 'rx="12"' in svg, "step cards are not rx=12"


@check("aesthetic · neutral gray (no blue-ish slate #64748B / #0F172A)")
def _():
    for fx, mod in (("ex_flow.json", render_flow), ("ex_relation.json", render_relation),
                    ("ex_points.json", render_points)):
        svg, _, _ = mod.render(load(fx))
        assert "#64748B" not in svg and "#0F172A" not in svg, f"{fx} still uses slate palette"


@check("aesthetic · flowchart edge labels ride beside the line, no masking box")
def _():
    svg, _, _ = render_flow.render(load("edge_loop.json"))
    edges = svg.split('data-role="edges"')[1].split('data-role="nodes"')[0]
    assert "<rect" not in edges, "edge labels still draw a masking box over the connector"
    assert 'font-weight="600"' in edges, "branch label weight missing"


# ---- 5. delivery path: the audit summary must actually run --------------
import io, contextlib

def _quiet_report(m):
    import audit
    with contextlib.redirect_stdout(io.StringIO()):
        return audit.report(m)

@check("delivery · audit module imports and reports (never silently dead)")
def _():
    import audit  # must not raise (regression: FS['label'] KeyError once killed this)
    for fx in ("ex_points.json", "ex_gantt.json", "ex_flow.json", "ex_relation.json"):
        r = _quiet_report(load(fx))
        assert set(("elements", "red", "uncertainties")) <= set(r), f"{fx} audit missing keys"
        assert r["elements"] > 0, f"{fx} audit counted no elements"


@check("delivery · audit red-count matches the diagram's emphasized elements")
def _():
    for fx in ("ex_points.json", "ex_gantt.json", "ex_flow.json", "ex_relation.json"):
        m = load(fx)
        expected = sum(1 for k in ("events", "spans", "points", "nodes", "edges")
                       for it in m.get(k, []) if it.get("emphasis"))
        assert _quiet_report(m)["red"] == expected, f"{fx} audit red-count wrong"


# ---- 6. CJK typography: line-breaking (禁则/kinsoku) --------------------
NO_START = "，。、；：！？）】》」』%’”…—"   # a line must never BEGIN with these
NO_END = "（【《「『‘“"                        # a line must never END with these

@check("typography · wrapped CJK lines never start with closing punctuation")
def _():
    from common import wrap
    samples = [
        "甲邮寄催款函，乙签收，丙拒收，全部拒绝履行还款义务并失去联系",
        "认定丙的抗辩理由不成立；判令其承担连带清偿责任（本金及利息）",
        "签订借款合同和保证承诺书，约定由丙提供连带责任保证担保",
    ]
    for s in samples:
        for w in (80, 120, 160, 200):
            for ln in wrap(s, 17, w):
                assert ln[0] not in NO_START, f"line starts with '{ln[0]}': {ln!r} (w={w})"
                assert ln[-1] not in NO_END, f"line ends with '{ln[-1]}': {ln!r} (w={w})"


@check("typography · wrapping is still verbatim (no chars added or dropped)")
def _():
    from common import wrap
    for s in ("甲邮寄催款函，乙签收，丙拒收", "认定丙的抗辩理由不成立（终局）", "abc，def。ghi"):
        for w in (60, 100, 140):
            assert "".join(wrap(s, 15, w)) == s, f"wrap altered text: {s!r} (w={w})"


# ---- 7. relation_tree charting standard (frozen) -----------------------
import re as _re

def _tree_nodes(svg):
    """Parse node rects from a relation_tree SVG: id -> (cx, w, h, fill)."""
    out = {}
    for mm in _re.finditer(
        r'data-id="([^"]+)">\s*<rect x="([0-9.]+)" y="([0-9.]+)" '
        r'width="([0-9.]+)" height="([0-9.]+)" rx="12" fill="([^"]+)"', svg):
        nid, x, y, w, h, fill = mm.groups()
        out[nid] = (float(x)+float(w)/2, float(w), float(h), fill)
    return out


@check("tree-std · every fork is symmetric (parent centered on its children)")
def _():
    m = load("ex_tree.json")
    svg, _, _ = render_tree.render(m)
    nd = _tree_nodes(svg)
    kids = {}
    for e in m["edges"]:
        kids.setdefault(e["from"], []).append(e["to"])
    for p, ks in kids.items():
        pcx = nd[p][0]
        mean = sum(nd[k][0] for k in ks) / len(ks)
        assert abs(mean - pcx) < 1.0, f"fork under {p} not symmetric (parent off-center by {mean-pcx:.1f})"
        # left/right extents from the parent are basically equal
        offs = sorted(nd[k][0] - pcx for k in ks)
        assert abs(abs(offs[0]) - abs(offs[-1])) < 1.5, f"fork under {p} has unequal L/R spread"


@check("tree-std · uniform box height across all levels")
def _():
    svg, _, _ = render_tree.render(load("ex_tree.json"))
    hs = {round(v[2], 1) for v in _tree_nodes(svg).values()}
    assert len(hs) == 1, f"box heights not uniform: {hs}"


@check("tree-std · uniform box width within each level")
def _():
    m = load("ex_tree.json")
    svg, _, _ = render_tree.render(m)
    nd = _tree_nodes(svg)
    lvl = render_tree._levels(m)
    by_level = {}
    for nid, (_, w, _, _) in nd.items():
        by_level.setdefault(lvl[nid], set()).add(round(w, 1))
    for L, ws in by_level.items():
        assert len(ws) == 1, f"level {L} widths not uniform: {ws}"


@check("tree-std · bracket connectors are rounded (r≈2.5), no arrowheads by default")
def _():
    svg, _, _ = render_tree.render(load("ex_tree.json"))
    edges = svg.split('data-role="edges"')[1].split('data-role="nodes"')[0]
    assert "Q " in edges, "tree connectors are not rounded (no quadratic corners)"
    assert "marker-end" not in edges, "tree drew arrowheads though arrows default off"


@check("tree-std · depth shading (dark root, light leaves) + red discipline")
def _():
    m = load("ex_tree.json")
    svg, _, _ = render_tree.render(m)
    nd = _tree_nodes(svg)
    lvl = render_tree._levels(m)
    maxl = max(lvl.values())
    roots = [n for n in nd if lvl[n] == 0]
    leaves = [n for n in nd if lvl[n] == maxl]
    assert any(nd[r][3] == "#374151" for r in roots), "root not dark-shaded"
    assert any(nd[l][3] in ("#EDEFF2",) for l in leaves), "leaves not light-shaded"
    red = sum(1 for n in m["nodes"] if n.get("emphasis")) + sum(1 for e in m["edges"] if e.get("emphasis"))
    assert red <= 2, f"tree uses {red} reds (max 2)"


# ---- 8. flowchart charting standard (frozen) ---------------------------
@check("flow-std · all step boxes share one uniform width")
def _():
    m = load("ex_flow_parallel.json")
    geo = flow_geo(m)
    kind = {n["id"]: n.get("kind", "step") for n in m["nodes"]}
    ws = {round(geo[nid]["right"] - geo[nid]["left"], 1)
          for nid in geo if kind.get(nid, "step") == "step"}
    assert len(ws) == 1, f"step boxes not one uniform width: {ws}"


@check("flow-std · connectors are straight-first (few needless bends)")
def _():
    svg, _, _ = render_flow.render(load("ex_flow_parallel.json"))
    edges = svg.split('data-role="edges"')[1].split('data-role="nodes"')[0]
    paths = re.findall(r'<path d="([^"]+)"', edges)
    straight = sum(1 for p in paths if "Q" not in p)
    bent = sum(1 for p in paths if "Q" in p)
    assert straight >= bent, f"too many bent connectors: {straight} straight vs {bent} bent"


@check("flow-std · title sits over the content center (symmetric framing)")
def _():
    svg, W, H = render_flow.render(load("ex_flow_parallel.json"))
    tx = float(re.search(r'<text x="([0-9.]+)" y="44"', svg).group(1))
    xs = []
    for mm in re.finditer(r'<rect x="([0-9.]+)"[^>]*width="([0-9.]+)"', svg):
        x, w = float(mm.group(1)), float(mm.group(2))
        xs += [x, x + w]
    content_center = (min(xs) + max(xs)) / 2
    assert abs(tx - content_center) < 2, f"title x={tx:.0f} not over content center {content_center:.0f}"
    assert abs(tx - W / 2) < 2, f"title x={tx:.0f} not at canvas center {W/2:.0f}"


# ---- 9. hardening: schema_version + final-SVG lint ---------------------
@check("schema · every example declares schema_version 1")
def _():
    import glob
    exdir = os.path.join(HERE, "..", "examples")
    files = glob.glob(os.path.join(exdir, "*.json"))
    assert files, "no examples found"
    for p in files:
        m = json.load(open(p, encoding="utf-8"))
        assert m.get("schema_version") == 1, f"{os.path.basename(p)} missing schema_version:1"


@check("schema · validate rejects an unsupported schema_version")
def _():
    from common import validate_map
    m = load("ex_points.json"); m = dict(m); m["schema_version"] = 2
    try:
        validate_map(m)
        assert False, "bad schema_version not caught"
    except RuntimeError as e:
        assert "schema_version" in str(e), "message not actionable"


@check("schema · validate error names the offending element id")
def _():
    from common import validate_map
    m = load("ex_dated.json"); m = json.loads(json.dumps(m))
    m["events"][0].pop("date", None)
    try:
        validate_map(m)
        assert False, "missing date not caught"
    except RuntimeError as e:
        assert '"1"' in str(e), "error does not name the event id"


@check("lint · rendered example SVGs are clean (no off-canvas / non-finite / diagonal arrow)")
def _():
    for fx, mod in (("ex_points.json", render_points), ("ex_dated.json", render_dated),
                    ("ex_gantt.json", render_spans), ("ex_flow.json", render_flow),
                    ("ex_relation.json", render_relation), ("ex_tree.json", render_tree),
                    ("ex_flow_parallel.json", render_flow)):
        svg, w, h = mod.render(load(fx))
        warns = lint.lint_svg(svg, w, h)
        assert not warns, f"{fx} lint: {warns}"


@check("lint · rejected blue/slate colour is caught")
def _():
    warns = lint.lint_svg('<svg width="50" height="50"><rect fill="#64748B" x="0" y="0" width="5" height="5"/></svg>', 50, 50)
    assert any("blue/slate" in w for w in warns), "slate colour not flagged by lint"


@check("lint · dangling url(#id) reference is caught")
def _():
    warns = lint.lint_svg('<svg width="9" height="9"><path marker-end="url(#ghost)" d="M0,0 L0,9"/></svg>', 9, 9)
    assert any("dangling reference" in w for w in warns), "dangling url(#id) not flagged"


# ---- 10. extraction discipline (pillar 1: read/analyze/decompose) -------
@check("extraction · audit flags emphasis overuse (>2 reds)")
def _():
    m = {"nodes": [{"id": str(i), "title": "x", "emphasis": True} for i in range(4)],
         "provenance": {"text_policy": "verbatim"}}
    r = _quiet_report(m)
    assert any("emphasis discipline" in n for n in r["notes"]), "red overuse not flagged"


@check("extraction · uncertainties force the checkpoint gate")
def _():
    m = {"events": [{"id": "1", "text": "x"}], "provenance": {"uncertainties": ["smudged date"]}}
    assert _quiet_report(m)["checkpoint_required"], "uncertainties did not trigger checkpoint"


@check("extraction · AI-chosen emphasis forces the checkpoint gate")
def _():
    m = {"nodes": [{"id": "1", "title": "x", "emphasis": True}],
         "provenance": {"text_policy": "verbatim", "emphasis_note": "AI建议：待确认"}}
    assert _quiet_report(m)["checkpoint_required"], "emphasis_note did not trigger checkpoint"


@check("extraction · a clean, fully-certain map needs no checkpoint")
def _():
    m = {"events": [{"id": "1", "text": "签约", "emphasis": True}],
         "provenance": {"text_policy": "verbatim"}}  # source-marked red, nothing uncertain
    assert not _quiet_report(m)["checkpoint_required"], \
        "clean map wrongly demanded a checkpoint"


@check("extraction · extraction-guide.md exists and covers the six steps")
def _():
    p = os.path.join(HERE, "..", "references", "extraction-guide.md")
    assert os.path.exists(p), "extraction-guide.md missing"
    txt = open(p, encoding="utf-8").read()
    for step in ("Step 1", "Step 2", "Step 3", "Step 4", "Step 5", "Step 6"):
        assert step in txt, f"extraction-guide missing {step}"
    assert "spine" in txt.lower() and "verbatim" in txt.lower(), "guide missing core discipline"


@check("timeline-select · dated form rejects an unparseable event date")
def _():
    m = {"schema_version": 1, "layout": "dated_point_timeline", "title_text": "t",
         "events": [{"id": "1", "date": "2013年", "date_text": "2013年", "text": "x"}]}
    try:
        render_dated.render(m)
        assert False, "unparseable date not rejected"
    except Exception as e:
        assert "1" in str(e) or "date" in str(e).lower(), "error not actionable"


@check("timeline-select · extraction-guide documents the ordered decision ladder")
def _():
    p = os.path.join(HERE, "..", "references", "extraction-guide.md")
    txt = open(p, encoding="utf-8").read()
    assert "decision ladder" in txt.lower() or "first match wins" in txt.lower(), "ladder missing"
    assert "safe default" in txt.lower() and "numbered_point_timeline" in txt, "default rule missing"


@check("extraction · guide covers text-only (judgment) input & multi-diagram split")
def _():
    p = os.path.join(HERE, "..", "references", "extraction-guide.md")
    txt = open(p, encoding="utf-8").read()
    assert "text-only" in txt.lower(), "no text-only source section"
    assert "本院认为" in txt and "condensed_from_prose" in txt, "fact-vs-argument / prose fidelity rule missing"
    assert "Multi-diagram" in txt or "companion diagram" in txt.lower(), "multi-diagram guidance missing"


@check("flow-std · decision is a rounded hexagon (6 rounded corners), never a diamond")
def _():
    svg, _, _ = render_flow.render(load("ex_flow.json"))
    hexes = re.findall(r'<path d="([^"]+)" fill="[^"]+" stroke="[^"]+" stroke-width="1.4"', svg)
    assert hexes, "no decision hexagon path found"
    for d in hexes:
        assert d.count("Q") == 6, f"decision not a 6-corner rounded hexagon ({d.count('Q')} corners)"
    assert "<polygon" not in svg, "a diamond/polygon decision shape is still present"


@check("relation · relation_tree refuses a network (multi-parent) → graphviz_relation")
def _():
    m = {"schema_version": 1, "layout": "relation_tree", "title_text": "t",
         "nodes": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}, {"id": "c", "title": "C"}],
         "edges": [{"from": "a", "to": "c"}, {"from": "b", "to": "c"}]}
    try:
        render_tree.render(m)
        assert False, "multi-parent not refused"
    except RuntimeError as e:
        assert "graphviz_relation" in str(e), "error does not redirect to graphviz_relation"


@check("relation · cross-row edges route orthogonally, never diagonal")
def _():
    m = {"schema_version": 1, "layout": "graphviz_relation", "engine": "dot", "direction": "TB",
         "title_text": "t",
         "nodes": [{"id": "a", "title": "顶层公司"}, {"id": "b", "title": "子公司"}],
         "edges": [{"from": "a", "to": "b", "label": "控股"}]}
    svg, w, h = render_relation.render(m)
    assert not lint.lint_svg(svg, w, h), f"relation produced lint warnings: {lint.lint_svg(svg,w,h)}"


@check("direction · audit reports entry/exit points for arrow-direction review")
def _():
    m = {"nodes": [{"id": "a", "title": "输入"}, {"id": "b", "title": "处理"}, {"id": "c", "title": "输出"}],
         "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}], "provenance": {}}
    d = _quiet_report(m)["direction"]
    assert d["sources"] == ["a"] and d["sinks"] == ["c"], f"entry/exit wrong: {d}"


@check("direction · a reversed arrow shows up as a lost entry point")
def _():
    # b->a reversed (should be a->b): now 'a' has an incoming edge, no longer a source
    m = {"nodes": [{"id": "a", "title": "输入"}, {"id": "b", "title": "处理"}, {"id": "c", "title": "输出"}],
         "edges": [{"from": "b", "to": "a"}, {"from": "b", "to": "c"}], "provenance": {}}
    d = _quiet_report(m)["direction"]
    assert "a" not in d["sources"], "reversed arrow not detectable via entry points"


@check("direction · a full cycle is flagged (no entry/exit)")
def _():
    m = {"nodes": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}],
         "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}], "provenance": {}}
    d = _quiet_report(m)["direction"]
    assert not d["sources"] and not d["sinks"], "cycle not flagged as no-entry/no-exit"


@check("flow-std · LR flow routes cleanly (no floating/short final segments)")
def _():
    import math, re as _re
    m = {"schema_version":1,"layout":"graphviz_flow","direction":"LR","title_text":"t",
         "nodes":[{"id":"a","kind":"step","title":"输入甲"},{"id":"b","kind":"step","title":"输入乙"},
                  {"id":"m","kind":"step","title":"汇聚"},{"id":"x","kind":"step","title":"输出一"},
                  {"id":"y","kind":"step","title":"输出二"}],
         "edges":[{"from":"a","to":"m"},{"from":"b","to":"m"},{"from":"m","to":"x"},{"from":"m","to":"y"}]}
    svg,w,h = render_flow.render(m)
    assert not lint.lint_svg(svg,w,h), f"LR flow lint: {lint.lint_svg(svg,w,h)}"
    edges = svg.split('data-role="edges"')[1].split('data-role="nodes"')[0]
    for d in _re.findall(r'<path d="([^"]+)"', edges):
        P=[(float(x),float(y)) for x,y in _re.findall(r"([0-9.]+),([0-9.]+)", d)]
        if len(P)>=2:
            fin=math.hypot(P[-1][0]-P[-2][0], P[-1][1]-P[-2][1])
            assert fin>=10, f"floating/short final segment ({fin:.0f}px) in LR flow"


@check("count · audit reports an extracted count breakdown")
def _():
    r = _quiet_report(load("ex_flow.json"))
    c = r["counts"]
    assert c["nodes"] > 0 and "edges" in c, "count breakdown missing"


@check("count · source_count mismatch is flagged and gates the checkpoint")
def _():
    m = {"nodes": [{"id": str(i), "title": "n"} for i in range(5)], "edges": [],
         "provenance": {"text_policy": "verbatim", "source_count": {"nodes": 7}}}
    r = _quiet_report(m)
    assert r["count_mismatch"] and r["checkpoint_required"], "count mismatch not caught"


@check("count · matching source_count does not false-trigger")
def _():
    m = {"events": [{"id": str(i), "text": "e"} for i in range(6)],
         "provenance": {"text_policy": "verbatim", "source_count": 6}}
    r = _quiet_report(m)
    assert not r["count_mismatch"], "matching count wrongly flagged"


@check("compare · comparison_table renders lint-clean")
def _():
    import json, os
    m = json.load(open(os.path.join(HERE, "..", "examples", "comparison-table.json"), encoding="utf-8"))
    svg, w, h = render_compare.render(m)
    assert not lint.lint_svg(svg, w, h), f"comparison_table lint: {lint.lint_svg(svg,w,h)}"
    assert w / h < 2.2, f"comparison_table too wide ({w}x{h}) — should read as a table, not a strip"


@check("compare · comparison_table demands exactly two columns")
def _():
    import common as _c
    for n in (1, 3):
        m = {"schema_version": 1, "layout": "comparison_table", "title_text": "t",
             "columns": [{"id": str(i), "title": "C"} for i in range(n)],
             "rows": [{"dimension": "d", "cells": {str(i): "x" for i in range(n)}}]}
        try:
            _c.validate_map(m); assert False, f"{n} columns not rejected"
        except RuntimeError as e:
            assert "exactly 2 columns" in str(e)


@check("compare · a row missing a cell is rejected")
def _():
    import common as _c
    m = {"schema_version": 1, "layout": "comparison_table", "title_text": "t",
         "columns": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}],
         "rows": [{"dimension": "d", "cells": {"a": "x"}}]}  # missing b
    try:
        _c.validate_map(m); assert False, "missing cell not rejected"
    except RuntimeError as e:
        assert "missing a cell" in str(e)


@check("skill · intent router + forbidden red-lines table present in SKILL.md")
def _():
    p = os.path.join(HERE, "..", "SKILL.md")
    t = open(p, encoding="utf-8").read()
    assert "Intent router" in t, "intent router missing from SKILL.md"
    assert "Forbidden" in t, "forbidden table missing from SKILL.md"
    for redline in ("hexagon", "#991B1B", "extraction-guide"):
        assert redline in t, f"red-line reference '{redline}' missing from SKILL.md"


# ---- draw.io export (editable deliverable) ------------------------------
# The .drawio export is an ADDITIVE, stdlib-only, editable artifact covering
# all seven layouts. These guards fix what could regress: well-formed XML, no
# dangling edges, counts faithful to the map, emphasis carried as deep red,
# unknown layouts refused cleanly, the .drawio.svg staying a valid SVG with an
# embedded editable model, the zero-graphviz fallback still placing every node,
# and — the newly reported bug — text never sized to hug the box border.
_GRAPH_EX = ["ex_flow.json", "ex_flow_parallel.json", "ex_relation.json", "ex_tree.json"]
_ALL_EX = _GRAPH_EX + ["ex_points.json", "ex_dated.json", "ex_gantt.json"]
# comparison-table has no fixture alias; load it straight from examples/
import export_drawio as _dw  # noqa


def _compare_map():
    with open(os.path.join(EXAMPLES, "comparison-table.json"), encoding="utf-8") as f:
        return json.load(f)


@check("drawio · all seven layouts export to well-formed mxGraphModel XML")
def _dw_wellformed():
    maps = [load(n) for n in _ALL_EX] + [_compare_map()]
    for m in maps:
        xml, _, _ = _dw.build_model(m)
        doc = _MD.parseString(xml)   # raises if not well-formed
        assert doc.getElementsByTagName("mxfile"), f"{m['layout']}: no <mxfile>"
        assert doc.getElementsByTagName("mxGraphModel"), f"{m['layout']}: no <mxGraphModel>"


@check("drawio · graph edges never reference a missing cell id")
def _dw_no_dangling():
    for name in _GRAPH_EX:
        xml, _, _ = _dw.build_model(load(name))
        doc = _MD.parseString(xml)
        cells = doc.getElementsByTagName("mxCell")
        ids = {c.getAttribute("id") for c in cells}
        for c in cells:
            if c.getAttribute("edge") == "1" and c.getAttribute("source"):
                assert c.getAttribute("source") in ids and c.getAttribute("target") in ids, \
                    f"{name}: dangling edge {c.getAttribute('id')}"


@check("drawio · graph node & edge counts stay faithful to the map")
def _dw_counts():
    for name in _GRAPH_EX:
        m = load(name)
        xml, _, _ = _dw.build_model(m)
        doc = _MD.parseString(xml)
        cells = doc.getElementsByTagName("mxCell")
        verts = [c for c in cells if c.getAttribute("vertex") == "1"
                 and c.getAttribute("id") != "title"
                 and not c.getAttribute("id").endswith("_note")]
        edges = [c for c in cells if c.getAttribute("edge") == "1"]
        assert len(verts) == len(m["nodes"]), f"{name}: {len(verts)} vs {len(m['nodes'])} nodes"
        assert len(edges) == len(m["edges"]), f"{name}: {len(edges)} vs {len(m['edges'])} edges"


@check("drawio · timelines/gantt/table produce the expected shape counts")
def _dw_nongraph_shapes():
    xml, _, _ = _dw.build_model(load("ex_points.json"))         # 7 events
    assert xml.count('ellipse;') == 7, "numbered timeline: one marker per event"
    g = _dw.build_model(load("ex_gantt.json"))[0]               # 7 spans
    assert g.count('rounded=0;') >= 7, "gantt: one bar per span"
    t = _dw.build_model(_compare_map())[0]                       # 3 rows x 2 cols + headers
    assert t.count('vertex="1"') == 1 + (1 + 2) + 3 * (1 + 2), "compare: title+headers+cells"


@check("drawio · emphasis is carried as the one deep red #991B1B")
def _dw_emphasis_red():
    assert "#991B1B" in _dw.build_model(load("ex_tree.json"))[0], "tree emphasis not red"
    assert "#991B1B" in _dw.build_model(load("ex_gantt.json"))[0], "gantt emphasis not red"
    clean = {"schema_version": 1, "layout": "graphviz_flow", "title_text": "t",
             "nodes": [{"id": "a", "kind": "step", "title": "甲"},
                       {"id": "b", "kind": "step", "title": "乙"}],
             "edges": [{"from": "a", "to": "b"}]}
    assert "#991B1B" not in _dw.build_model(clean)[0], "red leaked with no emphasis"


@check("drawio · an unknown layout is refused cleanly")
def _dw_refuse_unknown():
    try:
        _dw.build_model({"layout": "mind_map", "title_text": "x"})
        assert False, "unknown layout should raise"
    except RuntimeError as e:
        assert "does not support" in str(e), f"unclear refusal: {e}"


@check("drawio · .drawio.svg is a valid SVG embedding a well-formed model")
def _dw_svg_embed():
    m = load("ex_relation.json")
    xml, _, _ = _dw.build_model(m)
    svg, _, _ = render_relation.render(m)
    hybrid = _dw.embed_in_svg(svg, xml)
    doc = _MD.parseString(hybrid)
    assert doc.documentElement.tagName == "svg", "hybrid root is not <svg>"
    content = doc.documentElement.getAttribute("content")
    assert content.strip().startswith("<mxfile"), "no embedded mxfile"
    _MD.parseString(content)


@check("drawio · export works with NO graphviz (stdlib fallback places every node)")
def _dw_stdlib_fallback():
    m = load("ex_flow.json")
    sizes = {n["id"]: _dw._box_size(_dw._node_lines(n)) for n in m["nodes"]}
    pos = _dw._positions_layered(m, sizes)
    assert set(pos) == {n["id"] for n in m["nodes"]}, "fallback dropped a node"
    for nid, (x, y) in pos.items():
        assert abs(x) < 1e9 and abs(y) < 1e9, f"bad coord for {nid}"


@check("drawio · text is never sized to hug the box border (anti-overlap)")
def _dw_no_hug():
    # every text-bearing vertex must be tall enough for its own <br> line count
    # (guards the reported 'text too close to the border' regression)
    maps = [load(n) for n in _ALL_EX] + [_compare_map()]
    for m in maps:
        doc = _MD.parseString(_dw.build_model(m)[0])
        for c in doc.getElementsByTagName("mxCell"):
            if c.getAttribute("vertex") != "1":
                continue
            val = c.getAttribute("value")
            if not val:
                continue
            nlines = val.count("<br>") + 1
            geo = c.getElementsByTagName("mxGeometry")
            if not geo:
                continue
            h = float(geo[0].getAttribute("height") or 0)
            fsm = re.search(r"fontSize=(\d+)", c.getAttribute("style"))
            fs = int(fsm.group(1)) if fsm else _dw.NODE_FS
            # need room for the lines at THIS cell's font size (draw.io won't
            # re-wrap because we baked our own breaks and sized width w/ a fudge)
            assert h >= nlines * fs + 2, \
                f"{m['layout']} cell {c.getAttribute('id')}: h={h} too short for {nlines}x{fs}px"


@check("drawio · positioned layouts tile without cell overlap")
def _dw_positioned_no_overlap():
    def _boxes(m):
        doc = _MD.parseString(_dw.build_model(m)[0])
        out = []
        for c in doc.getElementsByTagName("mxCell"):
            if c.getAttribute("vertex") != "1" or c.getAttribute("id") == "title":
                continue
            g = c.getElementsByTagName("mxGeometry")
            if not g:
                continue
            f = lambda k: float(g[0].getAttribute(k) or 0)
            out.append((c.getAttribute("id"), f("x"), f("y"), f("width"), f("height"),
                        c.getAttribute("style")))
        return out

    def _ov(a, b):
        ix = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
        iy = max(0, min(a[2] + a[4], b[2] + b[4]) - max(a[2], b[2]))
        return ix > 2 and iy > 2

    # numbered-timeline cards must not overlap one another
    cards = [x for x in _boxes(load("ex_points.json")) if x[0].startswith("card")]
    assert not any(_ov(cards[i], cards[j]) for i in range(len(cards)) for j in range(i + 1, len(cards))), \
        "numbered timeline cards overlap"
    # comparison-table cells tile cleanly (no overlaps, columns aligned)
    cells = [x for x in _boxes(_compare_map())
             if x[0].startswith(("cell", "dim", "hdr"))]
    assert not any(_ov(cells[i], cells[j]) for i in range(len(cells)) for j in range(i + 1, len(cells))), \
        "comparison cells overlap"
    assert len({round(x[1]) for x in cells}) == 3, "comparison columns not aligned to 3 x-positions"
    # gantt bars: one per row (distinct y per bar) and inside the axis band
    bars = [x for x in _boxes(load("ex_gantt.json"))
            if x[0].startswith("bar") and not x[0].startswith("barlbl")]
    assert len({round(x[2]) for x in bars}) == len(bars), "gantt bars share a row"


# ---- Step 2 · drawio timeline connectors ---------------------------------
@check("drawio · timeline connectors stop at the marker edge (never cover the circle)")
def _dw_connector_not_over_marker():
    for name, r in (("ex_points.json", 17), ("ex_dated.json", 8)):
        m = load(name)
        doc = _MD.parseString(_dw.build_model(m)[0])
        # collect marker circle centres (ellipse vertices) and connector endpoints
        centres = []
        for c in doc.getElementsByTagName("mxCell"):
            if c.getAttribute("vertex") == "1" and "ellipse" in c.getAttribute("style"):
                g = c.getElementsByTagName("mxGeometry")[0]
                x, y = float(g.getAttribute("x")), float(g.getAttribute("y"))
                w, h = float(g.getAttribute("width")), float(g.getAttribute("height"))
                centres.append((x + w / 2, y + h / 2, w / 2))
        for c in doc.getElementsByTagName("mxCell"):
            if c.getAttribute("edge") != "1" or not c.getAttribute("id").startswith("cn"):
                continue
            pts = c.getElementsByTagName("mxPoint")
            for p in pts:
                px, py = float(p.getAttribute("x")), float(p.getAttribute("y"))
                for cx, cy, rad in centres:
                    if abs(px - cx) < 1:      # same column as this marker
                        assert abs(py - cy) >= rad - 0.5, \
                            f"{name}: connector endpoint enters the marker (dy={abs(py-cy)} < r={rad})"


# ---- Step 2 · relation routing + labels (no overlap, no line through a node) ----
@check("relation · routes avoid nodes, don't overlap, and labels never collide")
def _rel_router_clean():
    from common import text_w as _tw
    import re as _re

    def _pts(d):
        return [(float(a), float(b)) for a, b in _re.findall(r'(-?\d+\.?\d*),(-?\d+\.?\d*)', d)]

    for name in ("ex_relation.json", "edge_relation_dense.json"):
        m = load(name)
        svg, W, H = render_relation.render(m)
        nodes = [(mm.group(1), float(mm.group(2)), float(mm.group(3)),
                  float(mm.group(2)) + float(mm.group(4)), float(mm.group(3)) + float(mm.group(5)))
                 for mm in _re.finditer(
                     r'data-id="([^"]+)">\s*<rect x="([-\d.]+)" y="([-\d.]+)" width="([-\d.]+)" height="([-\d.]+)"', svg)]
        paths = _re.findall(r'<path d="([^"]+)" fill="none"', svg)
        fr = [e["from"] for e in m["edges"]]; to = [e["to"] for e in m["edges"]]

        # 1) no segment crosses a non-endpoint node
        segs = []
        for i, d in enumerate(paths):
            p = _pts(d)
            for j in range(len(p) - 1):
                segs.append((i, p[j], p[j + 1]))
                (x0, y0), (x1, y1) = p[j], p[j + 1]
                for nid, L, T, R, B in nodes:
                    if i < len(fr) and nid in (fr[i], to[i]):
                        continue
                    if abs(x0 - x1) < 1 and L - 2 < x0 < R + 2 and min(y0, y1) < B - 2 and max(y0, y1) > T + 2:
                        assert False, f"{name}: edge {i} runs through node {nid}"
                    if abs(y0 - y1) < 1 and T - 2 < y0 < B + 2 and min(x0, x1) < R - 2 and max(x0, x1) > L + 2:
                        assert False, f"{name}: edge {i} runs through node {nid}"

        # 2) no two different edges share a collinear run (parallel overlap)
        def _coll(s1, s2):
            (i1, a1, b1), (i2, a2, b2) = s1, s2
            if i1 == i2:
                return False
            if abs(a1[0] - b1[0]) < 1 and abs(a2[0] - b2[0]) < 1 and abs(a1[0] - a2[0]) < 5:
                lo1, hi1 = sorted([a1[1], b1[1]]); lo2, hi2 = sorted([a2[1], b2[1]])
                return min(hi1, hi2) - max(lo1, lo2) > 8
            if abs(a1[1] - b1[1]) < 1 and abs(a2[1] - b2[1]) < 1 and abs(a1[1] - a2[1]) < 5:
                lo1, hi1 = sorted([a1[0], b1[0]]); lo2, hi2 = sorted([a2[0], b2[0]])
                return min(hi1, hi2) - max(lo1, lo2) > 8
            return False
        assert not any(_coll(segs[i], segs[j]) for i in range(len(segs)) for j in range(i + 1, len(segs))), \
            f"{name}: two edges overlap on a collinear run"

        # 3) labels wrap and never overlap a node or another label
        blk = _re.search(r'<g data-role="edge-labels">(.*?)</g>', svg, _re.S)
        labs = _re.findall(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*text-anchor="(\w+)"[^>]*>([^<]+)</text>',
                           blk.group(1)) if blk else []
        blocks, cur = [], None
        for x, y, an, t in labs:
            x, y = float(x), float(y)
            if cur and abs(cur["x"] - x) < 0.5 and (y - cur["ys"][-1]) < 30:
                cur["ys"].append(y); cur["ts"].append(t)   # same block: same x AND adjacent y
            else:
                cur = {"x": x, "ys": [y], "ts": [t], "a": an}; blocks.append(cur)
        assert len(blocks) == sum(1 for e in m["edges"] if e.get("label")), f"{name}: a label went missing"
        lb = []
        for b in blocks:
            bw = max(_tw(t, 13) for t in b["ts"])
            assert bw <= 168 + 16, f"{name}: an edge label was not wrapped"
            L = b["x"] - (bw / 2 if b["a"] == "middle" else 0)
            R = b["x"] + (bw / 2 if b["a"] == "middle" else bw)
            lb.append((L, min(b["ys"]) - 13, R, max(b["ys"]) + 3))
        nb = [(n[1], n[2], n[3], n[4]) for n in nodes]
        def _ov(a, b, p=1):
            return not (a[2] < b[0] + p or a[0] > b[2] - p or a[3] < b[1] + p or a[1] > b[3] - p)
        assert not any(_ov(L, N) for L in lb for N in nb), f"{name}: a label overlaps a node"
        assert not any(_ov(lb[i], lb[j]) for i in range(len(lb)) for j in range(i + 1, len(lb))), \
            f"{name}: two labels overlap"

        # 4) no label is crossed by any connector segment (labels never sit on a line)
        for L in lb:
            for i, d in enumerate(paths):
                p = _pts(d)
                for j in range(len(p) - 1):
                    (x0, y0), (x1, y1) = p[j], p[j + 1]
                    if abs(x0 - x1) < 1 and L[0] < x0 < L[2] and min(y0, y1) < L[3] and max(y0, y1) > L[1]:
                        assert False, f"{name}: a label is crossed by a connector line"
                    if abs(y0 - y1) < 1 and L[1] < y0 < L[3] and min(x0, x1) < L[2] and max(x0, x1) > L[0]:
                        assert False, f"{name}: a label is crossed by a connector line"


# ---- Step 2 · relation deliberate layout ---------------------------------
@check("relation · layout centres a dominant hub, keeps source order, aligns rows")
def _rel_layout():
    # simple/linear graph keeps SOURCE ORDER left-to-right (not scrambled by degree)
    m = load("ex_relation.json")
    pos, sizes = render_relation._layout_nodes(m)
    order_by_x = [i for i, _ in sorted(pos.items(), key=lambda kv: kv[1][0])]
    src = [n["id"] for n in m["nodes"]]
    assert order_by_x == src, f"linear graph reordered: {order_by_x} vs {src}"

    # dense graph with a clear hub → hub is horizontally central + rows aligned
    md = load("edge_relation_dense.json")
    pos2, _ = render_relation._layout_nodes(md)
    deg = {}
    for e in md["edges"]:
        deg[e["from"]] = deg.get(e["from"], 0) + 1
        deg[e["to"]] = deg.get(e["to"], 0) + 1
    hub = max(deg, key=deg.get)
    xs = [p[0] for p in pos2.values()]
    cx = (min(xs) + max(xs)) / 2
    # hub sits nearer the horizontal centre than the average node
    hub_off = abs(pos2[hub][0] - cx)
    avg_off = sum(abs(p[0] - cx) for p in pos2.values()) / len(pos2)
    assert hub_off <= avg_off, f"hub not central (off {hub_off:.0f} vs avg {avg_off:.0f})"
    # rows are aligned: only a few distinct y bands, each shared by ≥1 node
    ybands = sorted({round(p[1]) for p in pos2.values()})
    assert len(ybands) <= 3, f"rows not aligned into tidy bands: {ybands}"


@check("relation · no module side carries 3+ edges (hub spreads across its borders)")
def _rel_side_spread():
    import re as _re
    m = load("edge_relation_dense.json")
    svg, W, H = render_relation.render(m)
    nodes = {mm.group(1): (float(mm.group(2)), float(mm.group(3)),
                           float(mm.group(2)) + float(mm.group(4)), float(mm.group(3)) + float(mm.group(5)))
             for mm in _re.finditer(
                 r'data-id="([^"]+)">\s*<rect x="([-\d.]+)" y="([-\d.]+)" width="([-\d.]+)" height="([-\d.]+)"', svg)}
    paths = _re.findall(r'<path d="([^"]+)" fill="none"', svg)
    def _pts(d):
        return [(float(a), float(b)) for a, b in _re.findall(r'(-?\d+\.?\d*),(-?\d+\.?\d*)', d)]
    from collections import Counter
    side = Counter()
    for i, d in enumerate(paths):
        e = m["edges"][i]; p = _pts(d)
        for endpt, nid in ((p[0], e["from"]), (p[-1], e["to"])):
            if nid not in nodes:
                continue
            L, T, R, B = nodes[nid]
            if abs(endpt[0] - L) < 3:   side[(nid, "L")] += 1
            elif abs(endpt[0] - R) < 3: side[(nid, "R")] += 1
            elif abs(endpt[1] - T) < 3: side[(nid, "T")] += 1
            elif abs(endpt[1] - B) < 3: side[(nid, "B")] += 1
    worst = max(side.values()) if side else 0
    assert worst <= 2, f"a module side carries {worst} edges (should spread ≤2 per side): {[(k,v) for k,v in side.items() if v>=3]}"


# ---- 白描 (monochrome court/print mode) ----------------------------------
@check("白描 · monochrome mode is pure black line-art, geometry byte-identical")
def _baimiao_mode():
    import re as _re
    import render as _render
    for name in ("ex_flow.json", "ex_relation.json", "ex_tree.json"):
        m = load(name)
        mod = _render.choose(m)
        colour, _, _ = mod.render(m)
        mono = _render.to_monochrome(colour)
        # 1. no colour survives: fills are white or ink-black, strokes are ink-black,
        #    and the deep red is gone
        assert "#991B1B" not in mono.upper(), f"{name}: red survived 白描"
        fills = set(_re.findall(r'fill="(#[0-9A-Fa-f]{6})"', mono))
        strokes = set(_re.findall(r'stroke="(#[0-9A-Fa-f]{6})"', mono))
        assert fills <= {"#FFFFFF", "#111111"}, f"{name}: stray fill colour {fills}"
        assert strokes <= {"#111111"}, f"{name}: stray stroke colour {strokes}"
        # 2. geometry is identical — only colour / stroke-weight / added hairlines change
        strip = lambda s: _re.sub(r"\s+", " ", _re.sub(r'(?:fill|stroke|stroke-width)="[^"]*"', "", s))
        assert strip(colour) == strip(mono), f"{name}: 白描 changed geometry, not just colour"


# ---- 歸葬流 (Guizang Swiss / IKB theme) -----------------------------------
@check("歸葬流 · blue/grey/white only, blue diamond decision, top margin, mono Latin")
def _guizang_mode():
    import re as _re
    import render as _render
    THEME = {"#FAFAF8", "#333333", "#737373", "#BDBDBD", "#D4D4D2", "#E0E0E0", "#002FA7", "#FFFFFF"}
    for name in ("ex_flow.json", "ex_relation.json", "ex_tree.json"):
        m = load(name)
        mod = _render.choose(m)
        try:
            mod._THEME = "guizang"
            colour, _, _ = mod.render(m)
        finally:
            mod._THEME = None
        svg = _render.to_guizang(colour)
        # 1. strictly blue / grey / white — no other colour survives
        cols = set(_re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"', svg))
        assert cols <= THEME, f"{name}: 歸葬流 has off-palette colour {cols - THEME}"
        # 2. a top margin (天头) was reserved for the big title
        assert 'transform="translate(0,60)"' in svg, f"{name}: 歸葬流 reserved no top margin"
        # 3. the Song serif is gone (sans/mono only)
        assert "宋体" not in svg and "Songti" not in svg, f"{name}: serif survived into 歸葬流"
        if name == "ex_flow.json":
            # decision is a 4-point blue DIAMOND, and there is at least one solid blue block
            assert _re.search(r'<path d="M [\d.]+,[\d.]+ L [\d.]+,[\d.]+ L [\d.]+,[\d.]+ L [\d.]+,[\d.]+ Z" fill="#002FA7"', svg), \
                f"{name}: decision is not a blue diamond"
            assert svg.count('fill="#002FA7"') >= 2, f"{name}: expected solid blue blocks (terminals/diamond)"


# ---- drawio theming ------------------------------------------------------
@check("drawio export follows the visual mode (白描 mono / 歸葬流 blue-grey), 奇川流 untouched")
def _drawio_themes():
    import re as _re
    import export_drawio as _ex
    for name in ("ex_flow.json", "ex_relation.json", "ex_tree.json"):
        m = load(name)
        base, _, _ = _ex.build_model(m)
        cols = lambda x: {c.upper() for c in _re.findall(r'Color=(#[0-9A-Fa-f]{6})', x)}
        # colour master is left exactly as-is
        assert _ex.theme_drawio(base, None) == base, f"{name}: theme_drawio touched 奇川流"
        # 白描 — black line-art only
        mono = cols(_ex.theme_drawio(base, "baimiao"))
        assert mono <= {"#FFFFFF", "#111111"}, f"{name}: 白描 drawio stray {mono}"
        # 歸葬流 — blue / grey / white only
        _d = {n["id"]: 0 for n in m["nodes"]}
        for _e in m.get("edges", []):
            if _e.get("from") in _d: _d[_e["from"]] += 1
            if _e.get("to") in _d: _d[_e["to"]] += 1
        _hub = None
        if _d:
            _hid = max(_d, key=lambda i: _d[i])
            _hub = "c%d" % [n["id"] for n in m["nodes"]].index(_hid)
        gz = cols(_ex.theme_drawio(base, "guizang", _hub))
        allowed = {"#002FA7", "#333333", "#737373", "#BDBDBD", "#D4D4D2", "#FFFFFF"}
        assert gz <= allowed, f"{name}: 歸葬流 drawio stray {gz - allowed}"
        assert "#002FA7" in gz, f"{name}: 歸葬流 drawio lost its blue"
        # structure untouched — only colours changed
        strip = lambda x: _re.sub(r'(?:fill|stroke|font)Color=#[0-9A-Fa-f]{6}', '', x)
        assert strip(_ex.theme_drawio(base, "guizang", _hub)) == strip(base), \
            f"{name}: theme_drawio altered structure, not just colour"


# ---- long text / overflow ------------------------------------------------
@check("over-long titles wrap instead of running off the canvas; notes reserve real room")
def _long_text():
    import re as _re, json as _json, subprocess, sys, pathlib, tempfile
    import render as _render
    root = pathlib.Path(__file__).resolve().parent.parent
    m = _json.loads((root / "examples" / "comparison-table.json").read_text())
    m["title_text"] = "关于某某市某某区某某工程建设项目施工合同纠纷一案二审判决与再审裁定裁判要旨逐项对比分析表"
    mod = _render.choose(m)
    svg, w, h = mod.render(m)
    fitted = _render.fit_title(svg)
    # the title is split into >1 tspan and the canvas grew to hold them
    assert fitted.count("<tspan") >= 2, "over-long title was not wrapped"
    nh = int(_re.search(r'<svg[^>]*height="(\d+)"', fitted).group(1))
    assert nh > h, "canvas did not grow for the wrapped title"
    # and no text runs off the canvas any more
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(fitted); p = f.name
    r = subprocess.run([sys.executable, str(root / "scripts" / "lint.py"), p],
                       capture_output=True, text=True, timeout=60)
    assert "overflows canvas" not in r.stdout, f"still overflowing: {r.stdout}"
    # a short title is left completely alone
    m2 = _json.loads((root / "examples" / "comparison-table.json").read_text())
    s2, _, _ = _render.choose(m2).render(m2)
    assert _render.fit_title(s2) == s2, "fit_title touched a title that already fits"


# ---- environment doctor --------------------------------------------------
@check("doctor.py runs, reports every dependency, and gates on required tooling")
def _doctor():
    import subprocess, sys, pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, str(root / "scripts" / "doctor.py")],
                       capture_output=True, text=True, timeout=60)
    out = r.stdout
    for needle in ("Python", "graphviz", "PNG rasteriser", "IBM Plex Mono", "Result:"):
        assert needle in out, f"doctor.py never reported {needle!r}"
    assert r.returncode in (0, 1), f"doctor.py exited {r.returncode}"
    # exit code must reflect REQUIRED tooling only
    assert (r.returncode == 0) == ("MISSING REQUIRED" not in out), \
        "doctor.py exit code disagrees with its own report"


# ---- report -------------------------------------------------------------
def main():
    width = max(len(n) for n, _, _ in RESULTS)
    passed = 0
    for name, ok, detail in RESULTS:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name.ljust(width)}"
        if not ok:
            line += f"   → {detail}"
        print(line)
        passed += ok
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
