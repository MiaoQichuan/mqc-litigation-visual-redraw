#!/usr/bin/env python3
"""doctor.py — environment self-check for a fresh clone.

A bare `git clone` gives you the code but not the system tools it shells out to,
and the failures that follow ("dot: not found", a PNG that never appears, a title
in the wrong typeface) are hard to read. Run this first:

    python3 scripts/doctor.py

It reports what is present, what is missing, and exactly what to install — and
tells you which features degrade if you skip an optional item. Exit code is 0 when
everything REQUIRED is present, 1 otherwise, so CI can gate on it.
"""
import shutil
import subprocess
import sys

OK, WARN, BAD = "  ok  ", " warn ", " MISS "


def _has(cmd):
    return shutil.which(cmd) is not None


def _fonts():
    """Return the list of installed font families (best effort, empty if unknown)."""
    if not _has("fc-list"):
        return None
    try:
        out = subprocess.run(["fc-list", "--format", "%{family}\n"],
                             capture_output=True, text=True, timeout=20)
        return out.stdout
    except Exception:
        return None


def main():
    rows, fatal = [], False

    # --- required ---------------------------------------------------------
    py_ok = sys.version_info >= (3, 9)
    rows.append((OK if py_ok else BAD, "Python ≥ 3.9",
                 f"found {sys.version.split()[0]}" if py_ok else "upgrade Python"))
    fatal |= not py_ok

    dot = _has("dot")
    rows.append((OK if dot else BAD, "graphviz (dot)",
                 "flowchart node positioning" if dot else
                 "REQUIRED for flowcharts — apt install graphviz / brew install graphviz"))
    fatal |= not dot

    # --- png rasteriser (any one) -----------------------------------------
    raster = [c for c in ("rsvg-convert", "inkscape", "soffice") if _has(c)]
    if raster:
        rows.append((OK, "PNG rasteriser", f"using {raster[0]}"))
    else:
        rows.append((WARN, "PNG rasteriser",
                     "none found — SVG still renders, PNG preview will not. "
                     "Install one: librsvg2-bin / inkscape / libreoffice"))

    # --- fonts (optional, affect looks only) ------------------------------
    fl = _fonts()
    if fl is None:
        rows.append((WARN, "fonts", "fc-list unavailable — cannot verify typefaces"))
    else:
        song = any(k in fl for k in ("Song", "宋", "SimSun", "Source Han Serif", "Noto Serif CJK"))
        rows.append((OK if song else WARN, "serif CJK (奇川流 titles)",
                     "found" if song else
                     "missing — titles fall back to a default serif; "
                     "install fonts-noto-cjk (or Source Han Serif)"))
        sans = any(k in fl for k in ("Noto Sans CJK", "Noto Sans SC", "Inter",
                                     "PingFang", "Helvetica", "Arial", "DejaVu Sans"))
        rows.append((OK if sans else WARN, "sans CJK (歸葬流 body)",
                     "found" if sans else "missing — install fonts-noto-cjk"))
        mono = "IBM Plex Mono" in fl
        rows.append((OK if mono else WARN, "IBM Plex Mono (歸葬流 numerals)",
                     "found" if mono else
                     "missing — numbers fall back to a generic monospace; "
                     "install IBM Plex Mono for the intended Swiss texture"))

    # --- report -----------------------------------------------------------
    print("\nmqc-litigation-visual-redraw · environment check\n")
    for state, name, note in rows:
        print(f"[{state}] {name:<34} {note}")
    print()
    if fatal:
        print("Result: MISSING REQUIRED TOOLING — install the items marked MISS above.\n")
        return 1
    warns = sum(1 for s, _, _ in rows if s == WARN)
    print(f"Result: ready to render{f' ({warns} optional item(s) degraded)' if warns else ''}.\n")
    print("Next:  python3 scripts/render.py examples/flowchart.json /tmp/out")
    print("       python3 tests/run_checks.py\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
