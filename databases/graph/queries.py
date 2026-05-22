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
    if network == "metro":
        rel_types = "METRO_LINK>"
    elif network == "rail":
        rel_types = "RAIL_LINK>"
    else:
        rel_types = "METRO_LINK>|RAIL_LINK>|INTERCHANGE_TO>"

    cypher = """
    MATCH (start:Station {station_id: $origin_id}), (end:Station {station_id: $destination_id})
    CALL apoc.algo.dijkstra(start, end, $rel_types, 'travel_time_min') YIELD path, weight
    RETURN [n in nodes(path) | {station_id: n.station_id, name: n.name}] AS path_stations,
           [r in relationships(path) | {
               from_station_id: startNode(r).station_id,
               from_station_name: startNode(r).name,
               to_station_id: endNode(r).station_id,
               to_station_name: endNode(r).name,
               line: r.line,
               travel_time_min: r.travel_time_min
           }] AS path_legs,
           weight AS total_time_min
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
                rel_types=rel_types
            )
            record = result.single()
            if not record or not record["path_stations"]:
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "total_time_min": 0.0,
                    "path": [],
                    "legs": []
                }

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "total_time_min": record["total_time_min"],
                "path": record["path_stations"],
                "legs": record["path_legs"]
            }


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
    if network == "metro":
        rel_types = "METRO_LINK>"
    elif network == "rail":
        rel_types = "RAIL_LINK>"
    else:
        rel_types = "METRO_LINK>|RAIL_LINK>|INTERCHANGE_TO>"

    fare_prop = "fare_first" if fare_class == "first" else "fare_standard"

    cypher = f"""
    MATCH (start:Station {{station_id: $origin_id}}), (end:Station {{station_id: $destination_id}})
    CALL apoc.algo.dijkstra(start, end, $rel_types, '{fare_prop}') YIELD path, weight
    RETURN [n in nodes(path) | {{station_id: n.station_id, name: n.name}}] AS path_stations,
           [r in relationships(path) | {{
               from_station_id: startNode(r).station_id,
               from_station_name: startNode(r).name,
               to_station_id: endNode(r).station_id,
               to_station_name: endNode(r).name,
               line: r.line,
               travel_time_min: r.travel_time_min,
               fare: r.{fare_prop}
           }}] AS path_legs,
           weight AS total_fare_usd
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
                rel_types=rel_types
            )
            record = result.single()
            if not record or not record["path_stations"]:
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "total_fare_usd": 0.0,
                    "stations": [],
                    "path": [],
                    "legs": []
                }

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "total_fare_usd": record["total_fare_usd"],
                "stations": record["path_stations"],
                "path": record["path_stations"],
                "legs": record["path_legs"]
            }


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
    if network == "metro":
        rel_pattern = "METRO_LINK"
    elif network == "rail":
        rel_pattern = "RAIL_LINK"
    else:
        rel_pattern = "METRO_LINK|RAIL_LINK|INTERCHANGE_TO"

    cypher = f"""
    MATCH path = (start:Station {{station_id: $origin_id}})-[r:{rel_pattern}*..15]->(end:Station {{station_id: $destination_id}})
    WHERE none(n in nodes(path)[1..-1] WHERE n.station_id = $avoid_station_id)
    RETURN [rel in relationships(path) | {{
               from_station_id: startNode(rel).station_id,
               from_station_name: startNode(rel).name,
               to_station_id: endNode(rel).station_id,
               to_station_name: endNode(rel).name,
               line: rel.line,
               travel_time_min: rel.travel_time_min
           }}] AS path_legs,
           reduce(s = 0, rel in relationships(path) | s + rel.travel_time_min) AS total_time
    ORDER BY total_time ASC
    LIMIT $max_routes
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
                avoid_station_id=avoid_station_id,
                max_routes=max_routes
            )
            return [record["path_legs"] for record in result]


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
    rel_types = "METRO_LINK>|RAIL_LINK>|INTERCHANGE_TO>"

    cypher = """
    MATCH (start:Station {station_id: $origin_id}), (end:Station {station_id: $destination_id})
    CALL apoc.algo.dijkstra(start, end, $rel_types, 'travel_time_min') YIELD path, weight
    RETURN [n in nodes(path) | {station_id: n.station_id, name: n.name}] AS path_stations,
           [r in relationships(path) | {
               from_station_id: startNode(r).station_id,
               from_station_name: startNode(r).name,
               to_station_id: endNode(r).station_id,
               to_station_name: endNode(r).name,
               type: type(r),
               line: r.line,
               travel_time_min: r.travel_time_min
           }] AS path_legs,
           weight AS total_time_min
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
                rel_types=rel_types
            )
            record = result.single()
            if not record or not record["path_stations"]:
                return {
                    "found": False,
                    "stations": [],
                    "path": [],
                    "interchange_points": [],
                    "total_time_min": 0.0,
                    "legs": []
                }

            path_legs = record["path_legs"]
            interchange_points = []
            for leg in path_legs:
                if leg["type"] == "INTERCHANGE_TO":
                    interchange_points.append(leg["from_station_id"])
                    interchange_points.append(leg["to_station_id"])

            # Deduplicate and keep order
            seen = set()
            interchange_points = [x for x in interchange_points if not (x in seen or seen.add(x))]

            return {
                "found": True,
                "stations": record["path_stations"],
                "path": record["path_stations"],
                "interchange_points": interchange_points,
                "total_time_min": record["total_time_min"],
                "legs": path_legs
            }


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
    hops = int(hops)
    cypher = f"""
    MATCH path = (start:Station {{station_id: $delayed_station_id}})-[r:METRO_LINK|RAIL_LINK*..{hops}]-(other:Station)
    WHERE other <> start
    WITH other, min(length(path)) AS hops_away
    RETURN other.station_id AS station_id,
           other.name AS name,
           hops_away,
           other.lines AS lines_affected
    ORDER BY hops_away ASC
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, delayed_station_id=delayed_station_id)
            return [
                {
                    "station_id": record["station_id"],
                    "name": record["name"],
                    "hops_away": record["hops_away"],
                    "lines_affected": record["lines_affected"]
                }
                for record in result
            ]


# ── STATION CONNECTIONS ───────────────────────────────────────────────────────

def query_station_connections(station_id: str) -> list[dict]:
    """
    List all direct connections from a given station.

    Args:
        station_id: e.g. "MS01" or "NR01"
    """
    cypher = """
    MATCH (start:Station {station_id: $station_id})-[r:METRO_LINK|RAIL_LINK|INTERCHANGE_TO]->(other:Station)
    RETURN other.station_id AS station_id,
           other.name AS name,
           coalesce(r.line, 'Transfer') AS line,
           r.travel_time_min AS travel_time_min
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, station_id=station_id)
            return [
                {
                    "station_id": record["station_id"],
                    "name": record["name"],
                    "line": record["line"],
                    "travel_time_min": record["travel_time_min"]
                }
                for record in result
            ]
