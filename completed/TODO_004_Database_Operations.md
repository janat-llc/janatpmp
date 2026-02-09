# TODO_004: Database Operations & MCP Tool Exposure

**Status:** Not Started  
**Priority:** High  
**Dependencies:** TODO_003 (Database initialized)

---

## Objective

Create the operational layer for database access - CRUD functions for Items/Tasks/Documents/Relationships, plus schema introspection capabilities. Expose these as MCP tools via Gradio's built-in `gr.api()` mechanism.

---

## Tasks

### 1. Create db/operations.py

Create comprehensive database operations module at `db/operations.py` with proper docstrings and type hints (Gradio uses these to auto-generate MCP tool schemas):

[Include the FULL operations.py content from earlier - all CRUD functions for items, tasks, documents, relationships, plus get_schema_info() and get_stats()]

**IMPORTANT:** Each function must have:
- Clear docstring (becomes MCP tool description)
- Type hints on all parameters (becomes MCP parameter schema)
- Simple return types (str, dict, list - JSON serializable)

### 2. Create db/test_operations.py

[Same test file as before - tests all CRUD operations]

### 3. Expose Operations in app.py

Update `app.py` to expose database operations as MCP tools:

```python
import gradio as gr
from db.operations import (
    create_item, get_item, list_items, update_item, delete_item,
    create_task, get_task, list_tasks, update_task,
    create_document, get_document, list_documents,
    create_relationship, get_relationships,
    get_schema_info, get_stats
)

# Existing inventory import
from features.inventory.scanner import inventory_tab

with gr.Blocks(title="JANATPMP v0.1 Alpha") as demo:
    with gr.Tabs():
        with gr.Tab("Inventory"):
            inventory_tab.render()
        
        with gr.Tab("Database"):
            gr.Markdown("# Database Operations")
            gr.Markdown("Database tools exposed via MCP for Claude Desktop")
            
            # Expose all database operations as API/MCP tools
            # No wrapper needed - Gradio auto-generates from docstrings!
            gr.api(create_item)
            gr.api(get_item)
            gr.api(list_items)
            gr.api(update_item)
            gr.api(delete_item)
            
            gr.api(create_task)
            gr.api(get_task)
            gr.api(list_tasks)
            gr.api(update_task)
            
            gr.api(create_document)
            gr.api(get_document)
            gr.api(list_documents)
            
            gr.api(create_relationship)
            gr.api(get_relationships)
            
            gr.api(get_schema_info)
            gr.api(get_stats)
            
            gr.Markdown("## MCP Tools Available")
            gr.Markdown("All database operations are now accessible via Claude Desktop at:")
            gr.Markdown("`http://localhost:7860/gradio_api/mcp/`")

if __name__ == "__main__":
    demo.launch(mcp_server=True)
```

**That's it!** Gradio automatically:
- Creates MCP tool schemas from docstrings
- Exposes at `/gradio_api/mcp/`
- Makes callable from Claude Desktop
- Generates API docs at `/gradio_api/mcp/schema`

### 4. Update database.py

Update existing `database.py` to import from operations:

```python
"""
Database module - re-exports from db/operations.py
Maintains backward compatibility
"""
from db.operations import *
```

---

## Acceptance Criteria

- [ ] `db/operations.py` created with all CRUD functions
- [ ] **Each function has proper docstring and type hints**
- [ ] `db/test_operations.py` created and runs successfully
- [ ] All CRUD operations work correctly
- [ ] Schema introspection functions work
- [ ] **Functions exposed via `gr.api()` in app.py**
- [ ] **NO separate API wrapper file needed**
- [ ] MCP server running at `/gradio_api/mcp/`
- [ ] MCP schema visible at `/gradio_api/mcp/schema`
- [ ] Can call tools from Claude Desktop
- [ ] `database.py` updated for compatibility
- [ ] All changes committed to git

---

## Verification Commands

```bash
# Run tests
python db/test_operations.py

# Check database integrity
sqlite3 db/janatpmp.db "PRAGMA integrity_check"

# Verify seeded domains still intact
sqlite3 db/janatpmp.db "SELECT COUNT(*) FROM items"
# Should be 12

# Launch with MCP server
docker-compose up

# Visit MCP schema endpoint
curl http://localhost:7860/gradio_api/mcp/schema | jq

# View in browser
# http://localhost:7860 → Database tab → See tools listed
```

---

## Notes

- **Gradio auto-generates MCP tools from functions** - no wrapper needed!
- Docstrings become tool descriptions
- Type hints define parameter schemas  
- Return values should be JSON-serializable
- `mcp_server=True` in launch() enables MCP endpoint
- Claude Desktop can immediately use these tools
- Agents can call via HTTP API
- **Simpler is better - let Gradio do the work!**

---

## Next Steps After Completion

With database operations exposed as MCP tools:
- **TODO_005**: Schema Viewer Mind Map (uses `get_schema_info()`)
- **TODO_006**: Import claude_exporter conversations (uses `create_document()`)
- **TODO_007**: Projects-first UI redesign (uses all CRUD)
- **Claude can manage database via natural language!**

The operational layer is the bridge between database structure and application features.
