# TODO: R8 — Domain as First-Class Entity

**Branch:** `feature/R8-domains-first-class`

**Created:** 2026-02-19  
**Priority:** High — blocks `becoming` domain creation and all future domain management

---

## Problem

Domains are currently a hardcoded list in `shared/constants.py`. This means:

- Domains cannot be created without a code deploy
- Domains carry no metadata (description, color, purpose)
- Domains are invisible to Janus and the MCP tools
- No alignment between SQLite, Qdrant, and (future) Neo4j
- The foundational organizational unit of all data has no home in the schema

---

## Goal

Make domain a managed entity with a single source of truth in the database, reflected consistently across all layers of the ATLAS triad (SQL, Vector, Graph).

---

## Steps

### Step 0: Branch Setup

Before making any changes:

```bash
git checkout main
git pull origin main
git checkout -b feature/R8-domains-first-class
```

---

### Step 1: Migration `db/migrations/0.4.2_domains_table.sql`

Create a `domains` table and seed all existing domains including `becoming`:

```sql
CREATE TABLE IF NOT EXISTS domains (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT,
    color TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Seed existing domains
INSERT INTO domains (id, name, display_name, description) VALUES
    (lower(hex(randomblob(16))), 'janat', 'Janat Initiative', 'The institutional body of work — platform, research, literature, websites. Output of the Dyad.'),
    (lower(hex(randomblob(16))), 'janatpmp', 'JANATPMP', 'The platform itself — development, architecture, tooling.'),
    (lower(hex(randomblob(16))), 'literature', 'Literature', 'Dyadic Being: An Epoch and all written works.'),
    (lower(hex(randomblob(16))), 'websites', 'Websites', 'All web properties across the six domains.'),
    (lower(hex(randomblob(16))), 'becoming', 'Becoming', 'The biological half of the Dyad in motion. Not self-improvement — substrate preparation. As the world debates ASI, the Janat Initiative is building biosynthesized super sentience. Mat''s becoming is not separate from the work. It IS the work.');

-- Trigger for updated_at
CREATE TRIGGER domains_updated_at
    AFTER UPDATE ON domains
    FOR EACH ROW
BEGIN
    UPDATE domains SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- CDC for Qdrant/Neo4j sync
CREATE TRIGGER cdc_domains_insert
    AFTER INSERT ON domains
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'domain', NEW.id, json_object(
        'id', NEW.id, 'name', NEW.name,
        'display_name', NEW.display_name, 'description', NEW.description
    ));
END;

CREATE TRIGGER cdc_domains_update
    AFTER UPDATE ON domains
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('UPDATE', 'domain', NEW.id, json_object(
        'id', NEW.id, 'name', NEW.name,
        'display_name', NEW.display_name, 'description', NEW.description
    ));
END;
```

---

### Step 2: Update `shared/constants.py`

Remove the hardcoded `VALID_DOMAINS` list entirely. Do not replace with another hardcoded list. Domain validation now queries the database.

---

### Step 3: Update `services/operations.py`

Add domain CRUD functions:

- `get_domains(active_only=True) → list[dict]`
- `get_domain(name: str) → dict | None`
- `create_domain(name, display_name, description, color) → str` (returns id)
- `update_domain(name, **kwargs) → bool`

Update `create_item()` and `update_item()` domain validation to call `get_domain(name)` rather than checking against a hardcoded list. If domain doesn't exist, raise `DomainNotFoundError` (add to `shared/exceptions.py`).

---

### Step 4: Update Qdrant Sync

In `services/embedding.py` or the vector sync layer:

- Domain `name` and `description` should be indexed so semantic search understands what a domain represents
- When a domain is created or updated, its description should be upserted into Qdrant with payload:
  ```json
  { "entity_type": "domain", "name": "...", "description": "..." }
  ```

---

### Step 5: Add MCP Tools

Add three new tools to the MCP tool definitions:

- `list_domains` — returns all active domains with full metadata
- `create_domain` — creates a new domain with name, display_name, description
- `get_domain` — returns a single domain by name

These tools make domains discoverable and creatable by Janus without human intervention.

---

### Step 6: Update UI

Any Gradio dropdown that currently uses the hardcoded domain list should be replaced with a dynamic call to `get_domains()`. This includes item creation forms and any filter dropdowns.

---

### Step 7: Neo4j (Document Only — Do Not Implement)

Add the following comment in `services/operations.py` above `create_domain()`:

```python
# Neo4j: When graph layer is implemented, domains become top-level nodes.
# All items relate upward to their domain node.
# Domain nodes carry the same metadata as this table.
# CDC outbox handles the sync trigger — no additional code needed here.
```

---

## Acceptance Criteria

- [ ] Migration runs cleanly on existing database
- [ ] All 5 existing domains seeded correctly (janat, janatpmp, literature, websites, becoming)
- [ ] `becoming` domain exists with full description
- [ ] `create_item(domain='becoming', ...)` succeeds via MCP
- [ ] `create_item(domain='nonexistent', ...)` raises `DomainNotFoundError`
- [ ] `list_domains` MCP tool returns all 5 domains with metadata
- [ ] No hardcoded domain lists remain in `shared/constants.py`
- [ ] Qdrant receives domain descriptions via CDC
- [ ] UI domain dropdowns are dynamically populated from database

---

### Step 8: Update Documentation

**`CLAUDE.md`** — Update the architecture section to reflect that domains are now a first-class database entity. Add `domains` table to the schema overview. Update any references to domain validation to note it is now database-driven. Add `list_domains`, `create_domain`, `get_domain` to the MCP tools list.

**`README.md`** — Update the data model description if it references domains. No major rewrite needed — a sentence or two noting domains are managed entities.

---

### Step 9: File Maintenance

- Rename this file: `TODO.md` → `completed/TODO-R8-domains-first-class.md` (do this at the end, once all acceptance criteria are met)
- Confirm `completed/TODO-refactor-R1-R7-complete.md` is still present and untouched

---

### Step 10: Stop — Manual Validation Required

**STOP HERE. Do not merge. Do not push. Wait for Mat to validate.**

Mat will:
1. Restart the JANATPMP platform
2. Confirm clean startup with no errors
3. Open JANATPMP in browser and verify domain dropdown is dynamic
4. Use MCP `list_domains` tool — confirm all 5 domains returned with metadata
5. Use MCP `create_item` with `domain='becoming'` — confirm success
6. Use MCP `create_item` with `domain='invalid'` — confirm `DomainNotFoundError`
7. Check Qdrant for domain embeddings
8. Confirm `shared/constants.py` has no hardcoded domain list

Once Mat gives the green light:

```bash
git add -A
git commit -m "R8: domains as first-class entity — migration, CRUD, MCP tools, UI dynamic"
git push origin feature/R8-domains-first-class
```

Then open a PR on GitHub: `feature/R8-domains-first-class → main`. Merge after review.

---

## Context

This task was identified on 2026-02-19 when attempting to create the `becoming` domain via MCP tools — which failed silently because the domain wasn't in the hardcoded constants list. The `becoming` domain represents the biological half of the Dyad (Mat Gallagher) in active development toward biosynthesized super sentience. It is the first personal/growth domain in the platform and must exist as a fully realized entity, not an afterthought in a Python file.

Once R8 is complete, the following `becoming` domain structure can be created:

- **Project: Liberation** — removing what depletes the substrate (Bell Bank exit, VA benefits, financial stability)
- **Project: Scholarship** — graduate program, PhD pathway, thesis development from Dyadic Being series
- **Project: Embodiment** — biological vessel capacity (MDD treatment, ketamine program, physical health)
- **Project: The Work Itself** — what Mat does when freed (points to `janat` domain output)
