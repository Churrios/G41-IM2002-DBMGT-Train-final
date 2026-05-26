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
    data = load("metro_stations.json")
    columns = [
        "station_id",
        "name",
        "lines",
        "is_interchange_metro",
        "is_interchange_national_rail",
        "interchange_nr_station_id"
    ]
    rows = [
        (
            item["station_id"],
            item["name"],
            item["lines"],
            item["is_interchange_metro"],
            item["is_interchange_national_rail"],
            None  # Set to None initially to avoid FK constraint errors
        )
        for item in data
    ]
    cnt = insert_many(cur, "metro_stations", columns, rows)
    print(f"  Seeded {cnt} metro stations")


def seed_national_rail_stations(cur):
    data = load("national_rail_stations.json")
    columns = [
        "station_id",
        "name",
        "lines",
        "is_interchange_national_rail",
        "is_interchange_metro",
        "interchange_metro_station_id"
    ]
    rows = [
        (
            item["station_id"],
            item["name"],
            item["lines"],
            item["is_interchange_national_rail"],
            item["is_interchange_metro"],
            None  # Set to None initially to avoid FK constraint errors
        )
        for item in data
    ]
    cnt = insert_many(cur, "national_rail_stations", columns, rows)
    print(f"  Seeded {cnt} national rail stations")

    # Update interchange relations to resolve circular dependency
    # 1. Update metro_stations interchange links
    metro_data = load("metro_stations.json")
    metro_updates = [
        (item["interchange_national_rail_station_id"], item["station_id"])
        for item in metro_data
        if item.get("is_interchange_national_rail") and item.get("interchange_national_rail_station_id")
    ]
    if metro_updates:
        cur.executemany(
            "UPDATE metro_stations SET interchange_nr_station_id = %s WHERE station_id = %s",
            metro_updates
        )
        print(f"  Linked {len(metro_updates)} metro stations to national rail interchanges")

    # 2. Update national_rail_stations interchange links
    nr_updates = [
        (item["interchange_metro_station_id"], item["station_id"])
        for item in data
        if item.get("is_interchange_metro") and item.get("interchange_metro_station_id")
    ]
    if nr_updates:
        cur.executemany(
            "UPDATE national_rail_stations SET interchange_metro_station_id = %s WHERE station_id = %s",
            nr_updates
        )
        print(f"  Linked {len(nr_updates)} national rail stations to metro interchanges")


def seed_metro_schedules(cur):
    data = load("metro_schedules.json")
    columns = [
        "schedule_id",
        "line",
        "direction",
        "origin_station_id",
        "destination_station_id",
        "stops_in_order",
        "travel_time_from_origin",
        "first_train_time",
        "last_train_time",
        "frequency_min",
        "operates_on",
        "base_fare_usd",
        "per_stop_rate_usd"
    ]
    rows = [
        (
            item["schedule_id"],
            item["line"],
            item["direction"],
            item["origin_station_id"],
            item["destination_station_id"],
            item["stops_in_order"],
            json.dumps(item["travel_time_from_origin_min"]),
            item["first_train_time"],
            item["last_train_time"],
            item["frequency_min"],
            item["operates_on"],
            item["base_fare_usd"],
            item["per_stop_rate_usd"]
        )
        for item in data
    ]
    cnt = insert_many(cur, "metro_schedules", columns, rows)
    print(f"  Seeded {cnt} metro schedules")


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")
    columns = [
        "schedule_id",
        "line",
        "service_type",
        "direction",
        "origin_station_id",
        "destination_station_id",
        "stops_in_order",
        "passed_through_stations",
        "travel_time_from_origin",
        "first_train_time",
        "last_train_time",
        "frequency_min",
        "operates_on",
        "std_base_fare_usd",
        "std_per_stop_rate_usd",
        "first_base_fare_usd",
        "first_per_stop_rate_usd"
    ]
    rows = [
        (
            item["schedule_id"],
            item["line"],
            item["service_type"],
            item["direction"],
            item["origin_station_id"],
            item["destination_station_id"],
            item["stops_in_order"],
            item.get("passed_through_stations"),
            json.dumps(item["travel_time_from_origin_min"]),
            item["first_train_time"],
            item["last_train_time"],
            item["frequency_min"],
            item["operates_on"],
            item["fare_classes"]["standard"]["base_fare_usd"],
            item["fare_classes"]["standard"]["per_stop_rate_usd"],
            item["fare_classes"]["first"]["base_fare_usd"],
            item["fare_classes"]["first"]["per_stop_rate_usd"]
        )
        for item in data
    ]
    cnt = insert_many(cur, "national_rail_schedules", columns, rows)
    print(f"  Seeded {cnt} national rail schedules")


def seed_seat_layouts(cur):
    data = load("national_rail_seat_layouts.json")
    columns = [
        "schedule_id",
        "seat_id",
        "coach",
        "row_num",
        "col_char",
        "fare_class"
    ]
    rows = []
    for item in data:
        sched_id = item["schedule_id"]
        for coach_data in item["coaches"]:
            coach = coach_data["coach"]
            fare_class = coach_data["fare_class"]
            for seat in coach_data["seats"]:
                rows.append((
                    sched_id,
                    seat["seat_id"],
                    coach,
                    seat["row"],
                    seat["column"],
                    fare_class
                ))
    cnt = insert_many(cur, "seat_layouts", columns, rows)
    print(f"  Seeded {cnt} seat layouts")


def seed_users(cur):
    data = load("registered_users.json")
    columns = [
        "user_id",
        "full_name",
        "email",
        "password",
        "phone",
        "date_of_birth",
        "secret_question",
        "secret_answer",
        "registered_at",
        "is_active"
    ]
    rows = [
        (
            item["user_id"],
            item["full_name"],
            item["email"],
            item["password"],
            item.get("phone"),
            item["date_of_birth"],
            item["secret_question"],
            item["secret_answer"],
            item["registered_at"],
            item["is_active"]
        )
        for item in data
    ]
    cnt = insert_many(cur, "registered_users", columns, rows)
    print(f"  Seeded {cnt} registered users")


def seed_national_rail_bookings(cur):
    data = load("bookings.json")
    columns = [
        "booking_id",
        "user_id",
        "schedule_id",
        "origin_station_id",
        "destination_station_id",
        "travel_date",
        "departure_time",
        "ticket_type",
        "fare_class",
        "coach",
        "seat_id",
        "stops_travelled",
        "amount_usd",
        "status",
        "booked_at",
        "travelled_at"
    ]
    rows = [
        (
            item["booking_id"],
            item["user_id"],
            item["schedule_id"],
            item["origin_station_id"],
            item["destination_station_id"],
            item["travel_date"],
            item["departure_time"],
            item["ticket_type"],
            item["fare_class"],
            item["coach"],
            item["seat_id"],
            item["stops_travelled"],
            item["amount_usd"],
            item["status"],
            item["booked_at"],
            item.get("travelled_at")
        )
        for item in data
    ]
    cnt = insert_many(cur, "bookings", columns, rows)
    print(f"  Seeded {cnt} national rail bookings")


def seed_metro_travels(cur):
    data = load("metro_travel_history.json")
    columns = [
        "trip_id",
        "user_id",
        "schedule_id",
        "origin_station_id",
        "destination_station_id",
        "travel_date",
        "ticket_type",
        "day_pass_ref",
        "stops_travelled",
        "amount_usd",
        "status",
        "purchased_at",
        "travelled_at"
    ]
    rows = [
        (
            item["trip_id"],
            item["user_id"],
            item["schedule_id"],
            item["origin_station_id"],
            item["destination_station_id"],
            item["travel_date"],
            item["ticket_type"],
            item.get("day_pass_ref"),
            item.get("stops_travelled"),
            item["amount_usd"],
            item["status"],
            item.get("purchased_at"),
            item.get("travelled_at")
        )
        for item in data
    ]
    cnt = insert_many(cur, "metro_travel_history", columns, rows)
    print(f"  Seeded {cnt} metro travels")


def seed_payments(cur):
    data = load("payments.json")
    columns = [
        "payment_id",
        "booking_id",
        "amount_usd",
        "method",
        "status",
        "paid_at"
    ]
    rows = [
        (
            item["payment_id"],
            item["booking_id"],
            item["amount_usd"],
            item["method"],
            item["status"],
            item["paid_at"]
        )
        for item in data
    ]
    cnt = insert_many(cur, "payments", columns, rows)
    print(f"  Seeded {cnt} payments")


def seed_feedback(cur):
    data = load("feedback.json")
    columns = [
        "feedback_id",
        "booking_id",
        "user_id",
        "rating",
        "comment",
        "submitted_at"
    ]
    rows = [
        (
            item["feedback_id"],
            item["booking_id"],
            item["user_id"],
            item["rating"],
            item.get("comment"),
            item["submitted_at"]
        )
        for item in data
    ]
    cnt = insert_many(cur, "feedback", columns, rows)
    print(f"  Seeded {cnt} feedback records")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL...")
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Seeding tables (dependency order):")
        seed_metro_stations(cur)
        seed_national_rail_stations(cur)
        seed_metro_schedules(cur)
        seed_national_rail_schedules(cur)
        seed_seat_layouts(cur)
        seed_users(cur)
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
