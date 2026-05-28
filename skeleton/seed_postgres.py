"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.

Usage:
    python skeleton/seed_postgres.py

Run AFTER docker-compose up -d.
You must first design and create your tables in databases/relational/schema.sql.
Safe to re-run: implement your inserts with ON CONFLICT DO NOTHING.
"""

import json
import os
import sys

import bcrypt
import psycopg2
from psycopg2.extras import execute_values

# ── resolve paths ────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR    = os.path.join(PROJECT_DIR, "train-mock-data")

sys.path.insert(0, PROJECT_DIR)
from skeleton import config as cfg


def load(filename):
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def connect():
    return psycopg2.connect(
        host=cfg.PG_HOST,
        port=cfg.PG_PORT,
        dbname=cfg.PG_DB,
        user=cfg.PG_USER,
        password=cfg.PG_PASSWORD,
    )


def insert_many(cur, table, columns, rows):
    """Bulk insert with ON CONFLICT DO NOTHING. Returns row count inserted."""
    if not rows:
        return 0
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"ON CONFLICT DO NOTHING"
    )
    execute_values(cur, sql, rows)
    return cur.rowcount


# ── seeders ──────────────────────────────────────────────────────────────────

def seed_metro_stations(cur):
    """
    Seed metro_stations table from metro_stations.json.
    Ignores adjacent_stations. Sets interchange_nr_station_id = None to avoid circular FK.
    """
    data = load("metro_stations.json")
    columns = [
        "station_id", "name", "lines", "is_interchange_metro", 
        "is_interchange_national_rail", "interchange_nr_station_id"
    ]
    rows = []
    for s in data:
        rows.append((
            s.get("station_id"),
            s.get("name"),
            s.get("lines", []),
            s.get("is_interchange_metro", False),
            s.get("is_interchange_national_rail", False),
            None  # Set to None initially due to circular dependency
        ))
        
    inserted = insert_many(cur, "metro_stations", columns, rows)
    print(f"Seeded {inserted} metro stations.")


def seed_national_rail_stations(cur):
    """
    Seed national_rail_stations table from national_rail_stations.json.
    Ignores adjacent_stations.
    """
    data = load("national_rail_stations.json")
    columns = [
        "station_id", "name", "lines", "is_interchange_national_rail", 
        "is_interchange_metro", "interchange_metro_station_id"
    ]
    rows = []
    for s in data:
        rows.append((
            s.get("station_id"),
            s.get("name"),
            s.get("lines", []),
            s.get("is_interchange_national_rail", False),
            s.get("is_interchange_metro", False),
            s.get("interchange_metro_station_id")
        ))
        
    inserted = insert_many(cur, "national_rail_stations", columns, rows)
    print(f"Seeded {inserted} national rail stations.")


def update_metro_interchange(cur):
    """
    Update metro_stations table to set interchange_nr_station_id.
    This resolves the circular dependency between the two station tables.
    """
    data = load("metro_stations.json")
    rows = []
    for s in data:
        nr_id = s.get("interchange_national_rail_station_id")
        if nr_id:
            rows.append((nr_id, s.get("station_id")))
            
    if not rows:
        return
        
    sql = """
        UPDATE metro_stations AS m
        SET interchange_nr_station_id = v.nr_id
        FROM (VALUES %s) AS v(nr_id, station_id)
        WHERE m.station_id = v.station_id
    """
    execute_values(cur, sql, rows)
    print(f"Updated {len(rows)} metro stations with NR interchanges.")



def seed_metro_schedules(cur):
    """
    Seed metro_schedules table from metro_schedules.json.
    Converts travel_time_from_origin_min dict to JSON string for the JSONB column.
    """
    data = load("metro_schedules.json")
    columns = [
        "schedule_id", "line", "direction", "origin_station_id", 
        "destination_station_id", "stops_in_order", "travel_time_from_origin", 
        "first_train_time", "last_train_time", "frequency_min", 
        "operates_on", "base_fare_usd", "per_stop_rate_usd"
    ]
    rows = []
    for s in data:
        rows.append((
            s.get("schedule_id"),
            s.get("line"),
            s.get("direction"),
            s.get("origin_station_id"),
            s.get("destination_station_id"),
            s.get("stops_in_order", []),
            json.dumps(s.get("travel_time_from_origin_min", {})),
            s.get("first_train_time"),
            s.get("last_train_time"),
            s.get("frequency_min"),
            s.get("operates_on", []),
            s.get("base_fare_usd"),
            s.get("per_stop_rate_usd")
        ))
        
    inserted = insert_many(cur, "metro_schedules", columns, rows)
    print(f"Seeded {inserted} metro schedules.")


def seed_national_rail_schedules(cur):
    """
    Seed national_rail_schedules table from national_rail_schedules.json.
    Flattens fare_classes and converts travel_time_from_origin_min dict to JSONB string.
    Sets passed_through_stations = None.
    """
    data = load("national_rail_schedules.json")
    columns = [
        "schedule_id", "line", "service_type", "direction", "origin_station_id", 
        "destination_station_id", "stops_in_order", "passed_through_stations", 
        "travel_time_from_origin", "first_train_time", "last_train_time", 
        "frequency_min", "operates_on", "std_base_fare_usd", "std_per_stop_rate_usd", 
        "first_base_fare_usd", "first_per_stop_rate_usd"
    ]
    rows = []
    for s in data:
        fare_std = s.get("fare_classes", {}).get("standard", {})
        fare_first = s.get("fare_classes", {}).get("first", {})
        
        rows.append((
            s.get("schedule_id"),
            s.get("line"),
            s.get("service_type"),
            s.get("direction"),
            s.get("origin_station_id"),
            s.get("destination_station_id"),
            s.get("stops_in_order", []),
            None,
            json.dumps(s.get("travel_time_from_origin_min", {})),
            s.get("first_train_time"),
            s.get("last_train_time"),
            s.get("frequency_min"),
            s.get("operates_on", []),
            fare_std.get("base_fare_usd"),
            fare_std.get("per_stop_rate_usd"),
            fare_first.get("base_fare_usd"),
            fare_first.get("per_stop_rate_usd")
        ))
        
    inserted = insert_many(cur, "national_rail_schedules", columns, rows)
    print(f"Seeded {inserted} national rail schedules.")


def seed_seat_layouts(cur):
    """
    Seed seat_layouts table from national_rail_seat_layouts.json.
    Flattens the nested coaches and seats lists into individual rows.
    """
    data = load("national_rail_seat_layouts.json")
    columns = [
        "schedule_id", "seat_id", "coach", "row_num", "col_char", "fare_class"
    ]
    rows = []
    for schedule in data:
        schedule_id = schedule.get("schedule_id")
        coaches = schedule.get("coaches", [])
        for coach in coaches:
            coach_id = coach.get("coach")
            seats = coach.get("seats", [])
            for seat in seats:
                rows.append((
                    schedule_id,
                    seat.get("seat_id"),
                    coach_id,
                    seat.get("row"),
                    seat.get("column"),
                    seat.get("fare_class")
                ))
                
    inserted = insert_many(cur, "seat_layouts", columns, rows)
    print(f"Seeded {inserted} seat layouts.")


def seed_users(cur):
    """
    Seed registered_users table from registered_users.json.
    Hashes the plaintext password using bcrypt before inserting.
    """
    data = load("registered_users.json")
    columns = [
        "user_id", "full_name", "email", "password", "phone",
        "date_of_birth", "secret_question", "secret_answer",
        "registered_at", "is_active"
    ]
    
    rows = []
    for u in data:
        pwd = u.get("password", "")
        hashed_pwd = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()
        rows.append((
            u.get("user_id"),
            u.get("full_name"),
            u.get("email"),
            hashed_pwd,
            u.get("phone"),
            u.get("date_of_birth"),
            u.get("secret_question"),
            u.get("secret_answer"),
            u.get("registered_at"),
            u.get("is_active")
        ))
        
    inserted = insert_many(cur, "registered_users", columns, rows)
    print(f"Seeded {inserted} users.")


def seed_national_rail_bookings(cur):
    data = load("bookings.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    pass


def seed_metro_travels(cur):
    data = load("metro_travel_history.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    pass


def seed_payments(cur):
    data = load("payments.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    pass


def seed_feedback(cur):
    data = load("feedback.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    pass


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL...")
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Seeding tables (dependency order):")
        seed_users(cur)
        seed_metro_stations(cur)
        seed_national_rail_stations(cur)
        update_metro_interchange(cur)
        seed_metro_schedules(cur)
        seed_national_rail_schedules(cur)
        seed_seat_layouts(cur)
        seed_national_rail_bookings(cur)
        seed_metro_travels(cur)
        seed_payments(cur)
        seed_feedback(cur)
        conn.commit()
        print("\nAll done. Database seeded successfully.")
    except Exception as e:
        conn.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
