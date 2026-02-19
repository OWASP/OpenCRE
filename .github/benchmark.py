import time
from neo4j import GraphDatabase

uri = "bolt://localhost:7687"
user = "neo4j"
password = "your_password"

driver = GraphDatabase.driver(uri, auth=(user, password))


def run_query():
    with driver.session() as session:
        start_time = time.time()
        session.run("MATCH (s:Standard)-[:RELATED_TO]->(f:Framework) RETURN s, f;")
        end_time = time.time()
        print(
            f"Execution Time BEFORE Optimization: {(end_time - start_time) * 1000:.2f} ms"
        )


run_query()
driver.close()


# modify banchmark.py
def run_optimized_query():
    with driver.session() as session:
        start_time = time.time()
        session.run(
            """
            MATCH (s:Standard)-[:RELATED_TO]->(f:Framework)
            USING INDEX s:Standard(name)
            RETURN s, f LIMIT 1000;
        """
        )
        end_time = time.time()
        print(
            f"Execution Time AFTER Optimization: {(end_time - start_time) * 1000:.2f} ms"
        )


run_optimized_query()
