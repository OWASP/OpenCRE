from neo4j_connection import db  # type: ignore

# Queries to create nodes, relationships, and indexes
queries = [
    "CREATE (:User {name: 'Alice'})-[:FRIENDS_WITH]->(:User {name: 'Bob'});",
    "CREATE (:User {name: 'Charlie'})-[:FRIENDS_WITH]->(:User {name: 'Dave'});",
    "CREATE INDEX FOR (s:Standard) ON (s.name);",
    "CREATE INDEX FOR (f:Framework) ON (f.name);",
]

# Execute each query
for query in queries:
    db.run_query(query)
    print(f"Executed: {query}")

db.close()
