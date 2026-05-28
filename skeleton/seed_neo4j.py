"""
TransitFlow — Neo4j Seeder
Run once after starting Docker:
    python skeleton/seed_neo4j.py

Loads station and network data from train-mock-data/:
  - metro_stations.json         — city metro stations and adjacencies
  - national_rail_stations.json — national rail stations and adjacencies

Design your graph schema (node labels, relationship types, properties)
based on the data in these files, then implement the seed() function below.
"""

import json
import os
import sys

sys.path.insert(0, ".")

from neo4j import GraphDatabase
from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "train-mock-data")
)


def _load(filename):
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def seed():
    """Seeds the Neo4j database with Station nodes and CONNECTS_TO/INTERCHANGE_WITH relationships."""
    metro_stations = _load("metro_stations.json")
    rail_stations  = _load("national_rail_stations.json")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:

        session.run("MATCH (n) DETACH DELETE n")
        print("  Cleared existing graph data")


        # Create metro station nodes
        for s in metro_stations:
            session.run(
                "MERGE (s:Station {station_id: $station_id}) "
                "SET s.name = $name, "
                "    s.network = 'metro', "
                "    s.lines = $lines",
                station_id=s["station_id"],
                name=s["name"],
                lines=s["lines"]
            )
        print("  Created Metro nodes")

        # Create national rail station nodes
        for s in rail_stations:
            session.run(
                "MERGE (s:Station {station_id: $station_id}) "
                "SET s.name = $name, "
                "    s.network = 'national_rail', "
                "    s.lines = $lines",
                station_id=s["station_id"],
                name=s["name"],
                lines=s["lines"]
            )
        print("  Created National Rail nodes")

        # Create metro links
        metro_edges = []
        for s in metro_stations:
            for adj in s.get("adjacent_stations", []):
                metro_edges.append({
                    "from_id": s["station_id"],
                    "to_id": adj["station_id"],
                    "line": adj["line"],
                    "travel_time_min": adj["travel_time_min"],
                    "network": "metro"
                })

        session.run(
            "UNWIND $edges AS edge "
            "MATCH (a:Station {station_id: edge.from_id}) "
            "MATCH (b:Station {station_id: edge.to_id}) "
            "MERGE (a)-[r:CONNECTS_TO {line: edge.line, network: edge.network}]->(b) "
            "SET r.travel_time_min = edge.travel_time_min",
            edges=metro_edges
        )
        print(f"  Created {len(metro_edges)} metro CONNECTS_TO edges")

        # Create national rail links
        rail_edges = []
        for s in rail_stations:
            for adj in s.get("adjacent_stations", []):
                rail_edges.append({
                    "from_id": s["station_id"],
                    "to_id": adj["station_id"],
                    "line": adj["line"],
                    "travel_time_min": adj["travel_time_min"],
                    "network": "national_rail"
                })

        session.run(
            "UNWIND $edges AS edge "
            "MATCH (a:Station {station_id: edge.from_id}) "
            "MATCH (b:Station {station_id: edge.to_id}) "
            "MERGE (a)-[r:CONNECTS_TO {line: edge.line, network: edge.network}]->(b) "
            "SET r.travel_time_min = edge.travel_time_min",
            edges=rail_edges
        )
        print(f"  Created {len(rail_edges)} national rail CONNECTS_TO edges")

        # Create interchange relationships between metro and rail stations
        interchange_count = 0
        for s in metro_stations:
            if s.get("is_interchange_national_rail") and s.get("interchange_national_rail_station_id"):
                session.run(
                    "MATCH (m:Station {station_id: $metro_id}) "
                    "MATCH (nr:Station {station_id: $nr_id}) "
                    "MERGE (m)-[:INTERCHANGE_WITH]->(nr) "
                    "MERGE (nr)-[:INTERCHANGE_WITH]->(m)",
                    metro_id=s["station_id"],
                    nr_id=s["interchange_national_rail_station_id"]
                )
                interchange_count += 2
        print(f"  Created {interchange_count} INTERCHANGE_WITH edges")

        nodes_count = session.run("MATCH (n) RETURN count(n) AS nodes").single()["nodes"]
        edges_count = session.run("MATCH ()-[r]->() RETURN count(r) AS edges").single()["edges"]
        print(f"  Validation: {nodes_count} nodes, {edges_count} edges")

    driver.close()
    print("\nNeo4j graph seeded successfully.")
    print("   Open http://localhost:7475 to explore the graph.")


if __name__ == "__main__":
    print("Connecting to Neo4j...")
    seed()
