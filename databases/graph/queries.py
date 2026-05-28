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


def _driver():
    """Return a Neo4j driver. Caller is responsible for closing."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a session, run Cypher, return data.

def example_count_nodes() -> int:
    """Example: count all nodes currently in the graph."""
    with _driver() as driver:
        with driver.session() as session:
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
    # --- CYPHER HINT ---
    # MATCH (o:Station {station_id: $origin_id}), (d:Station {station_id: $dest_id})
    # CALL apoc.algo.dijkstra(o, d, 'CONNECTS_TO', 'travel_time_min')
    # YIELD path, weight
    # RETURN [node in nodes(path) | {station_id: node.station_id, name: node.name}] AS stations,
    #        [rel in relationships(path) | {line: rel.line, travel_time_min: rel.travel_time_min}] AS legs,
    #        weight AS total_time_min
    # → wrap in {"found": bool, "total_time_min": weight, "path": stations, "legs": legs}
    raise NotImplementedError("TODO: implement after designing your graph schema")


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
    # --- CYPHER HINT ---
    # MATCH p = (o:Station {station_id: $origin})-[:CONNECTS_TO*1..10]->(d:Station {station_id: $dest})
    # WHERE NONE(n IN nodes(p) WHERE n.station_id = $avoid_station_id)
    # RETURN [n IN nodes(p) | {station_id: n.station_id, name: n.name}] AS route,
    #        reduce(t=0, r IN relationships(p) | t + r.travel_time_min) AS total_time
    # ORDER BY total_time LIMIT $max_routes
    raise NotImplementedError("TODO: implement after designing your graph schema")


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
    # --- CYPHER HINT ---
    # MATCH p = (o:Station {station_id: $origin_id})
    #           -[:CONNECTS_TO|INTERCHANGE_WITH*1..20]->
    #           (d:Station {station_id: $dest_id})
    # WHERE any(r IN relationships(p) WHERE type(r) = 'INTERCHANGE_WITH')
    # RETURN nodes(p), relationships(p)
    # ORDER BY size(nodes(p)) LIMIT 1
    raise NotImplementedError("TODO: implement after designing your graph schema")


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
    # --- CYPHER HINT ---
    # MATCH (s:Station {station_id: $station_id})-[:CONNECTS_TO*1..$hops]->(affected:Station)
    # RETURN DISTINCT affected.station_id AS station_id,
    #        affected.name AS name,
    #        min(length(path)) AS hops_away,
    #        affected.lines AS lines_affected
    raise NotImplementedError("TODO: implement after designing your graph schema")


# ── STATION CONNECTIONS ───────────────────────────────────────────────────────

def query_station_connections(station_id: str) -> list[dict]:
    """
    List all direct connections from a given station.

    Args:
        station_id: e.g. "MS01" or "NR01"
    """
    # --- CYPHER HINT ---
    # MATCH (s:Station {station_id: $station_id})-[r:CONNECTS_TO]->(n:Station)
    # RETURN n.station_id AS station_id, n.name AS name,
    #        r.line AS line, r.travel_time_min AS travel_time_min, r.network AS network
    raise NotImplementedError("TODO: implement after designing your graph schema")
