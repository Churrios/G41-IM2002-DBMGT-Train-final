"""
TransitFlow — Neo4j Graph Database Layer
=========================================
This module handles all queries to Neo4j.

GRAPH ROLE:
  - Model the dual transit network (city metro M1–M4 + national rail NR1–NR2)
  - Find fastest routes (Dijkstra by travel_time_min via APOC)
  - Find cheapest routes (Dijkstra by fare via APOC)
  - Find alternative routes avoiding a given station
  - Find cross-network interchange paths (metro → rail or rail → metro)
  - Show delay ripple: which stations are affected within N hops

STUDENT TASK
------------
Design your graph schema (node labels, relationship types, properties)
based on the data in train-mock-data/, seed it with skeleton/seed_neo4j.py,
then implement the query_ functions below.

Functions prefixed with `query_` are called by the agent (skeleton/agent.py).
"""

from __future__ import annotations

from typing import Optional

from neo4j import GraphDatabase

from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


# Module-level singleton driver — created once, shared across all queries.
# Do NOT use `with _DRIVER as driver:` — that closes the driver on context exit.
# Always obtain a session with `with _get_driver().session() as session:`.
_DRIVER = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def _get_driver():
    """Return the shared module-level Neo4j driver singleton."""
    return _DRIVER


def _infer_network(station_id: str) -> str:
    """Infer the transit network from a station ID prefix.

    Args:
        station_id: e.g. "MS01" or "NR01"

    Returns:
        "metro", "national_rail", or "unknown"
    """
    if station_id.upper().startswith("MS"):
        return "metro"
    elif station_id.upper().startswith("NR"):
        return "national_rail"
    return "unknown"


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a session, run Cypher, return data.

def example_count_nodes() -> int:
    """Example: count all nodes currently in the graph."""
    with _get_driver().session() as session:
        result = session.run("MATCH (n) RETURN count(n) AS total")
        return result.single()["total"]

# TODO: Implement the query_ functions below.
# ─────────────────────────────────────────────────────────────────────────────


# ── FASTEST ROUTE (Dijkstra by travel_time_min) ───────────────────────────────

def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
) -> dict:
    """
    Find the fastest path between two stations, minimising total travel time.
    Uses apoc.algo.dijkstra (APOC required; enabled in docker-compose.yml).

    Args:
        origin_id:       e.g. "MS01" or "NR01"
        destination_id:  e.g. "MS09" or "NR05"
        network:         "metro", "rail", or "auto" (inferred from IDs)

    Returns:
        dict with keys: found, origin_id, destination_id,
                        total_time_min, path (list of station dicts), legs
    """
    _not_found = {
        "found": False,
        "origin_id": origin_id,
        "destination_id": destination_id,
        "total_time_min": None,
        "path": [],
        "legs": [],
    }
    try:
        with _get_driver().session() as session:
            result = session.run(
                """
                MATCH (o:Station {station_id: $origin_id}),
                      (d:Station {station_id: $dest_id})
                CALL apoc.algo.dijkstra(o, d, 'CONNECTS_TO', 'travel_time_min')
                YIELD path, weight
                RETURN
                    [node IN nodes(path) |
                        {station_id: node.station_id, name: node.name}] AS stations,
                    [rel IN relationships(path) |
                        {line: rel.line, travel_time_min: rel.travel_time_min}] AS legs,
                    weight AS total_time_min
                """,
                origin_id=origin_id,
                dest_id=destination_id,
            )
            record = result.single()
            if record is None:
                return _not_found
            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "total_time_min": int(record["total_time_min"]),
                "path": list(record["stations"]),
                "legs": list(record["legs"]),
            }
    except Exception:
        return _not_found


# ── CHEAPEST ROUTE (Dijkstra by fare) ────────────────────────────────────────

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard",
) -> dict:
    """
    Find the cheapest path between two stations, minimising total estimated fare.

    Args:
        origin_id:       e.g. "NR01"
        destination_id:  e.g. "NR05"
        network:         "metro", "rail", or "auto"
        fare_class:      "standard" or "first" (national rail only)

    Returns:
        dict with found, total_fare_usd (approximate), stations, legs
    """
    # --- CYPHER HINT ---
    # 注意：fare 不存在 edge 上，需用 travel_time_min 作為 proxy
    # 或者：從 PostgreSQL 取 base_fare + per_stop * stop_count 估算
    # Cypher: 同 shortest_route，但回傳後在 Python 計算 fare
    # CALL apoc.algo.dijkstra(o, d, 'CONNECTS_TO', 'travel_time_min') ...
    # → 再 call query_national_rail_fare / query_metro_fare 計算 total_fare_usd
    raise NotImplementedError("TODO: implement after designing your graph schema")


# ── ALTERNATIVE ROUTES (avoiding a station) ───────────────────────────────────

def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
    max_routes: int = 3,
) -> list[list[dict]]:
    """
    Find paths between two stations that avoid a specific intermediate station.
    Useful for routing around a delayed or closed station.

    Args:
        origin_id:         e.g. "NR01"
        destination_id:    e.g. "NR05"
        avoid_station_id:  e.g. "NR03"
        network:           "metro", "rail", or "auto"
        max_routes:        max number of alternatives to return

    Returns:
        List of routes, each route is a list of leg dicts
    """
    try:
        with _get_driver().session() as session:
            result = session.run(
                """
                MATCH p = (o:Station {station_id: $origin_id})
                          -[:CONNECTS_TO*1..10]->
                          (d:Station {station_id: $dest_id})
                WHERE NONE(n IN nodes(p) WHERE n.station_id = $avoid_station_id)
                RETURN
                    [n IN nodes(p) | {station_id: n.station_id, name: n.name}] AS route,
                    reduce(t = 0, r IN relationships(p) | t + r.travel_time_min)
                        AS total_time_min
                ORDER BY total_time_min
                LIMIT $max_routes
                """,
                origin_id=origin_id,
                dest_id=destination_id,
                avoid_station_id=avoid_station_id,
                max_routes=max_routes,
            )
            return [
                {"route": list(record["route"]), "total_time_min": record["total_time_min"]}
                for record in result
            ]
    except Exception:
        return []


# ── CROSS-NETWORK INTERCHANGE PATH ───────────────────────────────────────────

def query_interchange_path(origin_id: str, destination_id: str) -> dict:
    """
    Find a path between a metro station and a national rail station (or vice versa)
    crossing the network boundary via interchange relationships.

    Args:
        origin_id:       e.g. "MS03" (metro) or "NR05" (national rail)
        destination_id:  e.g. "NR05" (national rail) or "MS09" (metro)

    Returns:
        dict with found, stations list, interchange points, total_time_min
    """
    _not_found: dict = {
        "found": False,
        "stations": [],
        "interchanges": [],
        "total_time_min": None,
    }
    _TRANSFER_TIME = 5  # fixed minutes per INTERCHANGE_WITH hop

    try:
        with _get_driver().session() as session:
            result = session.run(
                """
                MATCH p = (o:Station {station_id: $origin_id})
                          -[:CONNECTS_TO|INTERCHANGE_WITH*1..20]->
                          (d:Station {station_id: $dest_id})
                WHERE any(r IN relationships(p) WHERE type(r) = 'INTERCHANGE_WITH')
                RETURN nodes(p) AS path_nodes, relationships(p) AS path_rels
                ORDER BY length(p)
                LIMIT 1
                """,
                origin_id=origin_id,
                dest_id=destination_id,
            )
            record = result.single()
            if record is None:
                return _not_found

            path_nodes = list(record["path_nodes"])
            path_rels = list(record["path_rels"])

            # --- identify which node indices border an INTERCHANGE_WITH edge ---
            interchange_node_ids: set[str] = set()
            interchanges: list[dict] = []

            for i, rel in enumerate(path_rels):
                if rel.type == "INTERCHANGE_WITH":
                    from_node = path_nodes[i]
                    to_node = path_nodes[i + 1]
                    interchange_node_ids.add(from_node["station_id"])
                    interchange_node_ids.add(to_node["station_id"])
                    interchanges.append({
                        "from": from_node["station_id"],
                        "to": to_node["station_id"],
                        "transfer_time_min": _TRANSFER_TIME,
                    })

            # --- build station list, marking interchange nodes ---
            stations = [
                {
                    "station_id": n["station_id"],
                    "name": n["name"],
                    "interchange": n["station_id"] in interchange_node_ids,
                }
                for n in path_nodes
            ]

            # --- total time: sum CONNECTS_TO weights + 5 min per interchange ---
            travel_time = sum(
                rel["travel_time_min"]
                for rel in path_rels
                if rel.type == "CONNECTS_TO" and rel["travel_time_min"] is not None
            )
            total_time_min = travel_time + len(interchanges) * _TRANSFER_TIME

            return {
                "found": True,
                "stations": stations,
                "interchanges": interchanges,
                "total_time_min": total_time_min,
            }
    except Exception:
        return _not_found


# ── DELAY RIPPLE ANALYSIS ─────────────────────────────────────────────────────

def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]:
    """
    Find all stations within N hops of a delayed or disrupted station.
    Works on both metro and national rail networks.

    Args:
        delayed_station_id: e.g. "NR03" or "MS01"
        hops:               how many connections out to search (default 2)

    Returns:
        List of dicts: {station_id, name, hops_away, lines_affected}
    """
    try:
        safe_hops = max(0, int(hops))  # int() conversion prevents injection
        with _get_driver().session() as session:
            # Step 1 — always fetch the start node (hops_away=0)
            start_record = session.run(
                "MATCH (s:Station {station_id: $sid}) "
                "RETURN s.station_id AS station_id, s.name AS name, s.lines AS lines_affected",
                sid=delayed_station_id,
            ).single()
            if start_record is None:
                return []

            start_dict = {
                "station_id": start_record["station_id"],
                "name": start_record["name"],
                "hops_away": 0,
                "lines_affected": list(start_record["lines_affected"] or []),
            }

            # Step 2 — hops=0: only the delayed station itself
            if safe_hops == 0:
                return [start_dict]

            # Step 3 — hops≥1: embed safe integer into Cypher (Cypher disallows $param here)
            cypher = f"""
                MATCH (s:Station {{station_id: $station_id}})
                      -[:CONNECTS_TO*1..{safe_hops}]->(affected:Station)
                RETURN DISTINCT
                    affected.station_id AS station_id,
                    affected.name       AS name,
                    min(length(shortestPath(
                        (s)-[:CONNECTS_TO*]-(affected)
                    )))                 AS hops_away,
                    affected.lines      AS lines_affected
                ORDER BY hops_away
            """
            result = session.run(cypher, station_id=delayed_station_id)
            neighbours = [
                {
                    "station_id": r["station_id"],
                    "name": r["name"],
                    "hops_away": r["hops_away"],
                    "lines_affected": list(r["lines_affected"] or []),
                }
                for r in result
            ]
            return [start_dict] + neighbours
    except Exception:
        return []


# ── STATION CONNECTIONS ───────────────────────────────────────────────────────

def query_station_connections(station_id: str) -> list[dict]:
    """
    List all direct connections from a given station.

    Args:
        station_id: e.g. "MS01" or "NR01"
    """
    try:
        with _get_driver().session() as session:
            result = session.run(
                """
                MATCH (s:Station {station_id: $station_id})-[r:CONNECTS_TO]->(n:Station)
                RETURN n.station_id AS station_id,
                       n.name       AS name,
                       r.line       AS line,
                       r.travel_time_min AS travel_time_min,
                       r.network    AS network
                ORDER BY r.travel_time_min
                """,
                station_id=station_id,
            )
            return [dict(record) for record in result]
    except Exception:
        return []
