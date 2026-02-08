# TODO_003: Initialize Database with Schema

**Status:** Not Started  
**Priority:** High  
**Dependencies:** TODO_002 (Docker environment running)

---

## Objective

Initialize the JANATPMP SQLite database using the schema.sql file, verify structure, and confirm the 11 domain projects are seeded.

---

## Tasks

### 1. Database Location Decision

The schema.sql will create the database at `/db/janatpmp.db`. This keeps it:
- ✅ Organized in the `/db/` directory with schema.sql
- ✅ Separate from application code
- ✅ Easy to back up as a unit
- ✅ Clear that it's persistent data

**Note:** We already have a `janatpmp.db` in the project root from the prototype. We'll replace it with the new schema-based database.

### 2. Initialize Database

```bash
# From project root
sqlite3 db/janatpmp.db < db/schema.sql
```

Or using Python:

```python
import sqlite3

# Read schema
with open('db/schema.sql', 'r') as f:
    schema = f.read()

# Create database and execute schema
conn = sqlite3.connect('db/janatpmp.db')
conn.executescript(schema)
conn.close()

print("✅ Database initialized successfully")
```

### 3. Verify Tables Created

```bash
# List all tables
sqlite3 db/janatpmp.db ".tables"

# Expected output:
# cdc_outbox           items                relationships      
# documents            items_fts            schema_version     
# documents_fts        tasks
```

Or using Python:

```python
import sqlite3

conn = sqlite3.connect('db/janatpmp.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()

print("Tables created:")
for table in tables:
    print(f"  ✅ {table[0]}")

conn.close()
```

### 4. Verify Seed Data

```bash
# Check the 11 seeded domains
sqlite3 db/janatpmp.db "SELECT domain, title, status FROM items ORDER BY domain"
```

Or using Python:

```python
import sqlite3

conn = sqlite3.connect('db/janatpmp.db')
cursor = conn.cursor()

cursor.execute("SELECT domain, title, status FROM items ORDER BY domain")
domains = cursor.fetchall()

print("\n11 Domains seeded:")
for domain, title, status in domains:
    print(f"  📁 {domain:15} | {title:40} | {status}")

conn.close()
```

### 5. Update database.py

Update the existing `database.py` to point to the new database location:

```python
import sqlite3
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent / "db" / "janatpmp.db"

def get_connection():
    """Get database connection with proper settings."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    return conn
```

### 6. Clean Up Old Database

```bash
# Archive the old prototype database
mv janatpmp.db janatpmp.db.prototype.backup

# Or delete if not needed
rm janatpmp.db
```

---

## Acceptance Criteria

- [ ] `/db/janatpmp.db` created successfully
- [ ] All 9 expected tables exist (items, tasks, documents, relationships, cdc_outbox, + 2 FTS, + schema_version)
- [ ] All 4 FTS trigger sets created (items_fts: insert/update/delete, documents_fts: insert/update/delete)
- [ ] All CDC triggers created (items, tasks, documents, relationships)
- [ ] 11 domain projects seeded in items table
- [ ] `database.py` updated to use new database path
- [ ] Old prototype database archived or removed
- [ ] Can query database successfully: `SELECT COUNT(*) FROM items` returns 11
- [ ] All changes committed to git

---

## Verification Queries

After initialization, run these to verify structure:

```sql
-- Count tables (should be 9)
SELECT COUNT(*) FROM sqlite_master WHERE type='table';

-- Count items (should be 11 domains)
SELECT COUNT(*) FROM items;

-- Show domains
SELECT domain, title, status FROM items ORDER BY domain;

-- Verify indexes created
SELECT name FROM sqlite_master WHERE type='index' ORDER BY name;

-- Verify triggers created
SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name;

-- Check schema version
SELECT * FROM schema_version;
```

---

## Notes

- The schema includes comprehensive comments explaining each table's purpose
- Foreign key constraints are ENABLED via PRAGMA - ensures data integrity
- WAL mode is enabled for better concurrent access
- Full-text search is set up on items and documents for fast searching
- CDC outbox captures all changes for future Qdrant/Neo4j sync
- Virtual columns on JSON fields enable efficient querying without full scans

---

## Future Considerations

Once this TODO is complete, we'll be ready for:
- **TODO_004**: Schema Viewer Mind Map (visualize the structure we just built)
- **TODO_005**: Import claude_exporter conversations (603 conversations → documents table)
- **TODO_006**: Basic CRUD operations for Items/Tasks/Documents
- **TODO_007**: Projects-first UI redesign

The database is the foundation. Everything else builds on this.
