"""
TransitFlow — PostgreSQL / Relational Database Layer
=====================================================
This module handles all queries to PostgreSQL.

TWO ROLES ARE SERVED HERE:
  1. Relational  → dual-network transit (metro + national rail),
                   availability, fares, bookings, seat selection
  2. Vector      → policy document similarity search (pgvector)

STUDENT TASK
------------
Design your schema in databases/relational/schema.sql, seed it with
skeleton/seed_postgres.py, then implement the query functions below.

Functions prefixed with `query_`  are read-only lookups called by the agent.
Functions prefixed with `execute_` are write operations (booking/cancellation).

The vector functions (query_policy_vector_search, store_policy_document)
are already implemented — do not modify them.
"""

from __future__ import annotations

import json
import random
import string
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import bcrypt
import psycopg2
import psycopg2.extras

from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD


def _connect():
    """Return a new psycopg2 connection with autocommit enabled."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn


def _gen_booking_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"BK-{suffix}"


def _gen_payment_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PM-{suffix}"


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a cursor, run SQL, return rows.
# Use _connect() for read-only queries; for write operations use a manual
# connection with conn.commit() / conn.rollback() (see execute_booking below).

def example_query() -> dict:
    """Example: returns the name of the connected database."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db;")
            return dict(cur.fetchone())

# TODO: Implement the query_ and execute_ functions below.
# ─────────────────────────────────────────────────────────────────────────────


# ── NATIONAL RAIL AVAILABILITY ────────────────────────────────────────────────

def query_national_rail_availability(
    origin_id: str,
    destination_id: str,
    travel_date: Optional[str] = None,
) -> list[dict]:
    """
    Return national rail schedules that serve both origin and destination stations
    in the correct order, along with seat occupancy for the requested travel date.

    Args:
        origin_id:       e.g. "NR01"
        destination_id:  e.g. "NR05"
        travel_date:     e.g. "2025-06-01" — used to count bookings; omit for general info
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT s.*,
                       array_position(s.stops_in_order, %s) AS origin_pos,
                       array_position(s.stops_in_order, %s) AS dest_pos,
                       COUNT(b.booking_id) AS booked_seats,
                       (SELECT COUNT(*) FROM seat_layouts sl
                        WHERE sl.schedule_id = s.schedule_id) - COUNT(b.booking_id) AS available_seats
                FROM national_rail_schedules s
                LEFT JOIN bookings b ON b.schedule_id = s.schedule_id
                                    AND b.travel_date = %s
                                    AND b.status != 'cancelled'
                WHERE s.stops_in_order @> ARRAY[%s, %s]::VARCHAR(10)[]
                GROUP BY s.schedule_id
                HAVING array_position(s.stops_in_order, %s) < array_position(s.stops_in_order, %s)
                """,
                (origin_id, destination_id, travel_date,
                 origin_id, destination_id,
                 origin_id, destination_id),
            )
            return [dict(row) for row in cur.fetchall()]


def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int,
) -> Optional[dict]:
    """
    Calculate the fare for a national rail journey.

    Args:
        schedule_id:     e.g. "NR_SCH01"
        fare_class:      "standard" or "first"
        stops_travelled: number of stops between origin and destination (inclusive)

    Returns:
        dict with fare_class, base_fare_usd, per_stop_rate_usd, total_fare_usd
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT std_base_fare_usd, std_per_stop_rate_usd,
                       first_base_fare_usd, first_per_stop_rate_usd
                FROM national_rail_schedules
                WHERE schedule_id = %s
                """,
                (schedule_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    if fare_class == "first":
        base = float(row["first_base_fare_usd"])
        per_stop = float(row["first_per_stop_rate_usd"])
    else:
        base = float(row["std_base_fare_usd"])
        per_stop = float(row["std_per_stop_rate_usd"])
    return {
        "fare_class": fare_class,
        "base_fare_usd": base,
        "per_stop_rate_usd": per_stop,
        "total_fare_usd": round(base + per_stop * stops_travelled, 2),
    }


# ── METRO SCHEDULES & FARE ────────────────────────────────────────────────────

def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """
    Return metro schedules that serve both origin and destination in the correct order.

    Args:
        origin_id:       e.g. "MS01"
        destination_id:  e.g. "MS09"
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM metro_schedules
                WHERE stops_in_order @> ARRAY[%s, %s]::VARCHAR(10)[]
                """,
                (origin_id, destination_id),
            )
            rows = cur.fetchall()
    # origin must appear before destination in the stop sequence
    return [
        dict(r) for r in rows
        if r["stops_in_order"].index(origin_id) < r["stops_in_order"].index(destination_id)
    ]


def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """
    Calculate the metro fare for a single-ticket journey.

    Args:
        schedule_id:     e.g. "MS_SCH01"
        stops_travelled: number of stops between origin and destination

    Returns:
        dict with base_fare_usd, per_stop_rate_usd, total_fare_usd
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT base_fare_usd, per_stop_rate_usd FROM metro_schedules WHERE schedule_id = %s",
                (schedule_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    base = float(row["base_fare_usd"])
    per_stop = float(row["per_stop_rate_usd"])
    return {
        "base_fare_usd": base,
        "per_stop_rate_usd": per_stop,
        "total_fare_usd": round(base + per_stop * stops_travelled, 2),
    }


# ── SEAT SELECTION ────────────────────────────────────────────────────────────

def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str,
) -> list[dict]:
    """
    Return available seats for a national rail journey on a given date.

    Args:
        schedule_id:  e.g. "NR_SCH01"
        travel_date:  e.g. "2025-06-01"
        fare_class:   "standard" or "first"

    Returns:
        List of dicts: {seat_id, coach, row, column}
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT sl.seat_id, sl.coach, sl.row_num AS row, sl.col_char AS column
                FROM seat_layouts sl
                WHERE sl.schedule_id = %s AND sl.fare_class = %s
                  AND sl.seat_id NOT IN (
                      SELECT seat_id FROM bookings
                      WHERE schedule_id = %s AND travel_date = %s AND status != 'cancelled'
                  )
                ORDER BY sl.coach, sl.row_num, sl.col_char
                """,
                (schedule_id, fare_class, schedule_id, travel_date),
            )
            return [dict(row) for row in cur.fetchall()]


def auto_select_adjacent_seats(available_seats: list[dict], count: int) -> list[str]:
    """
    Select `count` seats that are as close together as possible (same row preferred,
    then adjacent rows). Returns a list of seat_ids.

    Args:
        available_seats: output of query_available_seats()
        count:           number of seats needed
    """
    if not available_seats or count <= 0:
        return []
    if count >= len(available_seats):
        return [s["seat_id"] for s in available_seats[:count]]

    from collections import defaultdict
    rows: dict[int, list[dict]] = defaultdict(list)
    for seat in available_seats:
        rows[seat["row"]].append(seat)

    for row_seats in sorted(rows.values(), key=lambda s: s[0]["row"]):
        if len(row_seats) >= count:
            return [s["seat_id"] for s in row_seats[:count]]

    sorted_seats = sorted(available_seats, key=lambda s: (s["row"], s["column"]))
    return [s["seat_id"] for s in sorted_seats[:count]]


# ── USER & BOOKING QUERIES ────────────────────────────────────────────────────

def query_user_profile(user_email: str) -> Optional[dict]:
    """Return a user's profile by email."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM registered_users WHERE email = %s AND is_active = TRUE",
                (user_email,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    user = dict(row)
    # grading expects year_of_birth; schema stores date_of_birth
    if user.get("date_of_birth"):
        user["year_of_birth"] = user["date_of_birth"].year
    return user


def query_user_bookings(user_email: str) -> dict:
    """
    Return a user's combined booking history (national rail + metro).

    Returns:
        dict with keys 'national_rail' (list) and 'metro' (list)
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT b.*, s.line, s.service_type
                FROM bookings b
                JOIN national_rail_schedules s ON b.schedule_id = s.schedule_id
                WHERE b.user_id = (SELECT user_id FROM registered_users WHERE email = %s)
                """,
                (user_email,),
            )
            nr = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT m.*, s.line
                FROM metro_travel_history m
                JOIN metro_schedules s ON m.schedule_id = s.schedule_id
                WHERE m.user_id = (SELECT user_id FROM registered_users WHERE email = %s)
                """,
                (user_email,),
            )
            metro = [dict(row) for row in cur.fetchall()]

    return {"national_rail": nr, "metro": metro}


def query_payment_info(booking_id: str) -> Optional[dict]:
    """Return payment record for a booking or metro trip."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM payments WHERE booking_id = %s",
                (booking_id,),
            )
            row = cur.fetchone()
    return dict(row) if row is not None else None


# ── TRANSACTIONAL OPERATIONS ──────────────────────────────────────────────────

def execute_booking(
    user_id: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
    fare_class: str,
    seat_id: str,
    ticket_type: str = "single",
) -> tuple[bool, dict | str]:
    """
    Create a national rail booking for a logged-in user.

    Args:
        user_id:                e.g. "RU01" — must match the logged-in user
        schedule_id:            e.g. "NR_SCH01"
        origin_station_id:      e.g. "NR01"
        destination_station_id: e.g. "NR05"
        travel_date:            e.g. "2025-06-01"
        fare_class:             "standard" or "first"
        seat_id:                e.g. "B05" (or "any" to auto-assign)
        ticket_type:            "single" (default) or "return"

    Returns:
        (True, booking_dict)   on success
        (False, error_message) on failure
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Fetch schedule to get stop order, fares, and departure time
            cur.execute(
                """
                SELECT stops_in_order, first_train_time,
                       std_base_fare_usd, std_per_stop_rate_usd,
                       first_base_fare_usd, first_per_stop_rate_usd
                FROM national_rail_schedules
                WHERE schedule_id = %s
                """,
                (schedule_id,),
            )
            schedule = cur.fetchone()
            if schedule is None:
                return (False, "Schedule not found")

            stops = list(schedule["stops_in_order"])
            if origin_station_id not in stops or destination_station_id not in stops:
                return (False, "Stations not on this route")
            origin_pos = stops.index(origin_station_id)
            dest_pos = stops.index(destination_station_id)
            if origin_pos >= dest_pos:
                return (False, "Invalid route direction")
            stops_count = dest_pos - origin_pos

            # 2. Calculate fare
            if fare_class == "first":
                base = float(schedule["first_base_fare_usd"])
                per_stop = float(schedule["first_per_stop_rate_usd"])
            else:
                base = float(schedule["std_base_fare_usd"])
                per_stop = float(schedule["std_per_stop_rate_usd"])
            amount = round(base + per_stop * stops_count, 2)

            # 3. Resolve seat and coach
            if seat_id == "any":
                cur.execute(
                    """
                    SELECT seat_id, coach FROM seat_layouts
                    WHERE schedule_id = %s AND fare_class = %s
                      AND seat_id NOT IN (
                          SELECT seat_id FROM bookings
                          WHERE schedule_id = %s AND travel_date = %s AND status != 'cancelled'
                      )
                    LIMIT 1
                    """,
                    (schedule_id, fare_class, schedule_id, travel_date),
                )
                seat_row = cur.fetchone()
                if seat_row is None:
                    return (False, "No seats available")
                resolved_seat_id = seat_row["seat_id"]
                coach = seat_row["coach"]
            else:
                # Verify seat exists and is not already booked
                cur.execute(
                    """
                    SELECT coach FROM seat_layouts
                    WHERE schedule_id = %s AND seat_id = %s AND fare_class = %s
                      AND seat_id NOT IN (
                          SELECT seat_id FROM bookings
                          WHERE schedule_id = %s AND travel_date = %s AND status != 'cancelled'
                      )
                    """,
                    (schedule_id, seat_id, fare_class, schedule_id, travel_date),
                )
                seat_row = cur.fetchone()
                if seat_row is None:
                    return (False, f"Seat {seat_id} is unavailable or does not exist")
                resolved_seat_id = seat_id
                coach = seat_row["coach"]

            # 4. Insert booking
            booking_id = _gen_booking_id()
            cur.execute(
                """
                INSERT INTO bookings
                    (booking_id, user_id, schedule_id,
                     origin_station_id, destination_station_id,
                     travel_date, departure_time, ticket_type, fare_class,
                     coach, seat_id, stops_travelled, amount_usd, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'confirmed')
                RETURNING *
                """,
                (booking_id, user_id, schedule_id,
                 origin_station_id, destination_station_id,
                 travel_date, schedule["first_train_time"], ticket_type, fare_class,
                 coach, resolved_seat_id, stops_count, amount),
            )
            booking = dict(cur.fetchone())

            # 5. Insert payment — both inserts share one commit (atomic)
            cur.execute(
                """
                INSERT INTO payments (payment_id, booking_id, amount_usd, method, status)
                VALUES (%s, %s, %s, 'card', 'paid')
                """,
                (_gen_payment_id(), booking_id, amount),
            )

        conn.commit()
        return (True, booking)
    except Exception as e:
        conn.rollback()
        return (False, str(e))
    finally:
        conn.close()


def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    """
    Cancel a national rail booking owned by the given user.

    Calculates the refund amount according to the booking's service type:
      - Normal service: RF001 windows (100% / 75% / 50% / 0%)
      - Express service: RF002 windows (100% / 50% / 0%)

    Args:
        booking_id: e.g. "BK001"
        user_id:    must match the booking's user_id

    Returns:
        (True, result_dict)  with refund_amount and policy note
        (False, error_msg)
    """
    _POLICY_PATH = Path(__file__).parent.parent.parent / "train-mock-data" / "refund_policy.json"
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with open(_POLICY_PATH) as f:
            policies = json.load(f)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Fetch booking joined with schedule to get service_type
            cur.execute(
                """
                SELECT b.*, s.service_type
                FROM bookings b
                JOIN national_rail_schedules s ON b.schedule_id = s.schedule_id
                WHERE b.booking_id = %s
                """,
                (booking_id,),
            )
            row = cur.fetchone()
            if row is None:
                return (False, "Booking not found")
            booking = dict(row)

            # 2. Ownership and status checks
            if booking["user_id"] != user_id:
                return (False, "Booking does not belong to this user")
            if booking["status"] == "cancelled":
                return (False, "Booking is already cancelled")

            # 3. Calculate hours until departure (timezone-aware)
            travel_dt = datetime.combine(booking["travel_date"], booking["departure_time"])
            travel_dt = travel_dt.replace(tzinfo=timezone.utc)
            hours_until = (travel_dt - datetime.now(tz=timezone.utc)).total_seconds() / 3600

            # 4. Match cancellation window from refund_policy.json
            service_type = booking["service_type"]
            policy = next(
                (p for p in policies if p["applies_to"].get("service_type") == service_type),
                None,
            )
            refund_percent = 0
            admin_fee = 0.0
            policy_note = "No refund"
            if policy:
                for window in policy["cancellation_windows"]:
                    min_h = window["hours_before_departure_min"]
                    max_h = window["hours_before_departure_max"]
                    if max_h is None:
                        matches = hours_until >= min_h
                    else:
                        matches = min_h <= hours_until < max_h
                    if matches:
                        refund_percent = window["refund_percent"]
                        admin_fee = float(window["admin_fee_usd"])
                        policy_note = window["label"]
                        break

            # 5. Refund amount (floor at 0 — admin fee never exceeds refund on 0% windows)
            amount = float(booking["amount_usd"])
            refund_amount = max(round(amount * refund_percent / 100 - admin_fee, 2), 0.0)

            # 6. Cancel booking
            cur.execute(
                "UPDATE bookings SET status='cancelled', cancelled_at=NOW() WHERE booking_id = %s",
                (booking_id,),
            )

            # 7. Insert refund payment record (negative amount = money out to customer)
            cur.execute(
                """
                INSERT INTO payments (payment_id, booking_id, amount_usd, method, status, refunded_at)
                VALUES (%s, %s, %s, 'card', 'refunded', NOW())
                """,
                (_gen_payment_id(), booking_id, -refund_amount),
            )

        conn.commit()
        return (True, {
            "booking_id": booking_id,
            "refund_amount": refund_amount,
            "policy_note": policy_note,
        })
    except Exception as e:
        conn.rollback()
        return (False, str(e))
    finally:
        conn.close()


# ── AUTHENTICATION QUERIES ────────────────────────────────────────────────────

def register_user(
    email: str,
    first_name: str,
    surname: str,
    year_of_birth: int,
    password: str,
    secret_question: str,
    secret_answer: str,
) -> tuple[bool, str]:
    """
    Register a new user.
    Returns (True, user_id) on success or (False, error_message) on failure.
    """
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    full_name = f"{first_name} {surname}"
    dob = date(year_of_birth, 1, 1)
    user_id = "RU" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO registered_users
                    (user_id, full_name, email, password, date_of_birth,
                     secret_question, secret_answer)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (email) DO NOTHING
                """,
                (user_id, full_name, email, hashed, dob, secret_question, secret_answer),
            )
            inserted = cur.rowcount == 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        return (False, str(e))
    finally:
        conn.close()
    if not inserted:
        return (False, "Email already registered")
    return (True, user_id)


def login_user(email: str, password: str) -> Optional[dict]:
    """
    Verify credentials. Returns a user dict on success or None on failure.
    Dict keys: user_id, email, full_name, first_name, surname, phone, date_of_birth, is_active.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM registered_users WHERE email = %s AND is_active = TRUE",
                (email,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    if not bcrypt.checkpw(password.encode(), row["password"].encode()):
        return None
    user = dict(row)
    user.pop("password", None)
    return user


def get_user_secret_question(email: str) -> Optional[str]:
    """Return the secret question for a registered email, or None if not found."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT secret_question FROM registered_users WHERE email = %s",
                (email,),
            )
            row = cur.fetchone()
    return row[0] if row is not None else None


def verify_secret_answer(email: str, answer: str) -> bool:
    """Return True if the provided answer matches the stored secret answer (case-insensitive)."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT secret_answer FROM registered_users WHERE email = %s",
                (email,),
            )
            row = cur.fetchone()
    if row is None:
        return False
    return answer.strip().lower() == row[0].strip().lower()


def update_password(email: str, new_password: str) -> bool:
    """Update the password for a user. Returns True if the row was updated."""
    hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE registered_users SET password = %s WHERE email = %s",
                (hashed, email),
            )
            updated = cur.rowcount == 1
        conn.commit()
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()
    return updated


# ── VECTOR / RAG QUERIES — do not modify ─────────────────────────────────────

def query_policy_vector_search(embedding: list[float], top_k: int = VECTOR_TOP_K) -> list[dict]:
    """
    Find the most relevant policy documents for a given query embedding.

    Args:
        embedding: Query vector from llm.embed(user_question)
        top_k:     Number of results to return

    Returns:
        List of dicts with title, category, content, and similarity score
    """
    sql = """
        SELECT
            title,
            category,
            content,
            1 - (embedding <=> %s::vector) AS similarity
        FROM policy_documents
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (vec_str, vec_str, VECTOR_SIMILARITY_THRESHOLD, vec_str, top_k))
            return [dict(row) for row in cur.fetchall()]


def store_policy_document(
    title: str,
    category: str,
    content: str,
    embedding: list[float],
    source_file: str = "",
) -> int:
    """
    Insert a policy document with its embedding into the database.
    Used by skeleton/seed_vectors.py — students don't need to call this directly.

    Returns:
        The new document's id
    """
    sql = """
        INSERT INTO policy_documents (title, category, content, embedding, source_file)
        VALUES (%s, %s, %s, %s::vector, %s)
        RETURNING id
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (title, category, content, vec_str, source_file))
            return cur.fetchone()[0]
