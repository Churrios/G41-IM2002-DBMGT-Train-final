"""
TransitFlow — 直接函式煙霧測試 (direct-call smoke test)
=========================================================
不經過 LLM，直接呼叫每一支 query/execute 函式，分離「程式正確性」與「LLM 行為」。
涵蓋：Graph 6 支 (C1–C6) + Relational 關鍵讀取 (B1–B8) + 寫入錯誤路徑 (B9/B10 安全測) + Task 6。

⚠️ 安全性：本腳本「不會」新增正式 booking / 不會改動既有資料。
   - execute_booking / execute_cancellation 只測「保證失敗」的錯誤路徑（回 (False, msg)，不寫資料）。
   - Task 6 會插入一筆 station_id='MS99-TEST' 的測試列，跑完自動 DELETE 清掉。

前提：
   1. Docker 已起且 healthy：  docker compose ps
   2. 已 seed：  python skeleton/seed_postgres.py  且  python skeleton/seed_neo4j.py
   3. venv 已啟動、.env 存在

跑法（專案根目錄）：
   python live-test/smoke_test_functions.py
"""

from __future__ import annotations

import os
import sys
import traceback

# Windows 主控台預設 cp950，印 emoji 會 UnicodeEncodeError；強制 stdout 走 UTF-8。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 把專案根目錄加進 sys.path（本檔在 live-test/ 下，往上一層）
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)

import psycopg2
import psycopg2.extras

from skeleton.config import PG_DSN
from databases.graph.queries import (
    query_shortest_route,
    query_cheapest_route,
    query_alternative_routes,
    query_interchange_path,
    query_delay_ripple,
    query_station_connections,
)
from databases.relational.queries import (
    query_national_rail_availability,
    query_national_rail_fare,
    query_metro_schedules,
    query_metro_fare,
    query_available_seats,
    query_user_profile,
    query_user_bookings,
    query_payment_info,
    execute_booking,
    execute_cancellation,
    log_delay_event,
    get_active_delays,
    resolve_delay,
)

# ── 迷你測試框架 ───────────────────────────────────────────────────────────────
_PASS = 0
_FAIL = 0
_FAILED_NAMES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  [PASS] {name}")
    else:
        _FAIL += 1
        _FAILED_NAMES.append(name)
        print(f"  [FAIL] {name}" + (f"  → {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def _pg():
    return psycopg2.connect(PG_DSN)


# ── 從 DB 動態取樣本 ID（避免硬編，較耐用）─────────────────────────────────────
def sample_ids() -> dict:
    ids: dict = {}
    with _pg() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT schedule_id FROM national_rail_schedules ORDER BY schedule_id LIMIT 1")
            r = cur.fetchone(); ids["nr_schedule"] = r["schedule_id"] if r else None

            cur.execute("SELECT schedule_id FROM metro_schedules ORDER BY schedule_id LIMIT 1")
            r = cur.fetchone(); ids["metro_schedule"] = r["schedule_id"] if r else None

            cur.execute("SELECT email FROM registered_users WHERE is_active = TRUE ORDER BY user_id LIMIT 1")
            r = cur.fetchone(); ids["email"] = r["email"] if r else None

            cur.execute("SELECT booking_id FROM bookings ORDER BY booking_id LIMIT 1")
            r = cur.fetchone(); ids["booking"] = r["booking_id"] if r else None

            # NR 班次的頭尾停靠站，保證 availability 查得到
            if ids.get("nr_schedule"):
                cur.execute(
                    "SELECT station_id FROM national_rail_schedule_stops "
                    "WHERE schedule_id = %s ORDER BY stop_order",
                    (ids["nr_schedule"],),
                )
                stops = [row["station_id"] for row in cur.fetchall()]
                ids["nr_origin"] = stops[0] if stops else None
                ids["nr_dest"] = stops[-1] if len(stops) > 1 else None
    return ids


# ── GRAPH (C1–C6) ─────────────────────────────────────────────────────────────
def test_graph() -> None:
    section("GRAPH C1 query_shortest_route")
    r = query_shortest_route("MS01", "MS09")
    check("C1 metro found", r.get("found") is True, str(r))
    check("C1 path 非空", len(r.get("path", [])) >= 2)
    check("C1 total_time_min 為數字", isinstance(r.get("total_time_min"), (int, float)))
    r2 = query_shortest_route("NR01", "NR05")
    check("C1 rail found", r2.get("found") is True, str(r2))
    r3 = query_shortest_route("MS01", "ZZ99")  # 不存在 → 不可 crash
    check("C1 不可達回 found=False（不 raise）", r3.get("found") is False)

    section("GRAPH C2 query_cheapest_route（fare_class 要真的改變成本）")
    std = query_cheapest_route("NR01", "NR05", fare_class="standard")
    fst = query_cheapest_route("NR01", "NR05", fare_class="first")
    check("C2 standard found", std.get("found") is True, str(std))
    check("C2 first found", fst.get("found") is True, str(fst))
    if std.get("found") and fst.get("found"):
        check(
            "C2 first 票價 > standard（fare_class 有作用）",
            (fst["total_fare_usd"] or 0) > (std["total_fare_usd"] or 0),
            f"std={std.get('total_fare_usd')} first={fst.get('total_fare_usd')}",
        )

    section("GRAPH C3 query_alternative_routes（避開站 + legs）")
    routes = query_alternative_routes("MS01", "MS09", "MS07", max_routes=3)
    check("C3 回傳 list", isinstance(routes, list))
    check("C3 至少 1 條", len(routes) >= 1, f"got {len(routes)}")
    check("C3 數量 <= max_routes", len(routes) <= 3)
    avoided_ok = all(
        all(s["station_id"] != "MS07" for s in r["route"]) for r in routes
    )
    check("C3 沒有任何路線經過被避開的 MS07", avoided_ok)
    legs_ok = all("legs" in r and len(r["legs"]) == len(r["route"]) - 1 for r in routes)
    check("C3 每條路線都有 legs 且數量 = 站數-1", legs_ok)

    section("GRAPH C4 query_interchange_path（跨網 + INTERCHANGE_TO）")
    ip = query_interchange_path("MS01", "NR05")
    check("C4 found", ip.get("found") is True, str(ip))
    check("C4 有 interchange_points", len(ip.get("interchange_points", [])) >= 1)
    has_metro = any(s["station_id"].startswith("MS") for s in ip.get("path", []))
    has_rail = any(s["station_id"].startswith("NR") for s in ip.get("path", []))
    check("C4 路徑同時含兩網節點", has_metro and has_rail)

    section("GRAPH C5 query_delay_ripple（hops=0 只回起點）")
    z = query_delay_ripple("MS01", hops=0)
    check("C5 hops=0 只回 1 筆（起點本身）", len(z) == 1 and z[0]["hops_away"] == 0, str(z))
    two = query_delay_ripple("MS01", hops=2)
    check("C5 hops=2 回多筆", len(two) > 1, f"got {len(two)}")
    check("C5 每筆都有 hops_away", all("hops_away" in d for d in two))

    section("GRAPH C6 query_station_connections")
    conns = query_station_connections("MS01")
    check("C6 回傳 dict 含 station_id 與 connections", isinstance(conns, dict) and "station_id" in conns and "connections" in conns, str(conns))
    check("C6 station_id 正確為起點", conns.get("station_id") == "MS01", str(conns.get("station_id")))
    check("C6 connections 非空", len(conns.get("connections", [])) >= 1, str(conns))
    check("C6 每個鄰站有 travel_time_min", all("travel_time_min" in c for c in conns.get("connections", [])))


# ── RELATIONAL (B1–B8 讀取) ───────────────────────────────────────────────────
def test_relational(ids: dict) -> None:
    section("RELATIONAL B1 query_national_rail_availability")
    if ids.get("nr_origin") and ids.get("nr_dest"):
        av = query_national_rail_availability(ids["nr_origin"], ids["nr_dest"])
        check("B1 回傳 list（不 raise）", isinstance(av, list), str(av)[:200])
        check("B1 至少 1 筆班次", len(av) >= 1, f"{ids['nr_origin']}→{ids['nr_dest']} got {len(av)}")
        if av:
            check("B1 含 available_seats 欄位", "available_seats" in av[0])
    empty = query_national_rail_availability("NR01", "NR01")  # 同站 → 應為空 list 非 None
    check("B1 無服務時回 [] 非 None", empty == [], str(empty))

    section("RELATIONAL B3 query_national_rail_fare（標準 vs 頭等）")
    if ids.get("nr_schedule"):
        sid = ids["nr_schedule"]
        std = query_national_rail_fare(sid, "standard", 3)
        fst = query_national_rail_fare(sid, "first", 3)
        check("B3 standard 三個 key 齊全",
              std and {"base_fare_usd", "per_stop_rate_usd", "total_fare_usd"} <= set(std), str(std))
        check("B3 數值為數字非字串", std and isinstance(std["total_fare_usd"], (int, float)))
        check("B3 算術正確 total = base + rate*stops",
              std and abs(std["total_fare_usd"] - (std["base_fare_usd"] + std["per_stop_rate_usd"] * 3)) < 0.01)
        check("B3 first 的 per_stop_rate 與 standard 不同",
              std and fst and fst["per_stop_rate_usd"] != std["per_stop_rate_usd"],
              f"std={std} first={fst}")
        # 型別防呆：字串 stops 不可 crash（先前抓到的 bug）
        try:
            s_str = query_national_rail_fare(sid, "standard", "4")
            check("B3 stops 傳字串 '4' 不 crash", s_str is not None and "total_fare_usd" in s_str)
        except Exception as e:
            check("B3 stops 傳字串 '4' 不 crash", False, f"crashed: {e}")

    section("RELATIONAL B4 query_metro_fare")
    if ids.get("metro_schedule"):
        mf = query_metro_fare(ids["metro_schedule"], 3)
        check("B4 三個 key 齊全",
              mf and {"base_fare_usd", "per_stop_rate_usd", "total_fare_usd"} <= set(mf), str(mf))

    section("RELATIONAL B2 query_metro_schedules")
    if ids.get("metro_schedule"):
        # 用該班次頭尾兩站
        with _pg() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT station_id FROM metro_schedule_stops WHERE schedule_id=%s ORDER BY stop_order",
                    (ids["metro_schedule"],),
                )
                ms = [row[0] for row in cur.fetchall()]
        if len(ms) >= 2:
            scheds = query_metro_schedules(ms[0], ms[-1])
            check("B2 回傳 list 且至少 1 筆", isinstance(scheds, list) and len(scheds) >= 1, str(scheds)[:200])

    section("RELATIONAL B5 query_available_seats")
    if ids.get("nr_schedule"):
        seats = query_available_seats(ids["nr_schedule"], "2025-06-01", "standard")
        check("B5 回傳 list（不 raise）", isinstance(seats, list), str(seats)[:200])

    section("RELATIONAL B6 query_user_profile")
    if ids.get("email"):
        prof = query_user_profile(ids["email"])
        check("B6 已知 email 回 dict", isinstance(prof, dict), str(prof))
        check("B6 含 year_of_birth", prof and "year_of_birth" in prof)
    none_prof = query_user_profile("definitely-not-a-user@nowhere.test")
    check("B6 未知 email 回 None 非 raise", none_prof is None)

    section("RELATIONAL B7 query_user_bookings")
    if ids.get("email"):
        ub = query_user_bookings(ids["email"])
        check("B7 兩個 key 都在", isinstance(ub, dict) and "national_rail" in ub and "metro" in ub, str(ub)[:200])
    ub2 = query_user_bookings("definitely-not-a-user@nowhere.test")
    check("B7 未知 user 回 {national_rail:[],metro:[]}", ub2 == {"national_rail": [], "metro": []})

    section("RELATIONAL B8 query_payment_info")
    if ids.get("booking"):
        pay = query_payment_info(ids["booking"])
        check("B8 已知 booking 回 dict 或 None（不 raise）", pay is None or isinstance(pay, dict))
    check("B8 未知 booking 回 None", query_payment_info("NOPE-NOPE") is None)


# ── 寫入錯誤路徑（安全：不寫正式資料）───────────────────────────────────────────
def test_write_error_paths() -> None:
    section("RELATIONAL B9/B10 寫入錯誤路徑（不會新增資料）")
    ok, msg = execute_booking(
        user_id="RU_NOEXIST", schedule_id="NR_SCH_NOEXIST",
        origin_station_id="NR01", destination_station_id="NR05",
        travel_date="2025-06-01", fare_class="standard", seat_id="any",
    )
    check("B9 不存在班次回 (False, msg) 而非 raise", ok is False and isinstance(msg, str), f"{ok},{msg}")

    ok2, msg2 = execute_cancellation(booking_id="NOPE-NOPE", user_id="RU_NOEXIST")
    check("B10 不存在 booking 回 (False, msg)", ok2 is False and isinstance(msg2, str), f"{ok2},{msg2}")


# ── TASK 6（插一筆測試列，跑完清掉）─────────────────────────────────────────────
def test_task6() -> None:
    section("TASK 6 delay events（log → get → resolve → cleanup）")
    TEST_SID = "MS99-TEST"
    # 先清掉殘留
    with _pg() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM delay_events WHERE station_id = %s", (TEST_SID,))
        conn.commit()

    eid = log_delay_event(TEST_SID, "low", "smoke-test delay (safe to delete)")
    check("T6 log_delay_event 回 int event_id", isinstance(eid, int), str(eid))

    active = get_active_delays(TEST_SID)
    check("T6 get_active_delays 找得到剛插入的", any(d["event_id"] == eid for d in active), str(active))

    resolved = resolve_delay(eid)
    check("T6 resolve_delay 回 True", resolved is True)

    active2 = get_active_delays(TEST_SID)
    check("T6 resolve 後不再 active", all(d["event_id"] != eid for d in active2))

    resolved_again = resolve_delay(eid)
    check("T6 重複 resolve 回 False（不 raise）", resolved_again is False)

    # 清理測試列
    with _pg() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM delay_events WHERE station_id = %s", (TEST_SID,))
        conn.commit()
    print("  (已清除 MS99-TEST 測試列)")


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    print("TransitFlow 直接函式煙霧測試")
    print("=" * 60)
    try:
        ids = sample_ids()
    except Exception as e:
        print(f"\n❌ 無法連上 PostgreSQL 或抓樣本 ID：{e}")
        print("   檢查：docker compose ps（postgres healthy？）/ 是否已 seed / .env 的 PG_PORT")
        traceback.print_exc()
        return 2

    print(f"取樣 ID：{ids}")

    test_graph()
    test_relational(ids)
    test_write_error_paths()
    test_task6()

    print("\n" + "=" * 60)
    print(f"結果：{_PASS} PASS / {_FAIL} FAIL")
    if _FAIL:
        print("失敗項目：")
        for n in _FAILED_NAMES:
            print(f"   - {n}")
        print("\n→ 把上面 [FAIL] 那幾行整段貼回來即可。")
        return 1
    print("✅ 全數通過。graph + relational + Task 6 在直接呼叫層級皆正確。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
