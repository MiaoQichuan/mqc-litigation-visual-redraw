---
name: mqc-litigation-visual-redraw
metadata:
  author: 缪奇川
  version: 1.0.0
  last_updated: 2026-07-09
description: >-
  Redraw a litigation diagram into a restrained, court-ready presentation
  graphic (SVG + PNG) WITHOUT changing any text or legal meaning. Use this
  whenever the user supplies a case timeline, a legal process flowchart, OR a
  party/relationship diagram and wants it cleaned up, beautified, redrawn, made
  professional, de-cluttered, recolored, or turned into an exhibit for a
  complaint / hearing / arbitration. Timelines: fact chronology (事实经过时间轴),
  limitation/guarantee-period chart (诉讼时效/保证期间), gantt-style period chart.
  Flowcharts: case procedure / litigation process / claim-basis / attack-defense
  path (案件法律流程图). Relationship diagrams: parties and their legal
  relationships (当事人关系图 / 担保法律关系 / 股权·资金·控制关系). Also use it when the
  user hands over raw case facts and asks for such a graphic. Trigger even if the
  user only says "把这张图重画/美化一下", "做成诉讼材料能用的图", or "generate a case
  timeline/flowchart/relationship diagram" without naming this skill. Default
  scenario is Chinese litigation; internal instructions are in English.
---

# Litigation visual redraw

This skill is **`mqc-litigation-visual-redraw`** — the first open-source module of
**新诉讼可视化 · New Litigation Visualization** (slogan: 把法律画出来 · *Make the Law
Visible*), 缪奇川's litigation-visualization project. It takes an ugly / hand-drawn /
"AI-flavored" source — or even plain judgment text — and **redraws** it into a
standard legal diagram (timeline · flowchart · relationship). This module stands alone.

Turn a messy or generic litigation diagram into a calm, professional legal
graphic. The guiding idea (先吃透，再重画): **first understand the source
faithfully, then redraw it — never change the wording and never change the legal
meaning; only improve the visual expression.** Method, in the spirit of
mqc-legal-skills: scenario is vertical, the SOP is tight, the output should look
like a McKinsey exhibit, not a student's slide.

Scope: **timelines** (three forms — numbered, dated, gantt), **flowcharts**, and
**relationship diagrams** (free-form network + hierarchical tree; a two-column
**comparison table** is the A-vs-B variant of the relationship family). All are
frozen and share one visual language. **This skill draws these three families and
nothing else — do not invent new diagram types.**

## Intent router (what to read first)

Read `SKILL.md` + `references/STANDARDS.md` always. Then, by intent, open only what
you need (don't preload everything):

| The user gives / wants | Read this | Then |
|---|---|---|
| An ugly / hand-drawn / screenshot / AI-style diagram, OR plain text / a judgment to turn into a diagram | `references/extraction-guide.md` (read→analyze→decompose, six steps) | pick a layout below |
| A **timeline** (events over time) | extraction-guide Step 1 **timeline decision ladder** | `numbered` / `dated` / `gantt` |
| A **flowchart / process / decision** | `references/flowchart-spec.md` | `graphviz_flow` |
| A **relationship / parties / hierarchy** | `references/relationship-spec.md` (tree-vs-network rule) | `graphviz_relation` / `relation_tree` |
| **A vs B** side-by-side comparison | schema `comparison_table` | two columns |
| Field/shape details for the JSON | `references/semantic-map-schema.md` | write JSON |

## Forbidden — never do these (集中红线)

| Never | Do instead |
|---|---|
| Hand-write SVG coordinates / lay out nodes "by eye" | emit JSON; the scripts compute all geometry |
| Blue / slate / any second accent colour | neutral gray + the one deep red `#991B1B` (≤2 uses) |
| A **diamond** decision node | rounded **hexagon** (angled ends, r≈2.5) |
| Put an argument / 本院认为 reasoning / a whole paragraph inside a node | only facts & operative conclusions; reasoning is not a node |
| Change a frozen number (colour, radius, font, spacing) | change it in the owning spec / `style-tokens.json` first |
| Reorder events for looks, merge/drop items, or invent a date | verbatim, time-ordered; unknowns → `provenance.uncertainties` |
| Add a new diagram type / legend / icon / theme | stay within the three families above |

## Golden rule: the model extracts, the scripts draw

Do **not** hand-write SVG coordinates, and do not try to lay out nodes "by eye".
Language models place boxes/arrows badly (overlaps, overflow, crossings), and
this skill must work even on weaker models. So the division of labor is fixed:

- **The model's job**: read the source, transcribe every character verbatim,
  and emit a `semantic-map.json`. Judgement calls (which element is the single
  most important, reading order, above/below placement) live in that JSON.
- **The scripts' job** (`scripts/`): all geometry — column math, date scaling,
  text wrapping, collision-free stacking, styling, and rasterization.

If you follow this split, output quality comes from the JSON being correct, not
from the model being clever about pixels.

## Workflow

1. **Read, analyze, decompose the source** — this is the make-or-break stage of
   this skill (turning an ugly/hand-drawn/cluttered source into a high-grade legal
   diagram lives or dies here). Follow the six-step discipline in
   **`references/extraction-guide.md`**: (1) classify the diagram type → pick the
   layout; (2) find the **spine first** (the axis / the happy path / the core
   party), then hang branches off it — never transcribe left-to-right blindly;
   (3) transcribe **every character verbatim** — dates, labels, evidence numbers;
   do not normalize ("2023年5月左右" stays as is), paraphrase, or merge; (4) strip
   decoration (pie charts, waveforms, icons, flourishes) — this skill re-draws
   STRUCTURE, it does not copy illustrations; (5) pick the single deep-red emphasis
   (≤2); (6) when the source is dense, main structure goes in the diagram and
   sub-notes go to `provenance` — do not cram. Anything you cannot read confidently
   goes into `provenance.uncertainties`, never into a guess.

2. **Write `semantic-map.json`.** Follow `references/semantic-map-schema.md`.
   Preserve original numbering if present; you may add numbering for readability
   and must record that in `provenance`.

3. **CHECKPOINT — confirm the decomposition before rendering.** Show the user the
   extracted spine (the events/nodes/edges you read) and the `uncertainties`, and
   ask them to confirm anything that could change the legal meaning (date order vs.
   source order, unreadable labels, what the single emphasis should be, and — for a
   messy/hand-drawn source — whether your read of the structure is right). This
   checkpoint is **not optional** and matters most on a hand-drawn or dense source
   and on weaker models whose transcription is less reliable; skip it only if the
   user has explicitly said "just render it". See `references/extraction-guide.md`.

4. **Render deterministically.** From `scripts/`:
   ```bash
   python render.py <semantic-map.json> final
   ```
   This picks the layout, writes `final.svg` (primary, editable) and `final.png`
   (preview/filing), and prints an audit summary. Never edit coordinates by
   hand; if something is wrong, fix the JSON or the script, not the SVG output.

5. **Deliver.** Hand over `final.svg` + `final.png` + a one-line audit summary
   (elements preserved, emphasis used, any uncertainties). Keep the summary in
   the reply / JSON — never draw it onto the image.

## Pick a layout

Set `"layout"` in the JSON. **Three timeline forms**, chosen by what the spacing
should mean:

- **`numbered_point_timeline`** — discrete events whose spacing carries NO
  argument (a dense fact chronology, or events with no usable dates:
  签约 → 转账 → 违约 → 起诉 → 判决). Axis is **equidistant**; markers are numbered
  circles (1-2-3), cards alternating above/below. → `render_points.py`

- **`dated_point_timeline`** — discrete events on a **date-proportional** axis, so
  the distance between two events is faithful to the elapsed time. The axis is a
  light-gray bar carrying an honest ruler (year ticks, or year+month for a short
  span, auto-chosen); markers are dots (no numbering); the precise date sits in
  each card. **Best for long, well-separated chronologies** (诉讼时效, 长期履行).
  Every event needs a real date or it errors — use the numbered form for
  undated/clustered events. → `render_dated.py`

- **`proportional_gantt`** — periods that run, overlap, or leave gaps
  (诉讼时效 / 保证期间 / 主债权 / 履行期间). Axis is **date-proportional** — bar
  length and overlap ARE the legal point (e.g. whether 本诉 falls outside 诉讼时效).
  One period per row. → `render_spans.py`

Rule of thumb: real time distances matter → `dated_point_timeline` (points) or
`proportional_gantt` (periods); only the ORDER matters → `numbered_point_timeline`.
Decide the timeline form with the **ordered decision ladder** in
`references/extraction-guide.md` (Step 1): if any event lacks a precise, parseable
date — or events are tightly clustered — use the equidistant `numbered_point_timeline`;
reserve `dated_point_timeline` for precise dates whose gaps carry legal meaning.
`numbered_point_timeline` is the safe default. A gantt may also carry point events
(转让公告, 提起本诉) as dashed vertical markers — put those in `points` (see schema).

For a **process / procedure** diagram (not dates but steps, decisions,
branches, merges), use the flowchart layout:

- **`graphviz_flow`** — nodes + directed edges. graphviz (`dot`) computes node
  positions ONLY; the renderer routes the connectors itself (orthogonal, rounded
  corners, sibling branches share a level "bus"), because graphviz's own ortho
  edge routes are unreliable. Node shapes encode function: rounded rect = step,
  **rounded hexagon = decision** (angled ends, corners r≈2.5, same height as a
  same-content step box — a hexagon holds multi-line Chinese far better than a
  diamond, which is a poor container for CJK text), pill = start/end terminal.
  → `render_flow.py`. Requires `dot` (graphviz) on PATH. See
  `references/flowchart-spec.md`.

For a **party / relationship** diagram (who the parties are and how they relate —
债权人/债务人/保证人, 股权, 资金流, 控制关系), use:

- **`graphviz_relation`** — nodes are parties/entities; edges are labeled,
  directed relationships; each node may carry a `note` below it. graphviz (engine
  chosen by topology: `dot` for rows/chains, `neato`/`fdp` for networks, `twopi`/
  `circo` for radial) positions nodes; the renderer draws cards, labeled lines,
  notes, and top/bottom skip-routes itself. Layout is free-form — do NOT force a
  fixed template (three-column, radial, etc.); let the source's real structure
  decide. → `render_relation.py`. See `references/relationship-spec.md`.

For a **hierarchical** party/entity structure — a top-down 主体关系图: 实际控制人 →
控股公司 → 子公司, 集团/股权/控制层级, org-chart-shaped — use:

- **`relation_tree`** — a tidy hierarchy tree. The renderer positions nodes itself
  (no graphviz): leaves take equal horizontal slots and every parent sits at the
  MIDPOINT of its children, so **every fork is symmetric with equal branch
  distances**. Boxes are one uniform height, and one uniform width per level, so
  the levels read as tidy columns. Connectors are bracket lines with the same tiny
  r≈2.5 rounded corners; structural edges have **no arrowheads** (a hierarchy line,
  not a directed relationship) unless `"arrows": true`. Node shading is depth-coded
  (dark root → mid → light leaves; aesthetic only, red still the one meaning); each
  edge may carry a short `label` (持股比例 …) and each node an optional `note`.
  → `render_tree.py`. Use this when the source is a hierarchy; use `graphviz_relation`
  when it is a free-form network of labeled relationships. See
  `references/relationship-spec.md`.

## The frozen visual rules (summary)

Full details in `references/visual-style.md`. The non-negotiables:

- **No blue.** Grayscale is the base palette; if the source uses blue, convert
  to neutral gray.
- **Deep red `#991B1B` = the single most important element, and nothing else.**
  It is a highlight, not decoration. An emphasized element is a **solid deep-red
  block with white text** — no border tricks, no left accent bars.
- **Dots, not diamonds** for nodes/markers. Circles only.
- **Boxes get small rounded corners; period bars are right-angle** (a running
  period is a bar, not a card — do not round it).
- **Period-bar labels**: centered inside the bar if they fit; if too long,
  right-aligned hugging the bar's left edge. On the red bar the inside text is
  white.
- **Title**: keep/generate a neutral chart name, centered at the top, with **no
  decorative underline**. No lawyer/team credit, no date, no marketing text.
- **A4-friendly aspect ratio** — not too wide (text shrinks) nor too tall. The
  scripts target roughly A4 landscape automatically.

## Legal fidelity (summary)

Full details in `references/fidelity-rules.md`. Text is verbatim. Never reorder
events for looks. Do not invent emphasis the source doesn't support without
flagging it as a suggestion for the user to confirm. Gray vs. white fill is a
free aesthetic choice (it does NOT encode parties like 甲方/施工方) — only deep
red carries meaning.

## Environment / rendering

SVG is the deliverable; PNG is derived. `render.py` auto-detects an SVG
rasterizer and falls back to `soffice` (LibreOffice) → PDF → `pdftoppm` when no
dedicated one is installed — which is the common minimal setup. CJK fonts
(e.g. Noto Sans CJK SC) must be present or the PNG shows blank boxes; verify
with `fc-list | grep -i "CJK SC"`. See `references/rendering-and-workflow.md`.

## Reference files

- **`references/STANDARDS.md` — the consolidated, authoritative standard (single
  source of truth; on any conflict, this file wins). Read it first.**
- **`references/extraction-guide.md` — how to read, analyze & decompose an ugly /
  hand-drawn / cluttered source into a correct map (the six-step discipline). This
  is the make-or-break input stage; read it before your first extraction.**
- `references/semantic-map-schema.md` — JSON schema + fields for all layouts.
- `references/visual-style.md` — every frozen visual rule with values.
- `references/fidelity-rules.md` — verbatim text, ordering, numbering, emphasis.
- `references/flowchart-spec.md` — flowchart shapes, connectors, forks, tidy-up.
- `references/relationship-spec.md` — relationship nodes, labeled edges, notes,
  free-form layout, skip-routes, and the hierarchical tree standard.
- `references/rendering-and-workflow.md` — render pipeline, env probe, audit,
  the human checkpoint, output naming.
- `AUTHOR.md` — author card and method.
- `examples/` — worked `semantic-map.json` inputs (numbered/dated/gantt timelines,
  flowchart, relationship network, relationship tree).

---

> **把法律画出来 · Make the Law Visible** ｜ 新诉讼可视化 New Litigation Visualization ｜ 缪奇川 出品 ｜ v1.0.0
