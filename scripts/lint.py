#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Final-SVG lint — the artifact-level checks that are easiest to miss on a
fixture but obvious in a browser (inspired by Archify's check-render-output).
Read-only: it inspects the produced SVG and reports warnings; it never changes
how anything is drawn.

Checks:
  1. non-finite numbers leaked into attributes (nan / inf / None)
  2. elements whose box falls outside the canvas (clipping)
  3. arrows drawn as a single diagonal line (should be orthogonal)

Usage:  python lint.py <file.svg>       (exit 1 if any warning)
        from render.py: lint_svg(svg, w, h) -> list[str]
"""
import sys, re

_NUM = r'-?\d+(?:\.\d+)?'

# Explicitly-rejected blue / slate families (Tailwind slate + common blues). Our
# own neutral grays are mildly cool and are intentionally NOT in this list.
_REJECTED_BLUE = {
    "#0F172A", "#1E293B", "#334155", "#475569", "#64748B", "#94A3B8",
    "#CBD5E1", "#E2E8F0", "#F1F5F9", "#0EA5E9", "#3B82F6", "#2563EB",
    "#1D4ED8", "#1E40AF", "#60A5FA", "#93C5FD",
}


def _canvas(svg):
    m = re.search(r'<svg[^>]*width="(\d+)"[^>]*height="(\d+)"', svg)
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


def lint_svg(svg, w=None, h=None):
    warns = []
    if w is None or h is None:
        w, h = _canvas(svg)

    # 1. non-finite numbers in numeric attributes (case-sensitive: Python emits
    #    'nan'/'inf'; capital 'None' won't collide with the valid fill="none")
    if re.search(r'"[^"]*\b(?:nan|inf|Infinity|NaN|None)\b[^"]*"', svg):
        warns.append("non-finite value (nan/inf/None) leaked into an SVG attribute")

    # 2. off-canvas boxes (rects) and text anchors
    if w and h:
        tol = 2.0
        for mm in re.finditer(
                rf'<rect x="({_NUM})" y="({_NUM})" width="({_NUM})" height="({_NUM})"', svg):
            x, y, ww, hh = map(float, mm.groups())
            if x < -tol or y < -tol or x + ww > w + tol or y + hh > h + tol:
                warns.append(f"rect off-canvas at x={x:.0f},y={y:.0f} ({ww:.0f}x{hh:.0f}) vs {w:.0f}x{h:.0f}")
        for mm in re.finditer(rf'<text x="({_NUM})" y="({_NUM})"', svg):
            x, y = float(mm.group(1)), float(mm.group(2))
            if x < -tol or y < -tol or x > w + tol or y > h + tol:
                warns.append(f"text anchor off-canvas at x={x:.0f},y={y:.0f} vs {w:.0f}x{h:.0f}")

    # 3. arrowed path that is a single diagonal segment (should be orthogonal)
    for mm in re.finditer(r'<path d="([^"]+)"[^>]*marker-end=', svg):
        d = mm.group(1)
        pts = re.findall(rf'({_NUM}),({_NUM})', d)
        if "Q" not in d and len(pts) == 2:
            (x1, y1), (x2, y2) = ([float(a) for a in p] for p in pts)
            if abs(x1 - x2) > 1.5 and abs(y1 - y2) > 1.5:
                warns.append(f"diagonal arrow ({x1:.0f},{y1:.0f})->({x2:.0f},{y2:.0f}) — should be orthogonal")

    # 4. rejected blue / slate palette (the "no blue" standard, as an artifact check).
    #    A blacklist, not a blue-channel test — our neutral grays are mildly cool and
    #    must not be false-flagged; only the explicitly-rejected families are caught.
    for mm in re.finditer(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"', svg):
        if mm.group(1).upper() in _REJECTED_BLUE:
            warns.append(f"rejected blue/slate colour {mm.group(1)} (palette is neutral gray + one deep red)")

    # 5. marker sanity: orient must be "auto" (never the deprecated auto-start-reverse)
    for mm in re.finditer(r'<marker\b[^>]*>', svg):
        if 'auto-start-reverse' in mm.group(0) or 'orient="auto"' not in mm.group(0):
            warns.append("marker orient is not \"auto\" (deprecated/absent orient rotates arrows wrong)")

    # 6. well-formed XML (a malformed SVG rasterizes to nothing)
    try:
        import xml.etree.ElementTree as ET
        ET.fromstring(svg)
    except Exception as e:
        warns.append(f"SVG is not well-formed XML: {e}")

    # 7. reference integrity: every url(#id) must resolve to a defined id
    defined = set(re.findall(r'\bid="([^"]+)"', svg))
    for ref in re.findall(r'url\(#([^)]+)\)', svg):
        if ref not in defined:
            warns.append(f'dangling reference url(#{ref}) — no element defines id="{ref}"')

    # de-dupe while keeping order
    seen, out = set(), []
    for wn in warns:
        if wn not in seen:
            seen.add(wn); out.append(wn)
    return out


def main(path):
    svg = open(path, encoding="utf-8").read()
    warns = lint_svg(svg)
    if warns:
        print(f"lint: {len(warns)} warning(s) in {path}")
        for w in warns:
            print("  - " + w)
        return 1
    print(f"lint: clean — {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
