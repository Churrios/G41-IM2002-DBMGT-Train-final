// TransitFlow — Neo4j Schema Mirror
// =============================================================================
// IMPORTANT: The authoritative seeding source is skeleton/seed_neo4j.py.
// This file is a human-readable schema mirror for static review and manual
// verification in Neo4j Browser. It contains representative MERGE examples
// (not the full 30-node dataset) so reviewers can see every node label,
// relationship type, and property without running Python.
// =============================================================================

// ── Unique Constraints ────────────────────────────────────────────────────────
CREATE CONSTRAINT IF NOT EXISTS FOR (s:MetroStation)        REQUIRE s.station_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (s:NationalRailStation) REQUIRE s.station_id IS UNIQUE;

// ── MetroStation nodes ────────────────────────────────────────────────────────
// Properties: station_id (PK), name, lines (array), is_interchange_national_rail (bool)
MERGE (ms01:MetroStation {station_id: "MS01"})
SET ms01.name = "Central Square",
    ms01.lines = ["M1", "M2"],
    ms01.is_interchange_national_rail = true;

MERGE (ms07:MetroStation {station_id: "MS07"})
SET ms07.name = "Old Town",
    ms07.lines = ["M2"],
    ms07.is_interchange_national_rail = true;

MERGE (ms15:MetroStation {station_id: "MS15"})
SET ms15.name = "Ferndale",
    ms15.lines = ["M4"],
    ms15.is_interchange_national_rail = true;

// ── NationalRailStation nodes ─────────────────────────────────────────────────
// Properties: station_id (PK), name, lines (array),
//             is_interchange_metro (bool), interchange_metro_station_id (str or null)
MERGE (nr01:NationalRailStation {station_id: "NR01"})
SET nr01.name = "Central Station",
    nr01.lines = ["NR1", "NR2"],
    nr01.is_interchange_metro = true,
    nr01.interchange_metro_station_id = "MS01";

MERGE (nr03:NationalRailStation {station_id: "NR03"})
SET nr03.name = "Old Town Junction",
    nr03.lines = ["NR1"],
    nr03.is_interchange_metro = true,
    nr03.interchange_metro_station_id = "MS07";

MERGE (nr07:NationalRailStation {station_id: "NR07"})
SET nr07.name = "Ferndale Halt",
    nr07.lines = ["NR2"],
    nr07.is_interchange_metro = true,
    nr07.interchange_metro_station_id = "MS15";

// ── METRO_LINK relationships ──────────────────────────────────────────────────
// Properties: line, travel_time_min, fare_usd
// fare formula: round(1.0 + 0.5 * travel_time_min, 2)
MATCH (a:MetroStation {station_id: "MS01"}), (b:MetroStation {station_id: "MS07"})
MERGE (a)-[r:METRO_LINK {line: "M2"}]->(b)
SET r.travel_time_min = 2,
    r.fare_usd        = 2.0;

// ── RAIL_LINK relationships ───────────────────────────────────────────────────
// Properties: line, travel_time_min, fare_standard_usd, fare_first_usd
// standard formula: round(2.0 + 1.2 * travel_time_min, 2)
// first    formula: round(2.0 + 2.0 * travel_time_min, 2)
MATCH (a:NationalRailStation {station_id: "NR01"}), (b:NationalRailStation {station_id: "NR03"})
MERGE (a)-[r:RAIL_LINK {line: "NR1"}]->(b)
SET r.travel_time_min   = 30,
    r.fare_standard_usd = 38.0,
    r.fare_first_usd    = 62.0;

// ── INTERCHANGE_TO relationships ──────────────────────────────────────────────
// Two directed edges per pair (MetroStation <-> NationalRailStation) so that
// Dijkstra can traverse in either direction without needing undirected queries.
// Properties: transfer_time_min (fixed 5 min — no travel_time_min on this type)
MATCH (m:MetroStation {station_id: "MS01"}), (nr:NationalRailStation {station_id: "NR01"})
MERGE (m)-[r1:INTERCHANGE_TO]->(nr)  SET r1.transfer_time_min = 5
MERGE (nr)-[r2:INTERCHANGE_TO]->(m)  SET r2.transfer_time_min = 5;
