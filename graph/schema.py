"""Neo4j graph schema — idempotent constraints and indexes."""

import logging

logger = logging.getLogger(__name__)


def init_graph_schema(driver) -> None:
    """Create uniqueness constraints and indexes in Neo4j.

    Safe to call repeatedly — all statements use IF NOT EXISTS.

    Args:
        driver: neo4j.Driver instance.
    """
    constraints = [
        "CREATE CONSTRAINT item_id IF NOT EXISTS FOR (n:Item) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT task_id IF NOT EXISTS FOR (n:Task) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT conversation_id IF NOT EXISTS FOR (n:Conversation) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT message_id IF NOT EXISTS FOR (n:Message) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT domain_id IF NOT EXISTS FOR (n:Domain) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT message_metadata_id IF NOT EXISTS FOR (n:MessageMetadata) REQUIRE n.id IS UNIQUE",
    ]

    indexes = [
        "CREATE INDEX message_conv IF NOT EXISTS FOR (m:Message) ON (m.conversation_id)",
        "CREATE INDEX item_domain IF NOT EXISTS FOR (i:Item) ON (i.domain)",
        "CREATE INDEX message_sequence IF NOT EXISTS FOR (m:Message) ON (m.sequence)",
    ]

    with driver.session() as session:
        for stmt in constraints + indexes:
            session.run(stmt)

    logger.info("Neo4j schema initialized (%d constraints, %d indexes)",
                len(constraints), len(indexes))
