# Relationship-diagram spec (frozen)

For party/entity diagrams: nodes are parties (债权人/债务人/保证人, companies,
shareholders…), edges are labeled directed **relationships** (借贷, 担保, 追偿,
连带清偿, 股权, 资金流, 控制…). Rendered by `render_relation.py`. Requires `dot`
(graphviz) on PATH.

## Layout is free-form — do NOT template it

A relationship diagram has high degrees of freedom. Let the source's real
structure decide the shape: a chain/row, a central hub with spokes, or a loose
network. Pick the graphviz engine to match and set it in `engine`:

| structure | engine | note |
|---|---|---|
| chain / row / layered | `dot` | ranks left→right (LR) or top→bottom |
| central hub + spokes | `twopi` or `circo` | radial |
| loose network | `neato` or `fdp` | force-directed |

Never impose a fixed template (e.g. "three-column evidence↔view"). That column
layout is just one possible result of a `dot` LR graph, not a required form.

## Positioning: graphviz for coordinates ONLY

As with flowcharts, use graphviz for **node positions** and draw everything else
ourselves — cards, labeled relationship lines, per-node notes, and skip-routes.
Do not rely on graphviz's edge routes.

## Nodes

- Card: rounded rect (`rx=12`), light-gray fill, gray border, bold centered
  `title` (verbatim). Same restrained palette as the rest of the skill.
- `note` (optional): a short verbatim annotation rendered as small gray text
  **below** the node — no connector line. Notes describe a party (its identity /
  obligation), they are not relationships. In the source, an annotation that
  merely labels a party (e.g. an up-arrow tag "还款义务（本金+利息）") is a `note`,
  NOT an edge.

## Edges (relationships)

- Directed, drawn between node borders, arrow at the head; keep the source's
  direction.
- `label`: the relationship, verbatim, as plain text beside/above the line (NO masking box). Omit if the
  source edge had no label (don't invent one).
- `route`: `straight` (default, adjacent nodes) | `top` | `bottom`. Use `top`/
  `bottom` when a straight line would cross an intervening node (e.g. a
  first-party-to-guarantor 连带清偿责任 arc over the debtor). Skip-routes are
  orthogonal with **tiny rounded corners** (`r≈2.5`), same as flowcharts.
- `emphasis`: the pivotal relationship — solid **deep-red** thick line + red
  label. 1-2 per diagram; AI may choose it if the source doesn't dictate one.

## Spacing / occlusion

Keep node separation generous enough that a straight edge's label fits in the gap
between the two nodes without overlapping either card. If a label is wider than
the gap, widen `ranksep` (the renderer already uses a comfortable value) rather
than letting text collide with a node.

## Gray/white and red

Gray/white variation is aesthetic only — it does not encode party or category.
Only deep red carries meaning (the key relationship). No blue.

## Hierarchical tree (`relation_tree`) — frozen charting standard

For a top-down hierarchy (主体关系图 / 股权·控制层级, org-chart-shaped) use the
`relation_tree` layout (`render_tree.py`). Its geometry is a **fixed standard**,
locked by `tree-std` regression guards — do not loosen it:

1. **Tidy-tree layout, self-computed (no graphviz).** Leaves occupy **equal
   horizontal slots**; every parent is placed at the **exact midpoint of its
   children**. Consequence: **every fork is symmetric — the distance from a parent
   to each of its children is basically equal — and sibling gaps are uniform.**
2. **Uniform box height** across all levels (no level looks thicker than another),
   and **one uniform box width per level** so the levels read as tidy columns.
3. **Bracket connectors** (parent → shared bus → each child) with the skill's tiny
   **r≈2.5 rounded corners** (near right-angle). Structural edges carry **no
   arrowheads** by default — a hierarchy line is not a directed relationship; set
   `"arrows": true` only when the source's arrows are meaningful.
4. **Depth shading**: root dark (`#374151`, white text) → middle mid-gray → leaves
   light card (`#EDEFF2`, hairline border). This encodes DEPTH for legibility only;
   it is not legal semantics. Deep red remains the single carrier of meaning
   (a pivotal entity = solid red block + white text; 1-2 per diagram).
5. Optional per-branch `label` (持股比例 …, verbatim, no box) sits beside the child
   drop; optional per-node `note` sits below the node.

Use `relation_tree` when the source is a hierarchy; use `graphviz_relation` for a
free-form network of labeled relationships.

---

> **把法律画出来 · Make the Law Visible** ｜ 新诉讼可视化 New Litigation Visualization ｜ 缪奇川 出品 ｜ v1.0.0
