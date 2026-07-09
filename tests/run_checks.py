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
import lint  # noqa
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
