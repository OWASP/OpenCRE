import os
from neo4j import GraphDatabase
from dotenv import load_dotenv
# Neo4j connection details
uri = "bolt://localhost:7687"
user = "neo4j"
password = "Hardik123@"

# Connect to Neo4j
driver = GraphDatabase.driver(uri, auth=(user, password))

def test_connection():
    with driver.session() as session:
        result = session.run("RETURN 'Connected to Neo4j' AS message")
        for record in result:
            print(record["message"])

test_connection()
driver.close()