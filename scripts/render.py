#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point: semantic-map.json -> final.svg (+ final.png).

    python render.py <semantic-map.json> [out_basename]

Picks the layout from the map:
    layout == "numbered_point_timeline"  -> render_points
    layout == "proportional_gantt"       -> render_spans
(falls back to heuristics if `layout` is absent).

SVG is the primary, editable deliverable. PNG is derived for preview/filing.
"""
import sys, os, re, shutil, subprocess
from common import load_map, validate_map, TITLE_FONT
import render_points, render_spans, render_flow, render_relation, render_tree, render_dated, render_compare


def _best_installed_song():
    """LibreOffice does NOT walk the CSS font-family list for CJK: if the first
    family is missing it substitutes its own SANS default (WenQuanYi), ignoring
    the Song faces listed later. So for the PNG we find the best Song ACTUALLY
    installed on this machine and put it first. Priority prefers real 方正小标宋
    when present (so a lawyer's own machine renders the true face), then 思源宋/
    Noto Serif, then 华文中宋."""
    try:
        out = subprocess.run(["fc-list"], capture_output=True, text=True).stdout
    except Exception:
        return None
    for fam in ("方正小标宋", "FZXiaoBiaoSong", "思源宋体", "Source Han Serif SC",
                "Noto Serif CJK SC", "华文中宋", "STZhongsong", "Songti SC", "SimSun"):
        if fam in out:
            return fam
    return None


def _png_safe_svg(svg_path):
    """Write a soffice-only copy of the SVG whose title font-family leads with an
    installed Song (see _best_installed_song). The on-disk master SVG is left
    untouched — it keeps 方正小标宋 first for viewers that DO walk the list."""
    song = _best_installed_song()
    src = open(svg_path, encoding="utf-8").read()
    marker = f'font-family="{TITLE_FONT}"'
    if not song or marker not in src:
        return svg_path, None
    new_font = f"'{song}',serif"
    fixed = src.replace(marker, f'font-family="{new_font}"')
    # LibreOffice outlines *stroked* CJK <text> using its sans default (WenQuanYi)
    # instead of the requested Song, so the PNG title came out looking like 黑体.
    # The on-disk master SVG keeps the hairline stroke (renders fine on rsvg /
    # browsers); for the soffice-only copy we drop stroke on the TITLE text alone
    # and rely on the real Bold face (font-weight:700 -> Noto Serif CJK Bold).
    def _strip_title_stroke(m):
        tag = m.group(0)
        tag = re.sub(r'\s+stroke="[^"]*"', '', tag)
        tag = re.sub(r'\s+stroke-width="[^"]*"', '', tag)
        return tag
    fixed = re.sub(r'<text\b[^>]*font-family="' + re.escape(new_font) + r'"[^>]*>',
                   _strip_title_stroke, fixed)
    tmp = os.path.splitext(svg_path)[0] + "__png.svg"
    open(tmp, "w", encoding="utf-8").write(fixed)
    return tmp, tmp



def choose(m):
    layout = m.get("layout", "")
    if layout == "numbered_point_timeline":
        return render_points
    if layout == "dated_point_timeline":
        return render_dated
    if layout == "proportional_gantt":
        return render_spans
    if layout == "graphviz_flow":
        return render_flow
    if layout == "graphviz_relation":
        return render_relation
    if layout == "relation_tree":
        return render_tree
    if layout == "comparison_table":
        return render_compare
    # heuristic fallback
    if m.get("nodes") and m.get("edges"):
        return render_flow
    return render_spans if m.get("spans") else render_points


def svg_to_png(svg_path, png_path, dpi=150):
    """Render SVG -> PNG with whatever is installed. Prefer a real SVG
    rasterizer; fall back to soffice -> PDF -> pdftoppm (works everywhere
    LibreOffice is present, which is the common minimal environment)."""
    def has(x):
        return shutil.which(x) is not None

    if has("rsvg-convert"):
        subprocess.run(["rsvg-convert", "-d", str(dpi), "-p", str(dpi),
                        svg_path, "-o", png_path], check=True)
        return "rsvg-convert"
    if has("resvg"):
        subprocess.run(["resvg", "--dpi", str(dpi), svg_path, png_path], check=True)
        return "resvg"
    if has("inkscape"):
        subprocess.run(["inkscape", svg_path, "--export-type=png",
                        f"--export-dpi={dpi}", f"--export-filename={png_path}"], check=True)
        return "inkscape"
    # LibreOffice SVG -> PDF -> pdftoppm. Preferred over cairosvg for THIS skill
    # because our text is all-CJK: soffice+Noto renders Chinese reliably, whereas
    # cairosvg's Cairo font API does not do fontconfig fallback and can emit □
    # tofu boxes for CJK. So soffice is tried first; cairosvg is the last resort.
    if has("soffice") and has("pdftoppm"):
        outdir = os.path.dirname(os.path.abspath(png_path)) or "."
        src_svg, tmp = _png_safe_svg(svg_path)   # title Song-first so soffice picks a Song, not its sans default
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                        "--outdir", outdir, src_svg], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pdf = os.path.splitext(src_svg)[0] + ".pdf"
        pdf = os.path.join(outdir, os.path.basename(pdf))
        prefix = os.path.splitext(png_path)[0]
        subprocess.run(["pdftoppm", "-png", "-r", str(dpi), pdf, prefix], check=True)
        produced = prefix + "-1.png"
        if os.path.exists(produced):
            os.replace(produced, png_path)
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
        return "soffice+pdftoppm"
    try:
        import cairosvg  # noqa — last resort; may render CJK as tofu (see note above)
        cairosvg.svg2png(url=svg_path, write_to=png_path, dpi=dpi)
        return "cairosvg"
    except Exception:
        pass
    raise RuntimeError("No SVG->PNG renderer found. Install rsvg-convert/resvg/"
                       "inkscape, or LibreOffice(soffice)+pdftoppm (recommended for CJK).")


def main(mapfile, base="final", strict=False):
    m = load_map(mapfile)
    mod = choose(m)
    svg_path = base + ".svg"
    try:
        validate_map(m)
        svg, w, h = mod.render(m)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        return 1
    open(svg_path, "w", encoding="utf-8").write(svg)
    print(f"SVG: {svg_path}  {w}x{h}")
    png_path = base + ".png"
    try:
        engine = svg_to_png(svg_path, png_path)
        print(f"PNG: {png_path}  (via {engine})")
    except Exception as e:
        print(f"PNG skipped: {e}")
    # semantic audit
    try:
        import audit
        audit.report(m)
    except Exception as e:
        print(f"(audit unavailable: {e})")
    # final-SVG visual lint (read-only)
    try:
        import lint
        warns = lint.lint_svg(svg, w, h)
        if warns:
            print(f"lint: {len(warns)} warning(s)")
            for wn in warns:
                print("  - " + wn)
            if strict:
                return 2
        else:
            print("lint: clean")
    except Exception as e:
        print(f"(lint unavailable: {e})")
    return 0


def _cli(argv):
    """Subcommands: `validate <map>`, `lint <svg>`, or the default render."""
    if argv and argv[0] == "validate":
        try:
            validate_map(load_map(argv[1]))
            print(f"validate: OK — {argv[1]}")
            return 0
        except Exception as e:
            print(f"validate: {e}")
            return 1
    if argv and argv[0] in ("lint", "check"):
        import lint
        return lint.main(argv[1])
    strict = "--strict" in argv
    argv = [a for a in argv if a != "--strict"]
    return main(argv[0], argv[1] if len(argv) > 1 else "final", strict=strict)


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]) or 0)
