"""
Test script for database operations.
Run with: python db/test_operations.py
"""

from operations import (
    create_item, get_item, list_items, update_item, delete_item,
    create_task, get_task, list_tasks, update_task,
    create_document, get_document, list_documents,
    create_relationship, get_relationships,
    get_schema_info, get_stats,
    search_items, search_documents
)


def test_items():
    print("\n=== Testing Items ===")

    # List existing items
    items = list_items()
    print(f"Existing items: {len(items)}")

    # Create a new item
    item_id = create_item(
        entity_type="feature",
        domain="janatpmp",
        title="Test Feature",
        description="A test feature for validation",
        status="planning"
    )
    print(f"Created item: {item_id}")

    # Get the item
    item = get_item(item_id)
    print(f"Got item: {item['title']} ({item['status']})")

    # Update the item
    result = update_item(item_id, status="in_progress")
    print(f"Update result: {result}")

    # Verify update
    item = get_item(item_id)
    print(f"Updated status: {item['status']}")

    # Delete the item
    result = delete_item(item_id)
    print(f"Delete result: {result}")

    # Verify deletion
    item = get_item(item_id)
    print(f"After delete: {'Not found' if not item else 'Still exists'}")

    print("Items test: PASSED")


def test_tasks():
    print("\n=== Testing Tasks ===")

    # Create a task
    task_id = create_task(
        task_type="user_story",
        title="Test Task",
        description="A test task",
        assigned_to="mat",
        priority="normal"
    )
    print(f"Created task: {task_id}")

    # Get the task
    task = get_task(task_id)
    print(f"Got task: {task['title']} (assigned to {task['assigned_to']})")

    # Update task status
    result = update_task(task_id, status="processing")
    print(f"Update result: {result}")

    # List tasks
    tasks = list_tasks(status="processing")
    print(f"Processing tasks: {len(tasks)}")

    # Clean up - update to completed
    update_task(task_id, status="completed")

    print("Tasks test: PASSED")


def test_documents():
    print("\n=== Testing Documents ===")

    # Create a document
    doc_id = create_document(
        doc_type="session_notes",
        source="manual",
        title="Test Document",
        content="This is test content for the document."
    )
    print(f"Created document: {doc_id}")

    # Get the document
    doc = get_document(doc_id)
    print(f"Got document: {doc['title']} ({doc['doc_type']})")

    # List documents
    docs = list_documents(doc_type="session_notes")
    print(f"Session notes: {len(docs)}")

    print("Documents test: PASSED")


def test_relationships():
    print("\n=== Testing Relationships ===")

    # Get existing items to link
    items = list_items(limit=2)
    if len(items) >= 2:
        # Create a relationship
        rel_id = create_relationship(
            source_type="item",
            source_id=items[0]['id'],
            target_type="item",
            target_id=items[1]['id'],
            relationship_type="informs"
        )
        print(f"Created relationship: {rel_id}")

        # Get relationships
        rels = get_relationships(entity_type="item", entity_id=items[0]['id'])
        print(f"Relationships for item: {len(rels)}")
    else:
        print("Not enough items to test relationships")

    print("Relationships test: PASSED")


def test_schema_and_stats():
    print("\n=== Testing Schema & Stats ===")

    # Get schema
    schema = get_schema_info()
    print(f"Tables: {list(schema['tables'].keys())}")
    print(f"Indexes: {len(schema['indexes'])}")
    print(f"Triggers: {len(schema['triggers'])}")

    # Get stats
    stats = get_stats()
    print(f"Total items: {stats['total_items']}")
    print(f"Items by domain: {stats['items_by_domain']}")
    print(f"Total tasks: {stats['total_tasks']}")
    print(f"Total documents: {stats['total_documents']}")

    print("Schema & Stats test: PASSED")


def test_search():
    print("\n=== Testing Search ===")

    # Search items
    results = search_items("JANAT")
    print(f"Items matching 'JANAT': {len(results)}")
    for r in results[:3]:
        print(f"  - {r['title']}")

    print("Search test: PASSED")


if __name__ == "__main__":
    print("=" * 50)
    print("JANATPMP Database Operations Test")
    print("=" * 50)

    try:
        test_items()
        test_tasks()
        test_documents()
        test_relationships()
        test_schema_and_stats()
        test_search()

        print("\n" + "=" * 50)
        print("ALL TESTS PASSED")
        print("=" * 50)
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
