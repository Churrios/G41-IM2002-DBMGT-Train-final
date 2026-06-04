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

Schema:
  Nodes:  MetroStation, NationalRailStation
  Edges:  METRO_LINK (fare_usd), RAIL_LINK (fare_standard_usd / fare_first_usd),
          INTERCHANGE_TO (transfer_time_min=5)
"""

from __future__ import annotations

from typing import Optional

from neo4j import GraphDatabase

from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def _driver():
    # per-call driver; each query opens and closes its own connection pool entry
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


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


# ── FASTEST ROUTE (Dijkstra by travel_time_min) ───────────────────────────────

def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",  # accepted for API compatibility; query covers both networks
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
        with _driver() as driver:
            with driver.session() as session:
                # INTERCHANGE_TO is intentionally excluded: shortest_route is
                # same-network only; cross-network queries use interchange_path.
                result = session.run(
                    """
                    MATCH (o {station_id: $origin_id}),
                          (d {station_id: $dest_id})
                    CALL apoc.algo.dijkstra(o, d, 'METRO_LINK|RAIL_LINK', 'travel_time_min')
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
    Find the cheapest path between two stations, minimising total fare.
    Uses edge fare attributes stored during seeding (not estimated at query time).

    Args:
        origin_id:       e.g. "NR01"
        destination_id:  e.g. "NR05"
        network:         "metro", "rail", or "auto"
        fare_class:      "standard" or "first" (national rail only)

    Returns:
        dict with found, total_fare_usd, fare_class, path, legs
    """
    _not_found = {
        "found": False,
        "origin_id": origin_id,
        "destination_id": destination_id,
        "total_fare_usd": None,
        "fare_class": fare_class,
        "path": [],
        "legs": [],
    }
    try:
        # _infer_network is used because the agent always passes network="auto";
        # comparing network == "national_rail" literally would never match "auto".
        # Metro weight is fare_usd (single tier); rail has standard/first split.
        net = network if network in ("metro", "national_rail") else _infer_network(origin_id)
        if net == "rail":
            net = "national_rail"

        if net == "metro":
            weight_prop = "fare_usd"
        elif fare_class == "first":
            weight_prop = "fare_first_usd"
        else:
            weight_prop = "fare_standard_usd"

        # weight_prop is always one of three known string literals — safe to f-string
        cypher = f"""
            MATCH (o {{station_id: $origin_id}}),
                  (d {{station_id: $dest_id}})
            CALL apoc.algo.dijkstra(o, d, 'METRO_LINK|RAIL_LINK', '{weight_prop}')
            YIELD path, weight
            RETURN
                [node IN nodes(path) |
                    {{station_id: node.station_id, name: node.name}}] AS stations,
                [rel IN relationships(path) |
                    {{line: rel.line, travel_time_min: rel.travel_time_min,
                      fare_usd: rel.{weight_prop}}}] AS legs,
                weight AS total_fare_usd
        """
        with _driver() as driver:
            with driver.session() as session:
                result = session.run(
                    cypher,
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
                    "total_fare_usd": round(float(record["total_fare_usd"]), 2),
                    "fare_class": fare_class,
                    "path": list(record["stations"]),
                    "legs": list(record["legs"]),
                }
    except Exception:
        return _not_found


# ── ALTERNATIVE ROUTES (avoiding a station) ───────────────────────────────────

def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",  # accepted for API compatibility; query covers both networks
    max_routes: int = 3,
) -> list[dict]:
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
        List of routes, each with keys: route (list of station dicts), total_time_min
    """
    try:
        with _driver() as driver:
            with driver.session() as session:
                result = session.run(
                    """
                    MATCH p = (o {station_id: $origin_id})
                              -[:METRO_LINK|RAIL_LINK*1..10]-
                              (d {station_id: $dest_id})
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
    crossing the network boundary via INTERCHANGE_TO relationships.

    Args:
        origin_id:       e.g. "MS01" (metro) or "NR05" (national rail)
        destination_id:  e.g. "NR05" (national rail) or "MS09" (metro)

    Returns:
        dict with found, path (list of station dicts with interchange flag),
        interchange_points (list of transfer dicts), total_time_min
    """
    _not_found: dict = {
        "found": False,
        "path": [],
        "interchange_points": [],
        "total_time_min": None,
    }
    _TRANSFER_TIME = 5  # fixed minutes per INTERCHANGE_TO hop

    try:
        with _driver() as driver:
            with driver.session() as session:
                result = session.run(
                    """
                    MATCH p = (o {station_id: $origin_id})
                              -[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..20]-
                              (d {station_id: $dest_id})
                    WHERE any(r IN relationships(p) WHERE type(r) = 'INTERCHANGE_TO')
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
                path_rels  = list(record["path_rels"])

                interchange_node_ids: set[str] = set()
                interchange_points: list[dict] = []

                for i, rel in enumerate(path_rels):
                    if rel.type == "INTERCHANGE_TO":
                        from_node = path_nodes[i]
                        to_node   = path_nodes[i + 1]
                        interchange_node_ids.add(from_node["station_id"])
                        interchange_node_ids.add(to_node["station_id"])
                        interchange_points.append({
                            "from": from_node["station_id"],
                            "to":   to_node["station_id"],
                            "transfer_time_min": _TRANSFER_TIME,
                        })

                path = [
                    {
                        "station_id": n["station_id"],
                        "name":       n["name"],
                        "interchange": n["station_id"] in interchange_node_ids,
                    }
                    for n in path_nodes
                ]

                # Only *_LINK edges carry travel_time_min; INTERCHANGE_TO has none.
                # Transfer time is added separately as count × 5 min.
                travel_time = sum(
                    rel["travel_time_min"]
                    for rel in path_rels
                    if rel.type in ("METRO_LINK", "RAIL_LINK")
                    and rel["travel_time_min"] is not None
                )
                total_time_min = travel_time + len(interchange_points) * _TRANSFER_TIME

                return {
                    "found": True,
                    "path": path,
                    "interchange_points": interchange_points,
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
        # int() + f-string: Cypher does not accept $param for variable-length upper bound
        safe_hops = max(0, int(hops))
        with _driver() as driver:
            with driver.session() as session:
                start_record = session.run(
                    "MATCH (s {station_id: $sid}) "
                    "RETURN s.station_id AS station_id, s.name AS name, s.lines AS lines_affected",
                    sid=delayed_station_id,
                ).single()
                if start_record is None:
                    return []

                start_dict = {
                    "station_id":    start_record["station_id"],
                    "name":          start_record["name"],
                    "hops_away":     0,
                    "lines_affected": list(start_record["lines_affected"] or []),
                }

                if safe_hops == 0:
                    return [start_dict]

                cypher = f"""
                    MATCH (s {{station_id: $station_id}})
                          -[:METRO_LINK|RAIL_LINK*1..{safe_hops}]-
                          (affected)
                    RETURN DISTINCT
                        affected.station_id AS station_id,
                        affected.name       AS name,
                        min(length(shortestPath(
                            (s)-[:METRO_LINK|RAIL_LINK*]-(affected)
                        )))                 AS hops_away,
                        affected.lines      AS lines_affected
                    ORDER BY hops_away
                """
                result = session.run(cypher, station_id=delayed_station_id)
                neighbours = [
                    {
                        "station_id":    r["station_id"],
                        "name":          r["name"],
                        "hops_away":     r["hops_away"],
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

    Returns:
        List of dicts: {station_id, name, line, travel_time_min}
        sorted by travel_time_min ascending
    """
    try:
        with _driver() as driver:
            with driver.session() as session:
                result = session.run(
                    """
                    MATCH (s {station_id: $station_id})-[r:METRO_LINK|RAIL_LINK]-(n)
                    RETURN DISTINCT
                        n.station_id      AS station_id,
                        n.name            AS name,
                        r.line            AS line,
                        r.travel_time_min AS travel_time_min
                    ORDER BY r.travel_time_min
                    """,
                    station_id=station_id,
                )
                return [dict(record) for record in result]
    except Exception:
        return []
