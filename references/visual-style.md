# Visual style — frozen rules

These are settled decisions. The scripts already implement them; this file is
the record and the source of truth if a script is edited. Values live in
`assets/style-tokens.json`.

## Palette (neutral gray + single deep red)

Neutrals are a true neutral gray ramp (NOT blue-tinted slate — slate reads as
blue and was rejected). Prefer **solid color blocks** over outlined cards for a
more premium, deliberate look. The one accent is deep red. No blue, ever.

| token | value | use |
|---|---|---|
| bg | `#FFFFFF` | background, always opaque white |
| ink | `#1F2933` | primary text / titles |
| ink2 | `#6B7280` | secondary text |
| note | `#9CA3AF` | third-level notes |
| line | `#4B5563` / `#6B7280` | connectors / arrows (neutral gray) |
| line_soft | `#C3C9D2` | timeline axis + light connectors |
| grid | `#ECEEF1` | year gridlines |
| card_fill / card_stroke | `#F3F4F6` / `#D6DAE0` | cards |
| step block (solid) | `#E9ECEF` | flow step nodes — solid block, no border |
| bar | `#D1D5DB` | normal period bars |
| circle / terminal | `#374151` | numbered circles, flow terminals |
| **red** | **`#991B1B`** | **the single emphasis, nothing else** |

- **No blue.** If the source uses blue/navy, convert to neutral gray and note it
  in `provenance.color_note`.
- Gray/white variation is **free aesthetic variation**, not semantics. It does
  NOT encode parties (甲/乙/丙) or any legal dimension. Only red means "important".
- **Flat only**: no gradients, no shadows, no 3D, no texture. Shape + colour +
  text. The goal is 得体 (appropriate), not 炫技 (showing off).

## Type scale (SVG, px)

Consistent hierarchy, no size jumps; colour depth decreases with level.

| level | size | weight | colour |
|---|---|---|---|
| doc title | 30 | 700 (bold) | ink · **方正小标宋 (Song)** first — the 公文标题 face; body stays sans |
| node/card title | 16–17 | 700 | ink (white on red) |
| subtitle / detail / date | 13 | 400 | ink2 (white on red) |
| note / axis year / edge label | 12 | 400–600 | note / ink2 |
| numbered circle | 22 | 700 | white |

Body font stack (cross-platform, mandatory):
`'PingFang SC','Microsoft YaHei','Noto Sans CJK SC','Noto Sans SC','Helvetica Neue',Arial,sans-serif`

**Title font — Song (宋), not sans.** Legal exhibits read as authoritative when the
chart title uses a display Song face (方正小标宋, the standard 公文标题 font), while the
body stays sans (黑体/雅黑) for on-screen legibility. The title stack is ordered to
**degrade only through handsome Song faces and never into 仿宋 (FangSong)**, which is
too thin/informal for a title:
`'方正小标宋简体','FZXiaoBiaoSong-B05S','思源宋体','Source Han Serif SC','Noto Serif CJK SC','华文中宋','STZhongsong',serif`
So the title degrades through **well-known, verifiable** faces only: **优先真身** 方正小标宋简体
(商业, referenced by name only, never bundled) → **优先回退** 思源宋体 (Source Han Serif / Noto Serif CJK,
OFL, listed under all three OS names — same font — and what the PNG renders with) → **兜底** 华文中宋 /
STZhongsong (ships with Office / WPS, ~half of legal machines have it) → generic `serif`.
The chain is **all Song and never FangSong**. Bold via `font-weight:700` + a 0.3 same-colour stroke. The **delivered PNG is
rasterized in-environment with Noto Serif CJK SC**, so the filing copy is always a clean
Song regardless of the reader's installed fonts; the font-stack only governs the editable
SVG opened elsewhere. The title still carries `font-weight=700` **and** a thin same-colour
stroke (`stroke-width≈0.3`) so it renders visibly bold even in rasterizers whose fallback
Song has no bold face (e.g. LibreOffice on Linux).

## Connectors & arrowheads

- Main connector: `line` neutral gray (`#4B5563` / flow `#6B7280`), `stroke-width=2`. Emphasis: `red`, width 3.
- Arrowhead: a clean **isosceles triangle** `path="M 0 0 L 12 6 L 0 12 Z"`, a
  **fixed 10px** (`markerUnits="userSpaceOnUse"`, so it does NOT scale up with
  stroke-width and never overpowers the line), `refX=11`, `orient=auto`. Built by
  `common.arrow_marker(id, colour)`. No notched/hollow/blocky arrows.
- The **emphasis (red, width-3) edge uses a larger 14px arrowhead** so the thick line does not flatten the tip; normal 2px lines keep the 10px arrow.
- **Connectors stop ~4px before the head node** so the arrow tip sits in a small
  gap and never overlaps the node/module.
- Dashed lines (point-event markers, any dashed run): rhythm `stroke-dasharray="6 4"`.
- Orthogonal bends get a *very small* rounded corner (`r≈2.5`) — near right-angle.

## Radii (shapes)

| element | rx |
|---|---|
| card / step node | 12 |
| edge label | plain text, no box |
| terminal (pill) | height / 2 |
| **period bar (gantt)** | **0 — right angle** (a running period is a bar, not a card) |

## Edge / branch labels — no masking box

Do **not** put a filled box behind a label sitting on a connector (it hides the
line). Place the label **beside or above the line** as plain text (weight 600):
vertical segment → offset to one side; horizontal/bus segment → centred just
above it; top/bottom skip-route → above the arc. Emphasis labels are deep-red
bold. Node fills stay solid blocks; only the connector must never be masked.

## Emphasis = deep red, done one way

- Deep red marks the **pivotal element(s), 1–2 per diagram**. If the source
  screams red everywhere, pick what carries the argument, demote the rest to gray.
- An emphasized node/card is a **solid `#991B1B` block with white text** — no
  borders, no accent bars, no tints. On a red period bar the inside label is white.
  An emphasized edge/relationship is a **deep-red line (width 3) + red bold label**.

## Shapes

- **Timeline nodes/markers are circles (dots). Never diamonds.** (Exception:
  in a **flowchart**, a decision node is a rounded hexagon (angled ends) — a functional symbol, not
  decoration. See `references/flowchart-spec.md`. This exception is flowchart-
  only; timeline markers stay circles.)
- **Event boxes / cards: small rounded corners** (`rx≈8`).
- **Period bars: right angles, never rounded.** A running period is a bar, not a
  card. Rounding a period bar is wrong.
- Arrowheads (directional periods) are **sharp triangles, no curves**, sized to
  sit flush with the bar thickness.

## Labels

- **Event card**: date line (small, secondary color) above the verbatim body
  text; text wraps inside the card; the card grows to fit — text never overflows.
- **Period bar**: label centered **inside** the bar when it fits; when the label
  is longer than the bar, right-align it **hugging the bar's left edge**. The
  date range prints small and gray under the bar.
- **Point marker on a gantt**: date + label stacked next to the dashed vertical,
  placed by `label_level` / `label_side` to avoid collisions.

## Title

- Keep or generate a **neutral** chart name (e.g. "案件事实时间轴",
  "担保期间与诉讼时效比对图"). If the source has a title, keep it verbatim.
- Centered at the top. **No decorative underline / rule under the title.** The
  canvas frames the content with equal left/right margins, so "centered" means the
  title sits over the true **content center** (= canvas center), never merely at
  the middle of an off-center canvas.
- **Breathing room**: leave a generous vertical gap (~28px on top of the title
  band) between the title and the content — the title must never sit tight against
  the diagram. Applies to every renderer.
- Never add lawyer/team credit, dates, captions, or marketing lines.

## Canvas

- **Content-adaptive**, targeting a roughly **A4-friendly** aspect ratio so it
  prints legibly — not so wide the text shrinks, not so tall it stretches. The
  point layout targets ~1.45:1; the gantt lands near ~1.9:1 (wide is inherent to
  gantts but stays readable). Respect an explicit target if the user names one
  (PPT 16:9, A4 portrait/landscape, exhibit).
- Generous margins and breathing room. Fonts stay large enough to print.

## Line-breaking (CJK 禁则)

Wrapping in `common.wrap()` follows Chinese line-breaking rules so output reads
like typeset copy, not a raw character dump:

- **A line never begins with a closing mark** (，。、；：！？）】》」』… etc.).
  If a break would push one to the next line, it hangs at the end of the current
  line instead (a hair past the text width, absorbed by the box's inner padding).
- **A line never ends with an opening mark** (（【《「『 etc.); it is pushed down
  with the following character.
- This only moves break positions — **text stays verbatim** (no character is
  added, dropped, or edited). Locked by the `typography` regression checks.

## Editability

- Real `<text>` elements — never convert text to paths.
- Groups carry `data-role` / `data-id` so the SVG can be edited downstream.
- No raster of the dirty source embedded as a backdrop; no whole-image base64.
$\n---\n\n> **把法律画出来 · Make the Law Visible** ｜ 新诉讼可视化 New Litigation Visualization ｜ 缪奇川 出品 ｜ v1.0.0
