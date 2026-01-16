from neo4j import GraphDatabase

# Connection details
uri = "bolt://localhost:7687"
username = "neo4j"
password = "your_password"

# Connect to Neo4j
driver = GraphDatabase.driver(uri, auth=(username, password))


# Function to test connection
def test_connection():
    with driver.session() as session:
        result = session.run("RETURN 'Connection successful' AS message")
        print(result.single()["message"])


if __name__ == "_main_":
    test_connection()
