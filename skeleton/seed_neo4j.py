"""
TransitFlow — Neo4j Seeder
Run once after starting Docker:
    python skeleton/seed_neo4j.py

Loads station and network data from train-mock-data/:
  - metro_stations.json         — city metro stations and adjacencies
  - national_rail_stations.json — national rail stations and adjacencies

Graph schema:
  Nodes:  MetroStation, NationalRailStation
  Edges:  METRO_LINK, RAIL_LINK, INTERCHANGE_TO
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
    """Seeds Neo4j with MetroStation/NationalRailStation nodes and all relationships.

    Uses MERGE throughout — safe to run multiple times without creating duplicates.
    To fully reset the graph, use: docker compose down -v && docker compose up -d
    (DETACH DELETE is intentionally absent to preserve idempotency.)
    """
    metro_stations = _load("metro_stations.json")
    rail_stations  = _load("national_rail_stations.json")

    with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
        with driver.session() as session:

            # ── Unique constraints (idempotent) ──────────────────────────────
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (s:MetroStation) "
                "REQUIRE s.station_id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (s:NationalRailStation) "
                "REQUIRE s.station_id IS UNIQUE"
            )
            print("  Constraints ensured")

            # ── MetroStation nodes ────────────────────────────────────────────
            for s in metro_stations:
                session.run(
                    """
                    MERGE (st:MetroStation {station_id: $station_id})
                    SET st.name = $name,
                        st.lines = $lines,
                        st.is_interchange_national_rail = $is_interchange_national_rail
                    """,
                    station_id=s["station_id"],
                    name=s["name"],
                    lines=s["lines"],
                    is_interchange_national_rail=bool(s.get("is_interchange_national_rail", False)),
                )
            print(f"  Merged {len(metro_stations)} MetroStation nodes")

            # ── NationalRailStation nodes ─────────────────────────────────────
            for s in rail_stations:
                session.run(
                    """
                    MERGE (st:NationalRailStation {station_id: $station_id})
                    SET st.name = $name,
                        st.lines = $lines,
                        st.is_interchange_metro = $is_interchange_metro,
                        st.interchange_metro_station_id = $interchange_metro_station_id
                    """,
                    station_id=s["station_id"],
                    name=s["name"],
                    lines=s["lines"],
                    is_interchange_metro=bool(s.get("is_interchange_metro", False)),
                    interchange_metro_station_id=s.get("interchange_metro_station_id"),
                )
            print(f"  Merged {len(rail_stations)} NationalRailStation nodes")

            # ── Validation ────────────────────────────────────────────────────
            metro_count = session.run(
                "MATCH (n:MetroStation) RETURN count(n) AS c"
            ).single()["c"]
            rail_count = session.run(
                "MATCH (n:NationalRailStation) RETURN count(n) AS c"
            ).single()["c"]
            print(f"  Validation: {metro_count} MetroStation, {rail_count} NationalRailStation")

    print("\nNeo4j nodes seeded successfully.")
    print("   Open http://localhost:7475 to explore the graph.")


if __name__ == "__main__":
    print("Connecting to Neo4j...")
    seed()
