from neo4j_connection import db  # type: ignore

# Optimized query for performance
query = """
PROFILE MATCH (s:Standard)-[:RELATED_TO]->(f:Framework)
USING INDEX s:Standard(name)
RETURN s, f LIMIT 1000;
"""

# Execute and print results
result = db.run_query(query)
for record in result:
    print(record)

db.close()
# modify query fie
query = """
CALL apoc.cypher.runTimeboxed(
    'MATCH (s:Standard)-[:RELATED_TO]->(f:Framework) RETURN s, f',
    {timeout: 5000}
);
"""
