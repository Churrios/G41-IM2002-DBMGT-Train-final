"""
TransitFlow — Intelligent Agent
================================
This is the brain of the system.

HOW IT WORKS (the pipeline students should understand):
  1. User asks a natural language question
  2. The LLM reads the question and decides which databases to query
     (this is called "tool use" or "function calling")
  3. Each database query runs and returns structured data
  4. The LLM reads all the data and writes a helpful answer
  5. The answer is returned to the Gradio UI

THE THREE DATABASE ROLES IN THIS FILE:
  - Relational (PostgreSQL)  → schedules, fares, bookings, seat layouts, users
  - Vector (pgvector / RAG)  → policy documents (refunds, conduct, luggage, etc.)
  - Graph (Neo4j)            → route finding, delay ripple, cross-network paths

STUDENT TASK
------------
You do NOT need to rewrite this file.
Your goal is to make the database queries richer by:
  1. Adding more data to PostgreSQL (new tables, more seed data)
  2. Writing better Cypher in databases/graph/queries.py
  3. Adding more policy documents (databases/vector/documents.py)

The agent will automatically use whatever you put in the databases.

跨檔案互動：
  - 呼叫 databases/relational/queries.py → 關聯式資料與向量資料庫查詢（可用性、票價、預訂等）
  - 呼叫 databases/graph/queries.py → 圖形資料庫查詢（路徑尋找、替代路線、延遲影響等）
  - 呼叫 skeleton/rag.py → search_with_rerank()
  - 呼叫 skeleton/llm_provider.py → LLM 介面
  - 被 skeleton/ui.py 呼叫 → run_agent() 處理對話
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Optional

from skeleton.llm_provider import llm
from databases.relational.queries import (
    query_national_rail_availability,
    query_national_rail_fare,
    query_metro_schedules,
    query_metro_fare,
    query_available_seats,
    auto_select_adjacent_seats,
    query_user_profile,
    query_user_bookings,
    query_payment_info,
    execute_booking,
    execute_cancellation,
    query_policy_vector_search,
    log_delay_event,
    get_active_delays,
)
from databases.graph.queries import (
    query_shortest_route,
    query_cheapest_route,
    query_alternative_routes,
    query_interchange_path,
    query_delay_ripple,
    query_station_connections,
)


# ── Station name → ID lookup (resolved in Python, not by the LLM) ────────────

_STATION_INDEX: dict[str, str] = {
    # Metro
    "central square": "MS01", "riverside":   "MS02", "northgate":  "MS03",
    "elm park":       "MS04", "westfield":   "MS05", "harbour view": "MS06",
    "old town":       "MS07", "university":  "MS08", "queensbridge": "MS09",
    "parkside":       "MS10", "greenhill":   "MS11", "lakeshore":  "MS12",
    "clifton":        "MS13", "eastwick":    "MS14", "ferndale":   "MS15",
    "hilltop":        "MS16", "broadmoor":   "MS17", "sunnyvale":  "MS18",
    "redwood":        "MS19", "thornton":    "MS20",
    # National Rail (longer/specific names first so they match before shorter substrings)
    "central station":   "NR01", "maplewood":     "NR02",
    "old town junction": "NR03", "ashford":        "NR04",
    "stonehaven":        "NR05", "bridgeport":     "NR06",
    "ferndale halt":     "NR07", "coalport":       "NR08",
    "dunmore":           "NR09", "langford end":   "NR10",
}


def _inject_station_ids(text: str) -> str:
    """
    Replace station names in text with 'name (ID)' so the LLM reads the ID
    right next to the name and uses it as the parameter value.
    Longer names are substituted first so 'Old Town Junction' beats 'Old Town'.
    Returns the original text unchanged when no stations are found.
    """
    result = text
    seen_ids: set[str] = set()
    for name in sorted(_STATION_INDEX, key=len, reverse=True):
        sid = _STATION_INDEX[name]
        if sid in seen_ids:
            continue
        pattern = re.compile(re.escape(name), re.IGNORECASE)
        if pattern.search(result):
            result = pattern.sub(f"{name} ({sid})", result)
            seen_ids.add(sid)
    return result


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are TransitFlow, a transit assistant for a dual-network system.

Networks: City Metro MS01-MS20 (lines M1-M4) | National Rail NR01-NR10 (lines NR1-NR2)
Interchanges: Central=MS01/NR01 | Old Town=MS07/NR03 | Ferndale=MS15/NR07
Today: {today}

LOGIN RULE: Routes, fares, schedules, and policies work WITHOUT login for all users. Only make_booking and cancel_booking need login — if the user tries to book or cancel and is not logged in, tell them to log in first.

When DATA FROM TRANSITFLOW DATABASE is provided, use it as the only source of truth. Do not contradict it or say a route was not found if the data shows one.
For route results: list every station name in order, note any line changes, and give the total travel time.
Always reply in the same language as the user.
""".format(today=date.today().isoformat())


# ── Tool definitions (sent to the LLM to decide which to call) ────────────────

TOOLS = [
    {
        "name": "check_national_rail_availability",
        "description": (
            "Check available national rail trains and services between two stations. "
            "Use for any question about what trains run, schedules, timetables, or availability. "
            "Returns schedules, service types, fare classes, and seat occupancy."
        ),
        "parameters": {
            "origin_id":      {"type": "string", "description": "National rail station ID e.g. NR01"},
            "destination_id": {"type": "string", "description": "National rail station ID e.g. NR05"},
            "travel_date":    {"type": "string", "description": "YYYY-MM-DD (optional — omit for general info)"},
        },
        "required": ["origin_id", "destination_id"],
    },
    {
        "name": "get_national_rail_fare",
        "description": "Calculate the fare for a national rail journey on a specific schedule.",
        "parameters": {
            "schedule_id":     {"type": "string", "description": "e.g. NR_SCH01"},
            "fare_class":      {"type": "string", "description": "standard or first"},
            "stops_travelled": {"type": "integer", "description": "Number of stops between origin and destination (from availability result)"},
        },
        "required": ["schedule_id", "fare_class", "stops_travelled"],
    },
    {
        "name": "check_metro_availability",
        "description": "Check available metro services between two metro stations.",
        "parameters": {
            "origin_id":      {"type": "string", "description": "Metro station ID e.g. MS01"},
            "destination_id": {"type": "string", "description": "Metro station ID e.g. MS09"},
        },
        "required": ["origin_id", "destination_id"],
    },
    {
        "name": "calculate_metro_fare",
        "description": "Calculate the metro single-ticket fare for a journey.",
        "parameters": {
            "schedule_id":     {"type": "string", "description": "e.g. MS_SCH01"},
            "stops_travelled": {"type": "integer", "description": "Number of stops between origin and destination"},
        },
        "required": ["schedule_id", "stops_travelled"],
    },
    {
        "name": "get_metro_fare",
        "description": (
            "Get the metro ticket PRICE between two stations. "
            "Use ONLY for fare/price/cost questions ('how much does it cost', 'what is the fare'). "
            "Do NOT use this for route or direction questions — use find_route instead."
        ),
        "parameters": {
            "origin_id":      {"type": "string", "description": "Metro station ID e.g. MS01"},
            "destination_id": {"type": "string", "description": "Metro station ID e.g. MS09"},
        },
        "required": ["origin_id", "destination_id"],
    },
    {
        "name": "get_payment_info",
        "description": (
            "Retrieve payment information for a specific booking ID. "
            "Use this when a user asks about payment status, amount, or method for a booking."
        ),
        "parameters": {
            "booking_id": {"type": "string", "description": "The booking reference ID e.g. BK-A1B2C3"},
        },
        "required": ["booking_id"],
    },
    {
        "name": "get_user_bookings",
        "description": (
            "Retrieve the logged-in user's full booking history (national rail bookings + metro trips). "
            "Use whenever the user asks about their tickets, journeys, or travel history. "
            "Requires login — no parameters needed."
        ),
        "parameters": {},
        "required": [],
    },
    {
        "name": "get_available_seats",
        "description": (
            "Show available seats on a national rail service for a given date and fare class. "
            "Always call this before making a first-class booking, or when the user wants to select a seat."
        ),
        "parameters": {
            "schedule_id":  {"type": "string", "description": "e.g. NR_SCH01"},
            "travel_date":  {"type": "string", "description": "YYYY-MM-DD"},
            "fare_class":   {"type": "string", "description": "standard or first"},
        },
        "required": ["schedule_id", "travel_date", "fare_class"],
    },
    {
        "name": "make_booking",
        "description": (
            "Create a national rail booking for the logged-in user. "
            "REQUIRES LOGIN. Only call after the user has explicitly confirmed all booking details. "
            "Do NOT call this speculatively."
        ),
        "parameters": {
            "schedule_id":            {"type": "string", "description": "e.g. NR_SCH01"},
            "origin_station_id":      {"type": "string", "description": "e.g. NR01"},
            "destination_station_id": {"type": "string", "description": "e.g. NR05"},
            "travel_date":            {"type": "string", "description": "YYYY-MM-DD"},
            "fare_class":             {"type": "string", "description": "standard or first"},
            "seat_id":                {"type": "string", "description": "Specific seat ID (e.g. B05) or 'any' for auto-assign"},
            "ticket_type":            {"type": "string", "description": "single or return (default single)"},
        },
        "required": ["schedule_id", "origin_station_id", "destination_station_id", "travel_date", "fare_class", "seat_id"],
    },
    {
        "name": "cancel_booking",
        "description": (
            "Cancel a national rail booking for the logged-in user. "
            "REQUIRES LOGIN. Only call after the user has explicitly confirmed the cancellation. "
            "The refund amount is calculated automatically per the applicable policy."
        ),
        "parameters": {
            "booking_id": {"type": "string", "description": "Booking reference e.g. BK-A1B2C3"},
        },
        "required": ["booking_id"],
    },
    {
        "name": "search_policy",
        "description": (
            "Search company policy documents. Use for any question about: "
            "refunds, delay compensation, luggage, bicycles, pets, food and drink, "
            "conduct, booking rules, ticket types, fare evasion, or child fares."
        ),
        "parameters": {
            "query": {"type": "string", "description": "Natural language question about policy"},
        },
        "required": ["query"],
    },
    {
        "name": "find_route",
        "description": (
            "Find the best route or path between two stations. Use for ANY question about "
            "directions, how to get from A to B, fastest route, quickest route, or shortest path. "
            "Works for metro-only, rail-only, or cross-network journeys. "
            "Use optimise_by='time' for fastest/quickest, 'cost' for cheapest."
        ),
        "parameters": {
            "origin_id":      {"type": "string", "description": "Station ID e.g. MS01 or NR01"},
            "destination_id": {"type": "string", "description": "Station ID e.g. MS09 or NR05"},
            "network":        {"type": "string", "description": "metro, rail, or auto (default auto — inferred from IDs)"},
            "optimise_by":    {"type": "string", "description": "time (fastest, default) or cost (cheapest)"},
        },
        "required": ["origin_id", "destination_id"],
    },
    {
        "name": "find_alternative_routes",
        "description": "Find routes that avoid a specific delayed or closed station.",
        "parameters": {
            "origin_id":        {"type": "string", "description": "e.g. NR01"},
            "destination_id":   {"type": "string", "description": "e.g. NR05"},
            "avoid_station_id": {"type": "string", "description": "The station to avoid e.g. NR03"},
            "network":          {"type": "string", "description": "metro, rail, or auto"},
        },
        "required": ["origin_id", "destination_id", "avoid_station_id"],
    },
    {
        "name": "get_delay_ripple",
        "description": "Show which stations and lines are affected by a disruption or delay at a given station (within N hops).",
        "parameters": {
            "station_id": {"type": "string", "description": "Station ID e.g. NR03 or MS07"},
            "hops":       {"type": "integer", "description": "How many connections out to check (default 2)"},
        },
        "required": ["station_id"],
    },
    {
        "name": "get_station_connections",
        "description": "List all direct neighbouring stations connected to a given station.",
        "parameters": {
            "station_id": {"type": "string", "description": "Station ID e.g. NR03 or MS07"},
        },
        "required": ["station_id"],
    },
    # ── TASK 6 EXTENSION: Delay Event Logging ────────────────────────────────
    {
        "name": "report_delay",
        "description": (
            "Report a new delay or disruption at a station. "
            "Use when a user says there is a delay, signal failure, fault, or disruption at a station."
        ),
        "parameters": {
            "station_id":  {"type": "string", "description": "Station ID e.g. MS07 or NR03"},
            "severity":    {"type": "string", "description": "One of: low, medium, high"},
            "description": {"type": "string", "description": "Brief description of the disruption"},
        },
        "required": ["station_id", "severity", "description"],
    },
    {
        "name": "get_active_delays",
        "description": (
            "Get all currently active (unresolved) delays and disruptions. "
            "Optionally filter to a specific station. "
            "Use when a user asks 'are there any delays', 'what disruptions are active', or similar."
        ),
        "parameters": {
            "station_id": {"type": "string", "description": "Station ID to filter by (optional)"},
        },
        "required": [],
    },
]

TOOLS_SCHEMA = """\
find_route(origin_id, destination_id, optimise_by?)
check_national_rail_availability(origin_id, destination_id, travel_date?)
get_national_rail_fare(schedule_id, fare_class, stops_travelled)
check_metro_availability(origin_id, destination_id)
calculate_metro_fare(schedule_id, stops_travelled)
get_available_seats(schedule_id, travel_date, fare_class)
make_booking(schedule_id, origin_station_id, destination_station_id, travel_date, fare_class, seat_id, ticket_type?)
cancel_booking(booking_id)
get_payment_info(booking_id)
get_user_bookings()
search_policy(query)
find_alternative_routes(origin_id, destination_id, avoid_station_id, network?)
get_delay_ripple(station_id, hops?)
get_station_connections(station_id)
report_delay(station_id, severity, description)
get_active_delays(station_id?)"""


# ── Agent logic ───────────────────────────────────────────────────────────────

def _execute_tool(
    tool_name: str,
    params: dict,
    current_user_email: Optional[str] = None,
) -> str:
    """
    Execute a tool call and return the result as a JSON string.
    This is where the LLM's decision meets the actual databases.
    """
    try:
        if tool_name == "check_national_rail_availability":
            result = query_national_rail_availability(**params)

        elif tool_name == "get_national_rail_fare":
            result = query_national_rail_fare(**params)

        elif tool_name == "check_metro_availability":
            result = query_metro_schedules(
                origin_id=params["origin_id"],
                destination_id=params["destination_id"],
            )

        elif tool_name == "calculate_metro_fare":
            result = query_metro_fare(**params)

        elif tool_name == "get_metro_fare":
            schedules = query_metro_schedules(
                origin_id=params["origin_id"],
                destination_id=params["destination_id"],
            )
            if not schedules:
                result = {"error": "No metro service found between these stations."}
            else:
                sched = schedules[0]
                stops = sched.get("stops_in_order") or []
                try:
                    n_stops = stops.index(params["destination_id"]) - stops.index(params["origin_id"])
                except ValueError:
                    n_stops = 1
                fare = query_metro_fare(sched["schedule_id"], n_stops)
                result = {
                    "origin":       sched.get("origin_name", params["origin_id"]),
                    "destination":  sched.get("destination_name", params["destination_id"]),
                    "line":         sched.get("line"),
                    "schedule_id":  sched["schedule_id"],
                    "stops":        n_stops,
                    **(fare or {"error": "Fare lookup failed"}),
                }

        elif tool_name == "get_payment_info":
            result = query_payment_info(booking_id=params["booking_id"])

        elif tool_name == "get_user_bookings":
            if not current_user_email:
                return json.dumps({"error": "No user is currently logged in."})
            result = query_user_bookings(current_user_email)

        elif tool_name == "get_available_seats":
            result = query_available_seats(**params)

        elif tool_name == "make_booking":
            if not current_user_email:
                return json.dumps({"error": "You must be logged in to make a booking."})
            profile = query_user_profile(current_user_email)
            if not profile:
                return json.dumps({"error": "User profile not found."})
            ok, data = execute_booking(
                user_id=profile["user_id"],
                schedule_id=params["schedule_id"],
                origin_station_id=params["origin_station_id"],
                destination_station_id=params["destination_station_id"],
                travel_date=params["travel_date"],
                fare_class=params["fare_class"],
                seat_id=params["seat_id"],
                ticket_type=params.get("ticket_type", "single"),
            )
            result = data if ok else {"error": data}

        elif tool_name == "cancel_booking":
            if not current_user_email:
                return json.dumps({"error": "You must be logged in to cancel a booking."})
            profile = query_user_profile(current_user_email)
            if not profile:
                return json.dumps({"error": "User profile not found."})
            ok, data = execute_cancellation(
                booking_id=params["booking_id"],
                user_id=profile["user_id"],
            )
            result = data if ok else {"error": data}

        elif tool_name == "search_policy":
            embedding = llm.embed(params["query"])
            from skeleton.rag import search_with_rerank
            docs = search_with_rerank(embedding, params["query"])
            result = [
                {
                    "title":      d["title"],
                    "category":   d["category"],
                    "content":    d["content"][:800],
                    "similarity": round(d["similarity"], 3),
                }
                for d in docs
            ]

        elif tool_name == "find_route":
            origin_id      = params["origin_id"]
            destination_id = params["destination_id"]
            network        = params.get("network", "auto")
            optimise_by    = params.get("optimise_by", "time")

            # Detect cross-network routing (one MS, one NR)
            is_cross = (
                (origin_id.upper().startswith("MS") and destination_id.upper().startswith("NR")) or
                (origin_id.upper().startswith("NR") and destination_id.upper().startswith("MS"))
            )

            if is_cross:
                result = query_interchange_path(origin_id, destination_id)
            elif optimise_by == "cost":
                result = query_cheapest_route(
                    origin_id=origin_id,
                    destination_id=destination_id,
                    network=network,
                )
            else:
                result = query_shortest_route(
                    origin_id=origin_id,
                    destination_id=destination_id,
                    network=network,
                )

        elif tool_name == "find_alternative_routes":
            routes = query_alternative_routes(
                origin_id=params["origin_id"],
                destination_id=params["destination_id"],
                avoid_station_id=params["avoid_station_id"],
                network=params.get("network", "auto"),
            )
            result = [{"route_number": i + 1, "legs": r} for i, r in enumerate(routes)]

        elif tool_name == "get_delay_ripple":
            result = query_delay_ripple(
                delayed_station_id=params["station_id"],
                hops=params.get("hops", 2),
            )

        elif tool_name == "get_station_connections":
            result = query_station_connections(
                station_id=params["station_id"],
            )

        # ── TASK 6 EXTENSION ─────────────────────────────────────────────────
        elif tool_name == "report_delay":
            event_id = log_delay_event(
                station_id=params["station_id"],
                severity=params["severity"],
                description=params["description"],
            )
            result = {"event_id": event_id, "status": "recorded"}

        elif tool_name == "get_active_delays":
            result = get_active_delays(
                station_id=params.get("station_id"),
            )

        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({"error": str(e)})


def _flatten_to_text(obj, depth: int = 0) -> str:
    """Recursively convert any JSON value to indented key-value text."""
    pad = "  " * depth
    if isinstance(obj, dict):
        if not obj:
            return f"{pad}(empty)"
        lines = []
        for k, v in obj.items():
            if v is None:
                continue
            if isinstance(v, (dict, list)):
                inner = _flatten_to_text(v, depth + 1)
                if inner.strip():
                    lines.append(f"{pad}{k}:\n{inner}")
            else:
                lines.append(f"{pad}{k}: {v}")
        return "\n".join(lines) or f"{pad}(empty)"
    elif isinstance(obj, list):
        if not obj:
            return f"{pad}(no records)"
        parts = []
        for i, item in enumerate(obj, 1):
            if isinstance(item, (dict, list)):
                parts.append(f"{pad}[{i}]")
                parts.append(_flatten_to_text(item, depth + 1))
            else:
                parts.append(f"{pad}- {item}")
        return "\n".join(parts)
    else:
        return f"{pad}{obj}"


def _normalise_result(tool_name: str, result_json: str) -> str:
    """
    Convert raw tool JSON to structured readable text for the answer LLM.
    Pure Python — works for any tool output without per-tool code.
    Students never need to touch this when adding new tools.
    """
    try:
        data = json.loads(result_json)
    except json.JSONDecodeError:
        return result_json
    if isinstance(data, dict) and "error" in data:
        return f"Error: {data['error']}"
    return _flatten_to_text(data)


def _summarise_result(tool_name: str, result_json: str) -> str:
    """Raw result string shown in the debug panel only."""
    return result_json


def _parse_tool_calls(llm_response: str) -> list[dict] | None:
    """
    Parse tool call JSON from the LLM response.

    The LLM is prompted to respond ONLY with a JSON block when it wants
    to call tools. Format:
        {"tool_calls": [{"name": "...", "params": {...}}, ...]}
    """
    import re
    text = llm_response.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    # raw_decode stops after the first complete JSON object, so it handles both
    # preamble text and multiple JSON objects in one response (common on small models).
    decoder = json.JSONDecoder()
    for m in re.finditer(r'\{', text):
        try:
            data, _ = decoder.raw_decode(text, m.start())
            if "tool_calls" in data:
                return data["tool_calls"]
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return None


def run_agent(
    user_message: str,
    history: list[dict],
    debug: bool = False,
    current_user_email: Optional[str] = None,
) -> tuple:
    """
    Main agent loop.

    Args:
        user_message:       The user's latest message
        history:            Conversation history (list of {role, content} dicts)
        debug:              If True, also return internal tool call info
        current_user_email: Email of the logged-in user, or None for guests

    Returns:
        (assistant_reply, updated_history) or (assistant_reply, updated_history, debug_info)
    """
    debug_info = []

    # Build a context-aware system prompt based on login state
    if current_user_email:
        profile = query_user_profile(current_user_email)
        if profile:
            user_display = f"{profile['full_name']} (email: {current_user_email}, user_id: {profile['user_id']})"
        else:
            user_display = current_user_email
        contextual_prompt = SYSTEM_PROMPT + (
            f"\n\nLogged-in user: {user_display}. "
            "Answer personal booking queries for this user without asking for their email or ID. "
            "Use get_user_bookings() for any booking history request. "
            "Use make_booking / cancel_booking for booking and cancellation requests."
        )
    else:
        contextual_prompt = SYSTEM_PROMPT + (
            "\n\nNo user is currently logged in. "
            "If the user asks about personal bookings, history, or wants to make/cancel a booking, "
            "tell them they must log in first."
        )

    # Step 1: Ask the LLM which tools to call
    # Include recent history so the LLM can extract params from multi-turn flows.
    recent_history = history[-4:] if len(history) > 4 else history

    # Substitute station names with 'name (ID)' inline so the LLM reads the ID
    # directly next to each name and uses it as the parameter value.
    _augmented_message = _inject_station_ids(user_message)

    tool_selection_prompt = f"""Output only this JSON (no other text):
{{"tool_calls": [{{"name": "TOOL", "params": {{"KEY": "VALUE"}}}}]}}
Or if no tool needed: {{"tool_calls": []}}

STATIONS: Metro=MS01-MS20, Rail=NR01-NR10
USER: {current_user_email or "not logged in"}
get_user_bookings: call (no params) when logged-in user asks about their bookings, tickets, or travel history.
make_booking/cancel_booking: only if user is logged in.
Route/path/journey questions: use find_route. Policy questions: use search_policy.
Never use "" as a param value. Omit optional params if unknown.

TOOLS:
{TOOLS_SCHEMA}

HISTORY:
{json.dumps(recent_history, indent=None)}

USER: "{_augmented_message}"

Examples:
"fastest route MS01 to MS14" -> {{"tool_calls": [{{"name": "find_route", "params": {{"origin_id": "MS01", "destination_id": "MS14", "optimise_by": "time"}}}}]}}
"cheapest NR01 to NR05" -> {{"tool_calls": [{{"name": "find_route", "params": {{"origin_id": "NR01", "destination_id": "NR05", "optimise_by": "cost"}}}}]}}
"trains NR01 to NR03 on 2025-06-01" -> {{"tool_calls": [{{"name": "check_national_rail_availability", "params": {{"origin_id": "NR01", "destination_id": "NR03", "travel_date": "2025-06-01"}}}}]}}
"refund policy" -> {{"tool_calls": [{{"name": "search_policy", "params": {{"query": "refund policy"}}}}]}}
"hello" -> {{"tool_calls": []}}
"show my bookings" -> {{"tool_calls": [{{"name": "get_user_bookings", "params": {{}}}}]}}
"book me a seat NR01 to NR05 on 2025-06-01" -> {{"tool_calls": [{{"name": "check_national_rail_availability", "params": {{"origin_id": "NR01", "destination_id": "NR05", "travel_date": "2025-06-01"}}}}]}}

JSON:"""

    if llm.get_chat_provider() == "ollama":
        # llama3.2:1b is fine-tuned for native tool calling — far more reliable than
        # prompt-based JSON routing which produces malformed output on 1B models.
        tool_calls = llm.ollama_tool_call(
            recent_history, TOOLS, _augmented_message,
            system_prompt=(
                "You are a tool router. Call the right tool based on the user message. "
                f"Logged-in user: {current_user_email or 'none'}. "
                "My bookings/tickets/travel history → get_user_bookings (no params). "
                "Book a ticket / make a booking → check_national_rail_availability first, then make_booking. "
                "Cancel a booking → cancel_booking. "
                "Policy/rules/conduct/compensation/luggage/bicycle questions → search_policy. "
                "Route/directions/fastest/quickest/how-to-get/path questions → find_route ONLY (never get_metro_fare). "
                "Metro fare/price/cost/how-much-does-it-cost questions → get_metro_fare. "
                "Rail fare/cost/price questions → check_national_rail_availability then get_national_rail_fare. "
                "Schedule/timetable/trains/services questions → check_national_rail_availability or check_metro_availability. "
                "Only call a tool when needed. Output nothing except tool calls."
            ),
        )
        if debug:
            debug_info.append(f"**Tool selection (native):** {tool_calls}")
    else:
        selection_response = llm.chat(
            messages=[{"role": "user", "content": tool_selection_prompt}],
            system_prompt="JSON only. You are a router. Output valid JSON. No empty string param values.",
        )
        tool_calls = _parse_tool_calls(selection_response) or []
        if debug:
            debug_info.append(f"**Tool selection:** {selection_response}")

    # ── Deterministic fallbacks ────────────────────────────────────────────────
    # llama3.2:1b is unreliable for tool routing on anything beyond trivial queries.
    # Rules below cover every common query type.  Each rule only fires when the
    # correct tool is not already selected with valid required params.
    _lower = _augmented_message.lower()
    _station_ids = re.findall(r'\b(MS\d{2}|NR\d{2})\b', _augmented_message, re.IGNORECASE)
    _two_stations = len(_station_ids) >= 2

    def _tool_selected(name: str, *required_params) -> bool:
        """Return True only if tool `name` is in tool_calls with all required params set."""
        call = next((c for c in tool_calls if c.get("name") == name), None)
        if not call:
            return False
        p = call.get("params") or {}
        return all(p.get(k) for k in required_params)

    def _fallback(name: str, params: dict, reason: str):
        nonlocal tool_calls
        tool_calls = [{"name": name, "params": params}]
        if debug:
            debug_info.append(f"**Fallback:** {reason} → {name}({params})")

    # 1. Route / directions / path — also overrides wrong-tool selections
    _route_triggers = {"fastest route", "quickest route", "shortest route", "cheapest route",
                       "best route", "how to get", "directions from", "route from", "route to",
                       "get from", "travel from", "way from", "path from"}
    _is_route = (
        any(kw in _lower for kw in _route_triggers) or
        (_two_stations and "route" in _lower)
    )
    if _is_route and _two_stations \
            and not _tool_selected("find_route", "origin_id", "destination_id") \
            and not _tool_selected("find_alternative_routes", "origin_id", "destination_id"):
        _opt = "cost" if any(kw in _lower for kw in ["cheap", "cheapest", "lowest cost"]) else "time"
        _fallback("find_route",
                  {"origin_id": _station_ids[0].upper(), "destination_id": _station_ids[1].upper(), "optimise_by": _opt},
                  "route query")

    # 2. Availability / trains / schedules between two stations
    elif not tool_calls and _two_stations:
        _avail_triggers = {"train", "trains", "service", "services", "run from", "runs from",
                           "schedule", "timetable", "available", "availability"}
        if any(kw in _lower for kw in _avail_triggers):
            o, d = _station_ids[0].upper(), _station_ids[1].upper()
            _travel_date = next(
                (w for w in _lower.split() if re.match(r'\d{4}-\d{2}-\d{2}', w)), None
            )
            _params = {"origin_id": o, "destination_id": d}
            if _travel_date:
                _params["travel_date"] = _travel_date
            _tool = "check_national_rail_availability" if o.startswith("NR") else "check_metro_availability"
            _fallback(_tool, _params, "availability query")

    # 3. Personal booking history — requires login
    if current_user_email and not tool_calls:
        _personal_triggers = {"my booking", "my ticket", "my trip", "my journey", "my history",
                               "my reservation", "show booking", "view booking", "check booking",
                               "list booking", "show my", "view my"}
        if any(kw in _lower for kw in _personal_triggers):
            _fallback("get_user_bookings", {}, "personal booking query")

    # Step 2: Execute each tool call against the real databases
    tool_results = []
    for call in tool_calls:
        tool_name = call.get("name", "")
        params    = call.get("params") or call.get("parameters", {})

        # Skip calls with empty string values — LLM failed to extract params
        if any(v == "" for v in params.values()):
            if debug:
                debug_info.append(f"**Skipped** `{tool_name}` — empty params: {params}")
            continue

        if debug:
            debug_info.append(f"**Calling:** `{tool_name}({params})`")

        result_json = _execute_tool(tool_name, params, current_user_email)

        summary = _summarise_result(tool_name, result_json)

        if debug:
            debug_info.append(
                f"**Result (raw):** ```json\n{result_json[:300]}\n```\n"
                f"**Summary sent to LLM:** {summary}"
            )

        tool_results.append({
            "tool":    tool_name,
            "params":  params,
            "result":  result_json,
            "summary": summary,
        })

    # Step 3: Normalise raw tool results to plain English using the LLM, then
    # compose the final answer.  The normalisation call replaces hand-crafted
    # per-tool formatters: any tool a student adds works automatically.
    _DB_KEYWORDS = {"booking", "ticket", "schedule", "fare", "route", "seat",
                    "train", "metro", "journey", "trip", "history", "reservation"}
    if tool_results:
        data_block = "\n\n".join(
            f"[{tr['tool']}]\n{_normalise_result(tr['tool'], tr['result'])}"
            for tr in tool_results
        )
        if debug:
            debug_info.append(f"**Data (normalised):**\n{data_block}")
        content = (
            f"DATA FROM TRANSITFLOW DATABASE:\n{data_block}"
            f"\n\nUser asks: {user_message}"
            f"\n\nAnswer using only the data above:"
        )
    elif any(kw in user_message.lower() for kw in _DB_KEYWORDS):
        # No tool was called but the question needs DB data — prevent hallucination.
        content = (
            f"User asks: {user_message}\n\n"
            "IMPORTANT: No data was retrieved from the TransitFlow database for this query. "
            "Do NOT invent any bookings, fares, schedules, seat numbers, or travel times. "
            "Tell the user no data was found."
        )
    else:
        content = user_message

    final_messages = history + [{"role": "user", "content": content}]

    answer = llm.chat(messages=final_messages, system_prompt=contextual_prompt)

    # Update history
    updated_history = history + [
        {"role": "user",      "content": user_message},
        {"role": "assistant", "content": answer},
    ]

    if debug:
        return answer, updated_history, "\n\n".join(debug_info)
    return answer, updated_history
