# TASK 6 EXTENSION: log_delay_event(), get_active_delays(), resolve_delay() (see line 800+)
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

跨檔案互動：
  - 被 skeleton/agent.py 呼叫 → 執行各類關聯式查詢與寫入操作（預訂、票價計算等）
  - 被 skeleton/seed_postgres.py 呼叫 → 初始化與寫入基礎資料
  - 被 skeleton/rag.py 呼叫 → query_policy_vector_search() 執行向量相似度搜尋
  - 依賴 skeleton/config.py → 讀取 PG_DSN 連線設定
"""

from __future__ import annotations

import json
import secrets
import string
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import bcrypt
import psycopg2
import psycopg2.extras

from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD

# Module-level constant: avoids recomputing the path on every execute_cancellation call
_POLICY_PATH = Path(__file__).parent.parent.parent / "train-mock-data" / "refund_policy.json"


def _connect():
    """Return a new psycopg2 connection with autocommit enabled."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn


_ID_ALPHABET = string.ascii_uppercase + string.digits


def _gen_booking_id() -> str:
    return "BK-" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(6))


def _gen_payment_id() -> str:
    return "PM-" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(6))


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
                       o_stop.stop_order AS origin_pos,
                       d_stop.stop_order AS dest_pos,
                       COUNT(b.booking_id) AS booked_seats,
                       -- available_seats derived dynamically (seat_layouts total minus confirmed bookings)
                       -- rather than maintaining a separate occupancy table, to avoid sync issues
                       (SELECT COUNT(*) FROM seat_layouts sl
                        WHERE sl.schedule_id = s.schedule_id) - COUNT(b.booking_id) AS available_seats
                FROM national_rail_schedules s
                JOIN national_rail_schedule_stops o_stop
                     ON o_stop.schedule_id = s.schedule_id AND o_stop.station_id = %s
                JOIN national_rail_schedule_stops d_stop
                     ON d_stop.schedule_id = s.schedule_id AND d_stop.station_id = %s
                -- travel_date = NULL makes the join condition always FALSE (SQL 3-value logic),
                -- so booked_seats = 0 and available_seats = total capacity when date is omitted.
                LEFT JOIN bookings b ON b.schedule_id = s.schedule_id
                                    AND (%s IS NULL OR b.travel_date = %s)
                                    AND b.status != 'cancelled'
                GROUP BY s.schedule_id, o_stop.stop_order, d_stop.stop_order
                HAVING o_stop.stop_order < d_stop.stop_order
                """,
                (origin_id, destination_id, travel_date, travel_date),
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
        "total_fare_usd": round(base + per_stop * int(stops_travelled), 2),
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
                SELECT s.*,
                       ARRAY(
                           SELECT station_id FROM metro_schedule_stops
                           WHERE schedule_id = s.schedule_id
                           ORDER BY stop_order
                       ) AS stops_in_order
                FROM metro_schedules s
                JOIN metro_schedule_stops o_stop
                     ON o_stop.schedule_id = s.schedule_id AND o_stop.station_id = %s
                JOIN metro_schedule_stops d_stop
                     ON d_stop.schedule_id = s.schedule_id AND d_stop.station_id = %s
                WHERE o_stop.stop_order < d_stop.stop_order
                """,
                (origin_id, destination_id),
            )
            return [dict(r) for r in cur.fetchall()]


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
        "total_fare_usd": round(base + per_stop * int(stops_travelled), 2),
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
                """
                SELECT user_id, full_name, email, phone, date_of_birth,
                       secret_question, registered_at, is_active
                FROM registered_users
                WHERE email = %s AND is_active = TRUE
                """,
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
                "SELECT user_id FROM registered_users WHERE email = %s",
                (user_email,),
            )
            user_row = cur.fetchone()
            if user_row is None:
                return {"national_rail": [], "metro": []}
            uid = user_row["user_id"]

            cur.execute(
                """
                SELECT b.*, s.line, s.service_type
                FROM bookings b
                JOIN national_rail_schedules s ON b.schedule_id = s.schedule_id
                WHERE b.user_id = %s
                """,
                (uid,),
            )
            nr = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT m.*, s.line
                FROM metro_travel_history m
                JOIN metro_schedules s ON m.schedule_id = s.schedule_id
                WHERE m.user_id = %s
                """,
                (uid,),
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
            # 1. Fetch schedule fares and stop positions via junction table
            cur.execute(
                """
                SELECT s.first_train_time,
                       s.std_base_fare_usd, s.std_per_stop_rate_usd,
                       s.first_base_fare_usd, s.first_per_stop_rate_usd,
                       o_stop.stop_order AS origin_pos,
                       d_stop.stop_order AS dest_pos
                FROM national_rail_schedules s
                LEFT JOIN national_rail_schedule_stops o_stop
                     ON o_stop.schedule_id = s.schedule_id AND o_stop.station_id = %s
                LEFT JOIN national_rail_schedule_stops d_stop
                     ON d_stop.schedule_id = s.schedule_id AND d_stop.station_id = %s
                WHERE s.schedule_id = %s
                """,
                (origin_station_id, destination_station_id, schedule_id),
            )
            schedule = cur.fetchone()
            if schedule is None:
                return (False, "Schedule not found")

            if schedule["origin_pos"] is None or schedule["dest_pos"] is None:
                return (False, "Stations not on this route")
            if schedule["origin_pos"] >= schedule["dest_pos"]:
                return (False, "Invalid route direction")
            stops_count = schedule["dest_pos"] - schedule["origin_pos"]

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

            # 5. Insert payment — same transaction as booking insert.
            # Single conn.commit() makes both operations atomic: if payment fails,
            # rollback removes the booking too, preventing orphaned records.
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
    # Read policy file before opening the DB connection — file I/O inside a
    # transaction holds the connection open unnecessarily and risks timeouts.
    with open(_POLICY_PATH, encoding="utf-8") as f:
        policies = json.load(f)
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
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

            # 3. Calculate hours until departure to determine which refund window applies.
            # travel_date (DATE) + departure_time (TIME) are combined into a tz-aware datetime
            # so the comparison against now() is accurate regardless of server timezone.
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
    user_id = "RU" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(6))
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
    # ui.py expects first_name + surname; schema stores full_name only — split here
    parts = (user.get("full_name") or "").split(" ", 1)
    user["first_name"] = parts[0]
    user["surname"]    = parts[1] if len(parts) > 1 else ""
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
    # Case-insensitive strip: prevents trivial bypass via capitalisation or whitespace differences
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


# ── TASK 6 EXTENSION: DELAY EVENT LOGGING ────────────────────────────────────

def log_delay_event(station_id: str, severity: str, description: str) -> int:
    """
    Insert a new delay event for a station and return its event_id.

    Args:
        station_id:   Metro (e.g. MS03) or national rail (e.g. NR02) station ID.
        severity:     One of 'low', 'medium', 'high'.
        description:  Human-readable description of the disruption.

    Returns:
        The new event_id (SERIAL, integer).
    """
    # reported_at defaults to NOW() in the schema; we rely on the DB clock
    # so that all timestamps are consistent even under concurrent inserts.
    sql = """
        INSERT INTO delay_events (station_id, severity, description)
        VALUES (%s, %s, %s)
        RETURNING event_id
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (station_id, severity, description))
            event_id = cur.fetchone()[0]
        conn.commit()
    return event_id


def get_active_delays(station_id: Optional[str] = None) -> list[dict]:
    """
    Return all unresolved delay events, optionally filtered to one station.

    A delay is 'active' when resolved_at IS NULL.  Returning a list rather
    than a single row lets the agent surface multiple concurrent disruptions
    in one tool call, avoiding a round-trip per station.

    Args:
        station_id: Optional filter — pass a station ID to narrow results.

    Returns:
        List of dicts: event_id, station_id, reported_at, severity, description.
    """
    base_sql = """
        SELECT event_id, station_id, reported_at, severity, description
        FROM delay_events
        WHERE resolved_at IS NULL
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if station_id:
                cur.execute(base_sql + " AND station_id = %s ORDER BY reported_at DESC", (station_id,))
            else:
                cur.execute(base_sql + " ORDER BY reported_at DESC")
            return [dict(r) for r in cur.fetchall()]


def resolve_delay(event_id: int) -> bool:
    """
    Mark a delay event as resolved by setting resolved_at to the current time.

    Returns True if a row was updated, False if the event_id does not exist
    or was already resolved.  The caller can use the return value to detect
    double-resolution without raising an exception.
    """
    sql = """
        UPDATE delay_events
        SET resolved_at = NOW()
        WHERE event_id = %s AND resolved_at IS NULL
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (int(event_id),))
            updated = cur.rowcount
        conn.commit()
    return updated > 0
