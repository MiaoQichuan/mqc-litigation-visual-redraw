#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Relationship-diagram renderer. Nodes are parties/entities; edges are labeled,
directed relationships. graphviz (engine chosen per topology) positions the
nodes; we draw the cards, the labeled relationship lines, per-node notes, and
top/bottom skip-routes ourselves (graphviz edge routes are unreliable).

Usage: python render_relation.py <semantic-map.json> <out.svg>
"""
import sys, math, subprocess
from common import C, FONT, FS, TITLE_FONT, TOKENS, esc, wrap, text_w, load_map, arrow_marker

FC = TOKENS["flow_colors"]
FS_TITLE_DOC = FS["doc_title"]
FS_T, FS_NOTE, FS_EDGE = 19, FS["subtitle"], FS["subtitle"]
LH_NOTE = 20
PADX, PADY = 22, 16
NODE_MINW = 150
ARC_GAP = 56          # how far above the row the top-route runs
NOTE_GAP = 30         # gap from node bottom to its note
MARGIN = 72

def tw(s, fs): return text_w(s, fs)

def rounded(pts, r=2.5):
    pts = [p for i, p in enumerate(pts) if i == 0 or abs(p[0]-pts[i-1][0]) > 0.5 or abs(p[1]-pts[i-1][1]) > 0.5]
    if len(pts) < 2:
        return ""
    d = [f'M {pts[0][0]:.1f},{pts[0][1]:.1f}']
    for i in range(1, len(pts)-1):
        p0, p1, p2 = pts[i-1], pts[i], pts[i+1]
        v1 = (p1[0]-p0[0], p1[1]-p0[1]); l1 = math.hypot(*v1) or 1
        v2 = (p2[0]-p1[0], p2[1]-p1[1]); l2 = math.hypot(*v2) or 1
        rr = min(r, l1/2, l2/2)
        a = (p1[0]-v1[0]/l1*rr, p1[1]-v1[1]/l1*rr)
        b = (p1[0]+v2[0]/l2*rr, p1[1]+v2[1]/l2*rr)
        d.append(f'L {a[0]:.1f},{a[1]:.1f} Q {p1[0]:.1f},{p1[1]:.1f} {b[0]:.1f},{b[1]:.1f}')
    d.append(f'L {pts[-1][0]:.1f},{pts[-1][1]:.1f}')
    return " ".join(d)

def node_size(n):
    w = max(NODE_MINW, tw(n["title"], FS_T) + 2*PADX)
    h = FS_T + 2*PADY + 6
    return w, h

def _aliases(m):
    return {n["id"]: f"N{i}" for i, n in enumerate(m["nodes"])}

def build_dot(m):
    al = _aliases(m)
    eng_dir = m.get("direction", "LR")
    L = ['digraph G {', f'  rankdir={eng_dir}; splines=line;',
         '  nodesep=0.9; ranksep=2.0;', '  node [shape=box, fixedsize=true];']
    for n in m["nodes"]:
        w, h = node_size(n)
        L.append(f'  {al[n["id"]]} [label="{al[n["id"]]}", width={w/72:.3f}, height={h/72:.3f}];')
    for e in m["edges"]:
        constraint = "false" if e.get("route") in ("top", "bottom") else "true"
        L.append(f'  {al[e["from"]]} -> {al[e["to"]]} [constraint={constraint}];')
    L.append('}')
    return "\n".join(L)

def run_dot(dot_src, engine="dot"):
    try:
        p = subprocess.run([engine, "-Tplain"], input=dot_src, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise RuntimeError(f"graphviz '{engine}' not found on PATH. Relationship "
                           "layouts need graphviz — install it (e.g. `apt-get "
                           "install graphviz`).")
    nodes, gw, gh = {}, 0.0, 0.0
    for ln in p.stdout.splitlines():
        t = ln.split()
        if t and t[0] == "graph":
            gw, gh = float(t[2]), float(t[3])
        elif t and t[0] == "node":
            nodes[t[1]] = (float(t[2]), float(t[3]), float(t[4]), float(t[5]))
    return nodes, gw, gh

def render(m):
    engine = m.get("engine", "dot")
    raw, gw, gh = run_dot(build_dot(m), engine)
    inv = {v: k for k, v in _aliases(m).items()}
    nodes = {inv[a]: pos for a, pos in raw.items()}
    S = lambda v: v*72
    by_id = {n["id"]: n for n in m["nodes"]}

    # geometry in a top-origin space, leaving room for title, top arcs, notes
    title_zone = 102
    top_room = ARC_GAP + 26
    note_room = NOTE_GAP + 2*LH_NOTE + 20
    W = S(gw) + 2*MARGIN
    Yflip = lambda y: (gh - y)*72
    yoff = title_zone + top_room + MARGIN*0.2
    H = S(gh) + title_zone + top_room + note_room + MARGIN

    geo = {}
    for nid, (x, y, w, h) in nodes.items():
        cx, cy = S(x) + MARGIN, Yflip(y) + yoff
        geo[nid] = {"cx": cx, "cy": cy, "w": S(w), "h": S(h),
                    "top": cy - S(h)/2, "bottom": cy + S(h)/2,
                    "left": cx - S(w)/2, "right": cx + S(w)/2}

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" viewBox="0 0 {W:.0f} {H:.0f}" font-family="{FONT}">',
           '<defs>' + arrow_marker('ag', C["line"]) + arrow_marker('ar', C["red"], size=14, refX=11) + '</defs>',
           f'<rect width="{W:.0f}" height="{H:.0f}" fill="{C["bg"]}"/>',
           f'<text x="{W/2:.0f}" y="46" font-size="{FS_TITLE_DOC}" font-weight="700" font-family="{TITLE_FONT}" '
           f'fill="{C["ink"]}" stroke="{C["ink"]}" stroke-width="0.3" text-anchor="middle">{esc(m["title_text"])}</text>']

    # edges
    out.append('<g data-role="edges">')
    for e in m["edges"]:
        a, b = geo[e["from"]], geo[e["to"]]
        emph = e.get("emphasis")
        col = C["red"] if emph else C["line"]
        sw = 3 if emph else 2
        mk = "url(#ar)" if emph else "url(#ag)"
        route = e.get("route", "straight")
        GAP = 4
        if route == "top":
            ty = min(a["top"], b["top"]) - ARC_GAP
            pts = [(a["cx"], a["top"]), (a["cx"], ty), (b["cx"], ty), (b["cx"], b["top"] - GAP)]
            lx, ly = (a["cx"] + b["cx"]) / 2, ty - 8
            anchor = "middle"
        elif route == "bottom":
            ty = max(a["bottom"], b["bottom"]) + ARC_GAP
            pts = [(a["cx"], a["bottom"]), (a["cx"], ty), (b["cx"], ty), (b["cx"], b["bottom"] + GAP)]
            lx, ly = (a["cx"] + b["cx"]) / 2, ty + 18
            anchor = "middle"
        else:  # a direct relationship edge
            if abs(a["cy"] - b["cy"]) < 4:
                # same row -> clean horizontal between the two cards
                if b["left"] >= a["right"] - 1:
                    x0, x1 = a["right"], b["left"] - GAP
                else:
                    x0, x1 = a["left"], b["right"] + GAP
                pts = [(x0, a["cy"]), (x1, b["cy"])]
                lx, ly = (x0 + x1) / 2, a["cy"] - 10
            else:
                # different rows -> orthogonal (down/up, across, in), never a diagonal
                if b["cy"] > a["cy"]:
                    y0, y1 = a["bottom"], b["top"] - GAP
                else:
                    y0, y1 = a["top"], b["bottom"] + GAP
                midy = (y0 + y1) / 2
                pts = [(a["cx"], y0), (a["cx"], midy), (b["cx"], midy), (b["cx"], y1)]
                lx, ly = (a["cx"] + b["cx"]) / 2, midy - 8
            anchor = "middle"
        d = rounded(pts)
        out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{sw}" marker-end="{mk}"/>')
        if e.get("label"):   # text only, no box, placed off the line (top routes sit above the arc)
            lcol = C["red"] if emph else C["ink2"]
            out.append(f'<text x="{lx:.1f}" y="{ly+2:.1f}" font-size="{FS_EDGE}" font-weight="{"700" if emph else "600"}" '
                       f'fill="{lcol}" text-anchor="{anchor}">{esc(e["label"])}</text>')
    out.append('</g>')

    # nodes + notes
    out.append('<g data-role="nodes">')
    for nid, g in geo.items():
        n = by_id[nid]
        out.append(f'<g data-role="node" data-id="{nid}">')
        out.append(f'<rect x="{g["left"]:.1f}" y="{g["top"]:.1f}" width="{g["w"]:.1f}" height="{g["h"]:.1f}" '
                   f'rx="12" fill="{FC["step_fill"]}" stroke="{FC["step_stroke"]}" stroke-width="1.4"/>')
        out.append(f'<text x="{g["cx"]:.1f}" y="{g["cy"]+FS_T*0.35:.1f}" font-size="{FS_T}" font-weight="700" '
                   f'fill="{C["ink"]}" text-anchor="middle">{esc(n["title"])}</text>')
        if n.get("note"):
            nlines = wrap(n["note"], FS_NOTE, g["w"] + 80)
            ny = g["bottom"] + NOTE_GAP
            for ln in nlines:
                out.append(f'<text x="{g["cx"]:.1f}" y="{ny:.1f}" font-size="{FS_NOTE}" fill="{C["ink2"]}" '
                           f'text-anchor="middle">{esc(ln)}</text>')
                ny += LH_NOTE
        out.append('</g>')
    out.append('</g></svg>')
    return "\n".join(out), int(W), int(H)

def main(mapfile, out):
    svg, w, h = render(load_map(mapfile))
    open(out, "w", encoding="utf-8").write(svg)
    print(f"[relation] wrote {out}  {w}x{h}  ratio={w/h:.2f}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "out.svg")
