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

            # ── METRO_LINK relationships ──────────────────────────────────────
            # fare_usd is stored on each edge so Dijkstra can use it as a weight
            metro_edges = []
            for s in metro_stations:
                t = s["travel_time_min"] if "travel_time_min" in s else None
                for adj in s.get("adjacent_stations", []):
                    t = adj["travel_time_min"]
                    metro_edges.append({
                        "from_id": s["station_id"],
                        "to_id":   adj["station_id"],
                        "line":    adj["line"],
                        "travel_time_min": t,
                        "fare_usd": round(1.0 + 0.5 * t, 2),
                    })

            session.run(
                """
                UNWIND $edges AS e
                MATCH (a:MetroStation {station_id: e.from_id})
                MATCH (b:MetroStation {station_id: e.to_id})
                MERGE (a)-[r:METRO_LINK {line: e.line}]->(b)
                SET r.travel_time_min = e.travel_time_min,
                    r.fare_usd        = e.fare_usd
                """,
                edges=metro_edges,
            )
            print(f"  Merged {len(metro_edges)} METRO_LINK edges")

            # ── RAIL_LINK relationships ───────────────────────────────────────
            # Two fare tiers (standard / first class) stored as separate properties
            rail_edges = []
            for s in rail_stations:
                for adj in s.get("adjacent_stations", []):
                    t = adj["travel_time_min"]
                    rail_edges.append({
                        "from_id": s["station_id"],
                        "to_id":   adj["station_id"],
                        "line":    adj["line"],
                        "travel_time_min":    t,
                        "fare_standard_usd":  round(2.0 + 1.2 * t, 2),
                        "fare_first_usd":     round(2.0 + 2.0 * t, 2),
                    })

            session.run(
                """
                UNWIND $edges AS e
                MATCH (a:NationalRailStation {station_id: e.from_id})
                MATCH (b:NationalRailStation {station_id: e.to_id})
                MERGE (a)-[r:RAIL_LINK {line: e.line}]->(b)
                SET r.travel_time_min   = e.travel_time_min,
                    r.fare_standard_usd = e.fare_standard_usd,
                    r.fare_first_usd    = e.fare_first_usd
                """,
                edges=rail_edges,
            )
            print(f"  Merged {len(rail_edges)} RAIL_LINK edges")

            # ── INTERCHANGE_TO relationships ──────────────────────────────────
            # Two directed edges per interchange pair so both Dijkstra directions work.
            # transfer_time_min is fixed at 5 min (not travel_time_min — INTERCHANGE_TO
            # has no travel_time_min, so interchange_path sums it separately).
            interchange_count = 0
            for s in metro_stations:
                if s.get("is_interchange_national_rail") and s.get("interchange_national_rail_station_id"):
                    session.run(
                        """
                        MATCH (m:MetroStation       {station_id: $metro_id})
                        MATCH (nr:NationalRailStation {station_id: $nr_id})
                        MERGE (m)-[r1:INTERCHANGE_TO]->(nr)
                        SET r1.transfer_time_min = 5
                        MERGE (nr)-[r2:INTERCHANGE_TO]->(m)
                        SET r2.transfer_time_min = 5
                        """,
                        metro_id=s["station_id"],
                        nr_id=s["interchange_national_rail_station_id"],
                    )
                    interchange_count += 2
            print(f"  Merged {interchange_count} INTERCHANGE_TO edges")

            # ── Validation ────────────────────────────────────────────────────
            metro_count = session.run(
                "MATCH (n:MetroStation) RETURN count(n) AS c"
            ).single()["c"]
            rail_count = session.run(
                "MATCH (n:NationalRailStation) RETURN count(n) AS c"
            ).single()["c"]
            ml_count = session.run(
                "MATCH ()-[r:METRO_LINK]->() RETURN count(r) AS c"
            ).single()["c"]
            rl_count = session.run(
                "MATCH ()-[r:RAIL_LINK]->() RETURN count(r) AS c"
            ).single()["c"]
            ic_count = session.run(
                "MATCH ()-[r:INTERCHANGE_TO]->() RETURN count(r) AS c"
            ).single()["c"]
            print(
                f"  Validation: {metro_count} MetroStation, {rail_count} NationalRailStation | "
                f"{ml_count} METRO_LINK, {rl_count} RAIL_LINK, {ic_count} INTERCHANGE_TO"
            )

    print("\nNeo4j graph seeded successfully.")
    print("   Open http://localhost:7475 to explore the graph.")


if __name__ == "__main__":
    print("Connecting to Neo4j...")
    seed()
