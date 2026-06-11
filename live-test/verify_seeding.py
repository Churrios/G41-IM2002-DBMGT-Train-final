"""
TransitFlow — Seeding 驗證 (Live Section A 自我檢查)
====================================================
檢查 PostgreSQL 各表與 Neo4j 各 label/relationship 的筆數，對應評分 Live Section A /15。
不改任何資料，只讀 count。

跑法（專案根目錄，Docker 已起且已 seed）：
   python live-test/verify_seeding.py
"""

from __future__ import annotations

import os
import sys

# Windows 主控台預設 cp950，印 emoji 會 UnicodeEncodeError；強制 stdout 走 UTF-8。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)

import psycopg2
from neo4j import GraphDatabase

from skeleton.config import PG_DSN, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# PostgreSQL：表名 → 是否「必須 > 0」（policy_documents 視 provider 而定，仍要求 > 0）
_PG_TABLES = [
    ("registered_users", True),
    ("metro_stations", True),
    ("national_rail_stations", True),
    ("metro_schedules", True),
    ("metro_schedule_stops", True),
    ("national_rail_schedules", True),
    ("national_rail_schedule_stops", True),
    ("seat_layouts", True),
    ("bookings", True),
    ("metro_travel_history", True),
    ("payments", True),
    ("feedback", True),
    ("delay_events", True),          # Task 6
    ("policy_documents", True),      # 向量 / RAG（Live A 要求 > 0）
]

# Neo4j：預期值（依 design-document §3：20 MetroStation + 10 NationalRailStation，
# 66 邊 = 42 METRO_LINK + 18 RAIL_LINK + 6 INTERCHANGE_TO）。
# 對不上不一定是錯（資料可能更新），只是提醒比對。
_NEO_EXPECT = {
    "MetroStation": 20,
    "NationalRailStation": 10,
    "METRO_LINK": 42,
    "RAIL_LINK": 18,
    "INTERCHANGE_TO": 6,
}

_problems: list[str] = []


def check_postgres() -> None:
    print("\n=== PostgreSQL 表筆數 ===")
    try:
        with psycopg2.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                for table, must_have in _PG_TABLES:
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {table}")
                        n = cur.fetchone()[0]
                    except Exception as e:
                        conn.rollback()
                        print(f"  ❌ {table:<32} 查詢失敗：{e}")
                        _problems.append(f"PG 表 {table} 不存在或查詢失敗")
                        continue
                    flag = "✅" if (n > 0 or not must_have) else "❌"
                    if must_have and n == 0:
                        _problems.append(f"PG 表 {table} 是空的（Live A 要求有資料）")
                    print(f"  {flag} {table:<32} {n}")
    except Exception as e:
        print(f"  ❌ 連不上 PostgreSQL：{e}")
        print("     檢查 docker compose ps（postgres healthy？）與 .env 的 PG_PORT（應為 5433）")
        _problems.append("PostgreSQL 連線失敗")


def check_neo4j() -> None:
    print("\n=== Neo4j 節點 / 關係筆數 ===")
    try:
        with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
            with driver.session() as session:
                for label in ("MetroStation", "NationalRailStation"):
                    n = session.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"]
                    exp = _NEO_EXPECT[label]
                    flag = "✅" if n > 0 else "❌"
                    note = "" if n == exp else f"(預期 {exp})"
                    if n == 0:
                        _problems.append(f"Neo4j label {label} 沒有節點")
                    print(f"  {flag} (:{label}){'':<22} {n} {note}")
                for rel in ("METRO_LINK", "RAIL_LINK", "INTERCHANGE_TO"):
                    n = session.run(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c").single()["c"]
                    exp = _NEO_EXPECT[rel]
                    flag = "✅" if n > 0 else "❌"
                    note = "" if n == exp else f"(預期 {exp})"
                    if n == 0:
                        _problems.append(f"Neo4j 關係 {rel} 沒有邊")
                    print(f"  {flag} -[:{rel}]->{'':<20} {n} {note}")
    except Exception as e:
        print(f"  ❌ 連不上 Neo4j：{e}")
        print("     檢查 docker compose ps（neo4j healthy？）與 .env 的 NEO4J_URI（應為 bolt://localhost:7688）")
        _problems.append("Neo4j 連線失敗")


def main() -> int:
    print("TransitFlow Seeding 驗證（Live Section A）")
    print("=" * 60)
    check_postgres()
    check_neo4j()
    print("\n" + "=" * 60)
    if _problems:
        print("⚠️  發現問題：")
        for p in _problems:
            print(f"   - {p}")
        print("\n→ 多半是『沒 seed』或『provider/維度不符導致 vector seed 失敗』。")
        print("   先跑：python skeleton/seed_postgres.py  與  python skeleton/seed_neo4j.py")
        print("   policy_documents 為 0 → 跑：python skeleton/seed_vectors.py（注意 768 vs 3072 維度）")
        return 1
    print("✅ 所有表 / 節點 / 關係都有資料。Live Section A 自我檢查通過。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
