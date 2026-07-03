"""
Neo4j driver singleton. On AWS: if Neo4j runs on AuraDB (SaaS), Lambda just
needs outbound internet (NAT gateway if Lambda is in a VPC). If Neo4j is
self-hosted on EC2, Lambda must be attached to the same VPC/subnet as the
instance. Either way, pull credentials from Secrets Manager, not plain env
vars, in production — get_driver() below reads from env for local/dev use;
swap _get_credentials() to call boto3 secretsmanager for prod.
"""
import os
from neo4j import GraphDatabase, Driver
from typing import List, Dict, Any

_driver: Driver | None = None


def _get_credentials() -> tuple[str, str, str]:
    uri = os.environ["NEO4J_URI"]
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ["NEO4J_PASSWORD"]
    return uri, user, password

    # --- production variant ---
    # import boto3, json
    # client = boto3.client("secretsmanager")
    # secret = json.loads(client.get_secret_value(SecretId=os.environ["NEO4J_SECRET_ARN"])["SecretString"])
    # return secret["uri"], secret["user"], secret["password"]


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        uri, user, password = _get_credentials()
        _driver = GraphDatabase.driver(uri, auth=(user, password))
    return _driver


def run_query(cypher: str, params: Dict[str, Any] = None) -> List[Dict]:
    driver = get_driver()
    with driver.session() as session:
        return [record.data() for record in session.run(cypher, params or {})]


def run_write(cypher: str, params: Dict[str, Any] = None) -> None:
    driver = get_driver()
    with driver.session() as session:
        session.execute_write(lambda tx: tx.run(cypher, params or {}).consume())


def run_write_batch(statements: List[tuple[str, Dict[str, Any]]]) -> None:
    """Runs multiple statements in a single transaction — used by the direct
    ETL path for structured rows so a whole batch commits atomically."""
    driver = get_driver()
    with driver.session() as session:
        def _tx(tx):
            for cypher, params in statements:
                tx.run(cypher, params)
        session.execute_write(_tx)


def ping() -> bool:
    try:
        run_query("RETURN 1 AS ok")
        return True
    except Exception as e:
        print(f"[graph.client] connection failed: {e}")
        return False