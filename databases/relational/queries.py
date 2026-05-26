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
from datetime import datetime, timezone
from typing import Optional

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
    sql = """
        SELECT 
            schedule_id, line, service_type, direction,
            origin_station_id, destination_station_id, stops_in_order,
            first_train_time, last_train_time, frequency_min, operates_on,
            std_base_fare_usd, std_per_stop_rate_usd,
            first_base_fare_usd, first_per_stop_rate_usd
        FROM national_rail_schedules
        WHERE stops_in_order @> ARRAY[%s, %s]::VARCHAR(10)[]
          AND array_position(stops_in_order, %s) < array_position(stops_in_order, %s);
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (origin_id, destination_id, origin_id, destination_id))
            schedules = [dict(row) for row in cur.fetchall()]
            
            for sched in schedules:
                stops = sched["stops_in_order"]
                # Calculate stops travelled
                stops_travelled = stops.index(destination_id) - stops.index(origin_id)
                sched["stops_travelled"] = stops_travelled
                
                # Fetch total seats by class from layouts
                cur.execute("""
                    SELECT fare_class, COUNT(*) as total_seats 
                    FROM seat_layouts 
                    WHERE schedule_id = %s 
                    GROUP BY fare_class
                """, (sched["schedule_id"],))
                layouts = {row["fare_class"]: row["total_seats"] for row in cur.fetchall()}
                
                std_total = layouts.get("standard", 0)
                first_total = layouts.get("first", 0)
                
                sched["standard_seats_total"] = std_total
                sched["first_seats_total"] = first_total
                
                if travel_date:
                    # Count active bookings that overlap this segment
                    cur.execute("""
                        SELECT b.fare_class, COUNT(*) as booked_seats
                        FROM bookings b
                        JOIN national_rail_schedules s ON b.schedule_id = s.schedule_id
                        WHERE b.schedule_id = %s
                          AND b.travel_date = %s
                          AND b.status IN ('confirmed', 'completed')
                          AND array_position(s.stops_in_order, b.origin_station_id) < array_position(s.stops_in_order, %s)
                          AND array_position(s.stops_in_order, %s) < array_position(s.stops_in_order, b.destination_station_id)
                        GROUP BY b.fare_class
                    """, (sched["schedule_id"], travel_date, destination_id, origin_id))
                    
                    bookings = {row["fare_class"]: row["booked_seats"] for row in cur.fetchall()}
                    std_booked = bookings.get("standard", 0)
                    first_booked = bookings.get("first", 0)
                    
                    sched["standard_seats_booked"] = std_booked
                    sched["standard_seats_available"] = max(0, std_total - std_booked)
                    sched["first_seats_booked"] = first_booked
                    sched["first_seats_available"] = max(0, first_total - first_booked)
                else:
                    sched["standard_seats_booked"] = None
                    sched["standard_seats_available"] = std_total
                    sched["first_seats_booked"] = None
                    sched["first_seats_available"] = first_total
                    
            return schedules


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
    sql = """
        SELECT 
            std_base_fare_usd, std_per_stop_rate_usd,
            first_base_fare_usd, first_per_stop_rate_usd
        FROM national_rail_schedules
        WHERE schedule_id = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id,))
            row = cur.fetchone()
            if not row:
                return None
            
            if fare_class == "first":
                base = row["first_base_fare_usd"]
                rate = row["first_per_stop_rate_usd"]
            else:
                base = row["std_base_fare_usd"]
                rate = row["std_per_stop_rate_usd"]
                
            total = base + rate * stops_travelled
            return {
                "fare_class": fare_class,
                "base_fare_usd": float(base),
                "per_stop_rate_usd": float(rate),
                "total_fare_usd": float(total)
            }


# ── METRO SCHEDULES & FARE ────────────────────────────────────────────────────

def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """
    Return metro schedules that serve both origin and destination in the correct order.

    Args:
        origin_id:       e.g. "MS01"
        destination_id:  e.g. "MS09"
    """
    sql = """
        SELECT 
            schedule_id, line, direction, origin_station_id, destination_station_id,
            stops_in_order, travel_time_from_origin, first_train_time, last_train_time,
            frequency_min, operates_on, base_fare_usd, per_stop_rate_usd
        FROM metro_schedules
        WHERE stops_in_order @> ARRAY[%s, %s]::VARCHAR(10)[]
          AND array_position(stops_in_order, %s) < array_position(stops_in_order, %s);
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (origin_id, destination_id, origin_id, destination_id))
            return [dict(row) for row in cur.fetchall()]


def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """
    Calculate the metro fare for a single-ticket journey.

    Args:
        schedule_id:     e.g. "MS_SCH01"
        stops_travelled: number of stops between origin and destination

    Returns:
        dict with base_fare_usd, per_stop_rate_usd, total_fare_usd
    """
    sql = """
        SELECT base_fare_usd, per_stop_rate_usd
        FROM metro_schedules
        WHERE schedule_id = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id,))
            row = cur.fetchone()
            if not row:
                return None
            
            base = row["base_fare_usd"]
            rate = row["per_stop_rate_usd"]
            total = base + rate * stops_travelled
            return {
                "base_fare_usd": float(base),
                "per_stop_rate_usd": float(rate),
                "total_fare_usd": float(total)
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
    sql = """
        SELECT seat_id, coach, row_num AS row, col_char AS column
        FROM seat_layouts
        WHERE schedule_id = %s
          AND fare_class = %s
          AND seat_id NOT IN (
              SELECT seat_id
              FROM bookings
              WHERE schedule_id = %s
                AND travel_date = %s
                AND status IN ('confirmed', 'completed')
          )
        ORDER BY coach, row_num, col_char;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id, fare_class, schedule_id, travel_date))
            return [dict(row) for row in cur.fetchall()]


# ── USER & BOOKING QUERIES ────────────────────────────────────────────────────

def query_user_profile(user_email: str) -> Optional[dict]:
    """Return a user's profile by email."""
    sql = """
        SELECT user_id, full_name, email, phone, date_of_birth, secret_question, is_active
        FROM registered_users
        WHERE email = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (user_email,))
            row = cur.fetchone()
            return dict(row) if row else None


def query_user_bookings(user_email: str) -> dict:
    """
    Return a user's combined booking history (national rail + metro).

    Returns:
        dict with keys 'national_rail' (list) and 'metro' (list)
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT user_id FROM registered_users WHERE email = %s;", (user_email,))
            user_row = cur.fetchone()
            if not user_row:
                return {"national_rail": [], "metro": []}
            
            user_id = user_row["user_id"]
            
            cur.execute("""
                SELECT booking_id, schedule_id, origin_station_id, destination_station_id,
                       travel_date, departure_time, ticket_type, fare_class, coach, seat_id,
                       stops_travelled, amount_usd, status, booked_at, travelled_at, cancelled_at
                FROM bookings
                WHERE user_id = %s
                ORDER BY booked_at DESC;
            """, (user_id,))
            nr_bookings = [dict(row) for row in cur.fetchall()]
            
            cur.execute("""
                SELECT trip_id, schedule_id, origin_station_id, destination_station_id,
                       travel_date, ticket_type, day_pass_ref, stops_travelled, amount_usd,
                       status, purchased_at, travelled_at, cancelled_at
                FROM metro_travel_history
                WHERE user_id = %s
                ORDER BY travelled_at DESC;
            """, (user_id,))
            metro_bookings = [dict(row) for row in cur.fetchall()]
            
            return {
                "national_rail": nr_bookings,
                "metro": metro_bookings
            }


def query_payment_info(booking_id: str) -> Optional[dict]:
    """Return payment record for a booking or metro trip."""
    sql = """
        SELECT payment_id, booking_id, amount_usd, method, status, paid_at, refunded_at
        FROM payments
        WHERE booking_id = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (booking_id,))
            row = cur.fetchone()
            return dict(row) if row else None


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
    from datetime import datetime, timezone
    
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Fetch schedule details
            cur.execute("""
                SELECT line, service_type, stops_in_order, first_train_time, 
                       std_base_fare_usd, std_per_stop_rate_usd, 
                       first_base_fare_usd, first_per_stop_rate_usd
                FROM national_rail_schedules
                WHERE schedule_id = %s;
            """, (schedule_id,))
            sched = cur.fetchone()
            if not sched:
                return False, "Schedule not found"
            
            stops = sched["stops_in_order"]
            if origin_station_id not in stops or destination_station_id not in stops:
                return False, "Invalid origin or destination station for this schedule"
                
            orig_idx = stops.index(origin_station_id)
            dest_idx = stops.index(destination_station_id)
            if orig_idx >= dest_idx:
                return False, "Origin station must precede destination station"
                
            # 2. Select seat
            coach = None
            if seat_id.lower() == "any":
                cur.execute("""
                    SELECT seat_id, coach
                    FROM seat_layouts
                    WHERE schedule_id = %s
                      AND fare_class = %s
                      AND seat_id NOT IN (
                          SELECT seat_id
                          FROM bookings
                          WHERE schedule_id = %s
                            AND travel_date = %s
                            AND status IN ('confirmed', 'completed')
                      )
                    ORDER BY coach, row_num, col_char
                    LIMIT 1;
                """, (schedule_id, fare_class, schedule_id, travel_date))
                seat_row = cur.fetchone()
                if not seat_row:
                    return False, "No seats available in this class for the selected train"
                selected_seat_id = seat_row["seat_id"]
                coach = seat_row["coach"]
            else:
                cur.execute("""
                    SELECT coach, fare_class
                    FROM seat_layouts
                    WHERE schedule_id = %s
                      AND seat_id = %s;
                """, (schedule_id, seat_id))
                seat_row = cur.fetchone()
                if not seat_row:
                    return False, f"Seat {seat_id} does not exist on this train"
                if seat_row["fare_class"] != fare_class:
                    return False, f"Seat {seat_id} is {seat_row['fare_class']} class, but requested {fare_class}"
                
                cur.execute("""
                    SELECT COUNT(*) as cnt
                    FROM bookings
                    WHERE schedule_id = %s
                      AND travel_date = %s
                      AND seat_id = %s
                      AND status IN ('confirmed', 'completed');
                """, (schedule_id, travel_date, seat_id))
                if cur.fetchone()["cnt"] > 0:
                    return False, f"Seat {seat_id} is already booked for this date"
                
                selected_seat_id = seat_id
                coach = seat_row["coach"]
                
            # 3. Calculate fare
            stops_travelled = dest_idx - orig_idx
            if fare_class == "first":
                base = sched["first_base_fare_usd"]
                rate = sched["first_per_stop_rate_usd"]
            else:
                base = sched["std_base_fare_usd"]
                rate = sched["std_per_stop_rate_usd"]
            amount = base + rate * stops_travelled
            
            if ticket_type == "return":
                amount = amount * 2.0
                
            # 4. Create booking
            booking_id = _gen_booking_id()
            departure_time = sched["first_train_time"]
            booked_at = datetime.now(timezone.utc)
            
            cur.execute("""
                INSERT INTO bookings (
                    booking_id, user_id, schedule_id, origin_station_id, destination_station_id,
                    travel_date, departure_time, ticket_type, fare_class, coach, seat_id,
                    stops_travelled, amount_usd, status, booked_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'confirmed', %s);
            """, (
                booking_id, user_id, schedule_id, origin_station_id, destination_station_id,
                travel_date, departure_time, ticket_type, fare_class, coach, selected_seat_id,
                stops_travelled, amount, booked_at
            ))
            
            # 5. Create payment
            payment_id = _gen_payment_id()
            cur.execute("""
                INSERT INTO payments (payment_id, booking_id, amount_usd, method, status, paid_at)
                VALUES (%s, %s, %s, 'credit_card', 'paid', %s);
            """, (payment_id, booking_id, amount, booked_at))
            
            conn.commit()
            
            return True, {
                "booking_id": booking_id,
                "user_id": user_id,
                "schedule_id": schedule_id,
                "origin_station_id": origin_station_id,
                "destination_station_id": destination_station_id,
                "travel_date": str(travel_date),
                "departure_time": str(departure_time),
                "ticket_type": ticket_type,
                "fare_class": fare_class,
                "coach": coach,
                "seat_id": selected_seat_id,
                "stops_travelled": stops_travelled,
                "amount_usd": float(amount),
                "status": "confirmed",
                "payment_id": payment_id
            }
    except Exception as e:
        conn.rollback()
        return False, f"Database transaction failed: {str(e)}"
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
        (True, result_dict)  with refund_amount_usd and policy note
        (False, error_msg)
    """
    from datetime import datetime, timezone, time
    
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Fetch booking and schedule details
            cur.execute("""
                SELECT b.booking_id, b.user_id, b.status, b.amount_usd, b.travel_date, b.departure_time,
                       s.service_type
                FROM bookings b
                JOIN national_rail_schedules s ON b.schedule_id = s.schedule_id
                WHERE b.booking_id = %s;
            """, (booking_id,))
            booking = cur.fetchone()
            
            if not booking:
                return False, "Booking not found"
                
            if booking["user_id"] != user_id:
                return False, "You do not own this booking"
                
            if booking["status"] == "cancelled":
                return False, "Booking is already cancelled"
                
            if booking["status"] == "completed":
                return False, "Cannot cancel a completed trip"
                
            travel_date = booking["travel_date"]
            dep_time = booking["departure_time"]
            
            if isinstance(travel_date, str):
                travel_date = datetime.strptime(travel_date, "%Y-%m-%d").date()
                
            if isinstance(dep_time, str):
                parts = list(map(int, dep_time.split(":")))
                dep_time = time(*parts)
            elif isinstance(dep_time, (int, float)):
                # If time is interval or offset
                dep_time = time(0, 0)
                
            dep_datetime = datetime.combine(travel_date, dep_time)
            
            # Compute time difference (treat local time as naive)
            now = datetime.now()
            diff = dep_datetime - now
            hours_before = diff.total_seconds() / 3600.0
            
            if hours_before < 0:
                return False, "Cannot cancel a booking after the departure time has passed"
                
            service_type = booking["service_type"]
            amount_usd = float(booking["amount_usd"])
            
            if service_type == "express":
                if hours_before >= 48:
                    refund_percent = 100
                    admin_fee = 1.00
                    policy_note = "Early cancellation policy (RF002): 100% refund, $1.00 fee."
                elif hours_before >= 24:
                    refund_percent = 50
                    admin_fee = 1.00
                    policy_note = "Late cancellation policy (RF002): 50% refund, $1.00 fee."
                else:
                    refund_percent = 0
                    admin_fee = 0.00
                    policy_note = "No refund policy (RF002): Less than 24 hours before departure."
            else:  # normal service
                if hours_before >= 48:
                    refund_percent = 100
                    admin_fee = 0.00
                    policy_note = "Early cancellation policy (RF001): 100% refund, no fee."
                elif hours_before >= 24:
                    refund_percent = 75
                    admin_fee = 0.50
                    policy_note = "Standard cancellation policy (RF001): 75% refund, $0.50 fee."
                elif hours_before >= 2:
                    refund_percent = 50
                    admin_fee = 0.50
                    policy_note = "Late cancellation policy (RF001): 50% refund, $0.50 fee."
                else:
                    refund_percent = 0
                    admin_fee = 0.00
                    policy_note = "No refund policy (RF001): Less than 2 hours before departure."
                    
            refund_amount = (amount_usd * (refund_percent / 100.0)) - admin_fee
            refund_amount = max(0.0, refund_amount)
            
            cancelled_at = datetime.now(timezone.utc)
            cur.execute("""
                UPDATE bookings 
                SET status = 'cancelled', cancelled_at = %s 
                WHERE booking_id = %s;
            """, (cancelled_at, booking_id))
            
            cur.execute("""
                UPDATE payments 
                SET status = 'refunded', refunded_at = %s 
                WHERE booking_id = %s;
            """, (cancelled_at, booking_id))
            
            conn.commit()
            
            return True, {
                "booking_id": booking_id,
                "refund_amount_usd": round(refund_amount, 2),
                "policy_note": policy_note,
                "status": "cancelled"
            }
            
    except Exception as e:
        conn.rollback()
        return False, f"Cancellation failed: {str(e)}"
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

    NOTE: passwords are stored as plain text here intentionally for teaching
    purposes. In production, replace with a salted hash (e.g. bcrypt).
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM registered_users WHERE email = %s;", (email,))
            if cur.fetchone()["cnt"] > 0:
                return False, "Email already registered"
                
            cur.execute("SELECT user_id FROM registered_users;")
            ids = [row["user_id"] for row in cur.fetchall()]
            nums = []
            for uid in ids:
                if uid.startswith("RU") and uid[2:].isdigit():
                    nums.append(int(uid[2:]))
            next_num = max(nums) + 1 if nums else 1
            new_uid = f"RU{next_num:02d}"
            
            full_name = f"{first_name} {surname}"
            dob = f"{year_of_birth}-01-01"
            
            cur.execute("""
                INSERT INTO registered_users (
                    user_id, full_name, email, password, date_of_birth, 
                    secret_question, secret_answer, is_active, registered_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, NOW());
            """, (new_uid, full_name, email, password, dob, secret_question, secret_answer))
            
            conn.commit()
            return True, new_uid
    except Exception as e:
        conn.rollback()
        return False, f"Registration failed: {str(e)}"
    finally:
        conn.close()


def login_user(email: str, password: str) -> Optional[dict]:
    """
    Verify credentials. Returns a user dict on success or None on failure.
    Dict keys: user_id, email, full_name, first_name, surname, phone, date_of_birth, is_active.
    """
    sql = """
        SELECT user_id, email, full_name, phone, date_of_birth, is_active, password
        FROM registered_users
        WHERE email = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            if not row:
                return None
                
            if row["password"] != password:
                return None
                
            if not row["is_active"]:
                return None
                
            full_name = row["full_name"] or ""
            parts = full_name.split(" ", 1)
            first_name = parts[0]
            surname = parts[1] if len(parts) > 1 else ""
            
            return {
                "user_id": row["user_id"],
                "email": row["email"],
                "full_name": full_name,
                "first_name": first_name,
                "surname": surname,
                "phone": row["phone"],
                "date_of_birth": str(row["date_of_birth"]) if row["date_of_birth"] else None,
                "is_active": row["is_active"]
            }


def get_user_secret_question(email: str) -> Optional[str]:
    """Return the secret question for a registered email, or None if not found."""
    sql = "SELECT secret_question FROM registered_users WHERE email = %s;"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            return row[0] if row else None


def verify_secret_answer(email: str, answer: str) -> bool:
    """Return True if the provided answer matches the stored secret answer (case-insensitive)."""
    sql = "SELECT secret_answer FROM registered_users WHERE email = %s;"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            if not row:
                return False
            stored_answer = row[0]
            return stored_answer.strip().lower() == answer.strip().lower()


def update_password(email: str, new_password: str) -> bool:
    """Update the password for a user. Returns True if the row was updated."""
    sql = "UPDATE registered_users SET password = %s WHERE email = %s;"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (new_password, email))
            return cur.rowcount > 0


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
