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
    data = load("national_rail_stations.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    pass


def update_metro_interchange(cur):
    data = load("metro_stations.json")
    # TODO: Implement the update logic here.
    pass



def seed_metro_schedules(cur):
    data = load("metro_schedules.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    pass


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    pass


def seed_seat_layouts(cur):
    data = load("national_rail_seat_layouts.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    pass


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
