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
    metro_stations = _load("metro_stations.json")
    rail_stations  = _load("national_rail_stations.json")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:

        session.run("MATCH (n) DETACH DELETE n")
        print("  Cleared existing graph data")

        # Create metro station nodes
        for s in metro_stations:
            session.run(
                "MERGE (n:MetroStation:Station {station_id: $station_id}) "
                "SET n.name = $name, n.lines = $lines",
                station_id=s["station_id"],
                name=s["name"],
                lines=s["lines"]
            )
        print("  Created MetroStation nodes")

        # Create national rail station nodes
        for s in rail_stations:
            session.run(
                "MERGE (n:NationalRailStation:Station {station_id: $station_id}) "
                "SET n.name = $name, n.lines = $lines",
                station_id=s["station_id"],
                name=s["name"],
                lines=s["lines"]
            )
        print("  Created NationalRailStation nodes")

        # Create metro links
        for s in metro_stations:
            for adj in s["adjacent_stations"]:
                session.run(
                    "MATCH (a:Station {station_id: $origin_id}), (b:Station {station_id: $dest_id}) "
                    "MERGE (a)-[r:METRO_LINK {line: $line}]->(b) "
                    "SET r.travel_time_min = $travel_time_min, "
                    "    r.fare_standard = 0.30, "
                    "    r.fare_first = 0.30",
                    origin_id=s["station_id"],
                    dest_id=adj["station_id"],
                    line=adj["line"],
                    travel_time_min=adj["travel_time_min"]
                )
        print("  Created METRO_LINK relationships")

        # Create national rail links
        for s in rail_stations:
            for adj in s["adjacent_stations"]:
                session.run(
                    "MATCH (a:Station {station_id: $origin_id}), (b:Station {station_id: $dest_id}) "
                    "MERGE (a)-[r:RAIL_LINK {line: $line}]->(b) "
                    "SET r.travel_time_min = $travel_time_min, "
                    "    r.fare_standard = 1.50, "
                    "    r.fare_first = 2.50",
                    origin_id=s["station_id"],
                    dest_id=adj["station_id"],
                    line=adj["line"],
                    travel_time_min=adj["travel_time_min"]
                )
        print("  Created RAIL_LINK relationships")

        # Create interchange relationships between metro and rail stations
        for s in metro_stations:
            if s["is_interchange_national_rail"] and s["interchange_national_rail_station_id"]:
                session.run(
                    "MATCH (a:MetroStation {station_id: $metro_id}), (b:NationalRailStation {station_id: $rail_id}) "
                    "MERGE (a)-[r1:INTERCHANGE_TO]->(b) "
                    "SET r1.travel_time_min = 5, r1.fare_standard = 0.0, r1.fare_first = 0.0 "
                    "MERGE (b)-[r2:INTERCHANGE_TO]->(a) "
                    "SET r2.travel_time_min = 5, r2.fare_standard = 0.0, r2.fare_first = 0.0",
                    metro_id=s["station_id"],
                    rail_id=s["interchange_national_rail_station_id"]
                )
        print("  Created INTERCHANGE_TO relationships")

    driver.close()
    print("\nNeo4j graph seeded successfully.")
    print("   Open http://localhost:7475 to explore the graph.")


if __name__ == "__main__":
    print("Connecting to Neo4j...")
    seed()
