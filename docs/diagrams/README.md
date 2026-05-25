# Architectural diagrams

Visual companion to [`../EDEN_ARCHITECTURE.md`](../EDEN_ARCHITECTURE.md). Each
file is a **draw.io "Editable SVG"** — both a valid SVG that GitHub renders
inline and a draw.io source file that opens directly in the editor. Edit and
save in either tool; one file, no export/sync dance.

## Files

| # | File | What it shows | Architecture section |
|---|---|---|---|
| 1 | `01-principal-hierarchy.drawio.svg` | The 5 principal types (Consultancy, Partner, Client + members) and how they relate | §1 |
| 2 | `02-tenant-isolation.drawio.svg` | Control-plane schema vs per-client schemas; tenant router; `search_path` per request | §5 |
| 3 | `03-data-flow-recruitment.drawio.svg` | Partner referral → consultancy review queue → client pipeline | §4 partner, recruitment slice |
| 4 | `04-deployment-topology.drawio.svg` | FastAPI + Postgres + Keycloak in the India region; HA layout | §6, §0.1 #9 |
| 5 | `05-authorization-stack.drawio.svg` | Keycloak → principal → PDP → intra-schema RLS; defense in depth | §4, §7, §8 |

## How to edit

**In the browser:** drag any `.drawio.svg` file onto [app.diagrams.net](https://app.diagrams.net). Save back to overwrite the file in place.

**In VS Code:** install the **Draw.io Integration** extension by Henning Dieterichs. `.drawio.svg` files open directly in an embedded draw.io editor.

**In other editors:** any tool that supports draw.io's Editable SVG format will work (e.g. the standalone draw.io desktop app).

## How to add a new diagram

1. Add a row to the table above with the next sequence number.
2. Create a new placeholder by copying any existing `.drawio.svg` and renaming.
3. Open in draw.io and replace the placeholder content.
4. If it deserves a callout in the architecture doc, embed it inline:
   ```markdown
   ![Principal hierarchy](diagrams/01-principal-hierarchy.drawio.svg)
   ```

## Style guidelines (loose)

- Keep each diagram **one screen**. If it doesn't fit, split it.
- Use **consistent colors per principal type** across diagrams — pick once, stick to it (e.g. Consultancy = teal, Partner = amber, Client = indigo).
- Label edges with the relationship verb ("submits referral", "owns schema", "issues token"). Unlabeled arrows are usually a missed opportunity.
- Prefer **boxes-and-arrows** over rich graphics — these are spec diagrams, not marketing.
