# D1 交付：新 Graph Schema 文字（給蔡晟郁更新 AI_SESSION_CONTEXT.md）

> 用途：取代 [AI_SESSION_CONTEXT.md](../AI_SESSION_CONTEXT.md) 過時的 graph schema。
> 對齊對象：已進 main 的 `databases/graph/queries.py`、`skeleton/seed_neo4j.py`、`databases/graph/seed.cypher`。
> 操作：
> 1. 用下方【EN — 貼進 AI_SESSION_CONTEXT.md】整段，**取代原檔第 231–278 行**「## Agreed Graph Schema」整節。
> 2. 用【Changelog 行】**取代原檔第 329 行**那條過時的 changelog。
> 3. （AI_SESSION_CONTEXT.md 主體是英文，英文版是主要貼上對象；中文版附在最後供報告/口頭說明用。）

實際拓撲統計（由 JSON 實算）：**30 nodes**（20 MetroStation + 10 NationalRailStation）、**66 edges**（42 METRO_LINK + 18 RAIL_LINK + 6 INTERCHANGE_TO）。
> 註：METRO_LINK/RAIL_LINK 數字為 adjacency 條目數，MERGE 以 `(from, to, line)` 去重後可能略少。

---

## 【EN — 貼進 AI_SESSION_CONTEXT.md（取代第 231–278 行整節）】

```markdown
## Agreed Graph Schema

> **Status: CONFIRMED 2026-06-04 — Q1=A adopted (split-label model, aligned with grading standard).**
> Q1 split labels MetroStation / NationalRailStation ✓ | Q2 METRO_LINK / RAIL_LINK ✓ | Q3 INTERCHANGE_TO (bidirectional) ✓ | Q5 fare stored on edges ✓

\```
Node labels:
  MetroStation
    Properties:
      station_id                    String   (e.g. "MS01")        -- node identity / unique constraint
      name                          String   (e.g. "Central Square")
      lines                         List<String>  (e.g. ["M1", "M2"])
      is_interchange_national_rail  Boolean  (true if it transfers to a rail station)

  NationalRailStation
    Properties:
      station_id                    String   (e.g. "NR01")        -- node identity / unique constraint
      name                          String   (e.g. "Central Station")
      lines                         List<String>  (e.g. ["NR1", "NR2"])
      is_interchange_metro          Boolean
      interchange_metro_station_id  String   (the MetroStation it transfers to, or null)

  (Split into MetroStation / NationalRailStation rather than one Station label,
   to match the grading standard which checks for both labels explicitly.)

Relationship types:
  METRO_LINK   (MetroStation)-[:METRO_LINK]->(MetroStation)
    Properties:
      line              String
      travel_time_min   Integer
      fare_usd          Float    -- round(1.0 + 0.5 * travel_time_min, 2); metro is single-tier (no fare_class)

  RAIL_LINK    (NationalRailStation)-[:RAIL_LINK]->(NationalRailStation)
    Properties:
      line                String
      travel_time_min     Integer
      fare_standard_usd   Float  -- round(2.0 + 1.2 * travel_time_min, 2)
      fare_first_usd      Float  -- round(2.0 + 2.0 * travel_time_min, 2)

  INTERCHANGE_TO  (MetroStation)-[:INTERCHANGE_TO]-(NationalRailStation)
    Properties:
      transfer_time_min   Integer  -- fixed 5 (spec does not mandate; professor confirmed a sensible custom value is OK)
    Note: seeded as TWO directed edges (metro->rail and rail->metro) so Dijkstra
          can traverse either direction; queries match it undirected: -[:INTERCHANGE_TO]-.
\```

### Design rationale

| Decision | Choice | Reason |
|---|---|---|
| Split `MetroStation` / `NationalRailStation` | ✓ | Matches grading standard (Task 4 / Live A check both labels by name) |
| `METRO_LINK` / `RAIL_LINK` separate types | ✓ | Lets each network carry its own fare model on the edge; route queries can restrict to `'METRO_LINK\|RAIL_LINK'` and stay same-network |
| Fare stored on edges at seed time (Q5=A) | ✓ | `apoc.algo.dijkstra` can use a fare property directly as weight, so fare_class genuinely changes the chosen path (Live C2), not just the final total |
| `INTERCHANGE_TO` bidirectional, `transfer_time_min=5` | ✓ | Only `query_interchange_path` follows it (cross-network); excluded from shortest/cheapest so same-network routing returns found=False when unreachable |
| `station_id` as node identity | ✓ | Unique constraint per label; stable external key from the source JSON |

Topology: 30 nodes (20 MetroStation + 10 NationalRailStation),
66 edges (42 METRO_LINK + 18 RAIL_LINK + 6 INTERCHANGE_TO).
```

---

## 【Changelog 行 — 取代原檔第 329 行】

```markdown
- [x] **2026-06-04** Graph schema migrated to split-label model (Q1=A): `MetroStation` / `NationalRailStation`, `METRO_LINK {line, travel_time_min, fare_usd}` / `RAIL_LINK {line, travel_time_min, fare_standard_usd, fare_first_usd}`, `INTERCHANGE_TO {transfer_time_min:5}` (bidirectional). Stats: 30 nodes (20 metro + 10 NR), 66 edges (42 METRO_LINK + 18 RAIL_LINK + 6 INTERCHANGE_TO). Supersedes the 2026-05-28 single-Station design.
```

---

## 【ZH — 中文版（供 Design Doc Section 3 / 口頭說明用，不一定要貼進英文契約檔）】

### 已定案 Graph Schema（2026-06-04，採 Q1=A 分離標籤模型）

**節點標籤**

- **MetroStation**（捷運站）
  - `station_id` String（如 "MS01"）—— 節點唯一識別、加 unique constraint
  - `name` String
  - `lines` List<String>（如 ["M1","M2"]）
  - `is_interchange_national_rail` Boolean（是否可換乘國鐵）
- **NationalRailStation**（國鐵站）
  - `station_id` String（如 "NR01"）—— 節點唯一識別、加 unique constraint
  - `name` String
  - `lines` List<String>（如 ["NR1","NR2"]）
  - `is_interchange_metro` Boolean
  - `interchange_metro_station_id` String（對應的捷運站，或 null）

> 採分離標籤（而非單一 `Station`）是為對齊評分標準——Task 4 / Live A 會明文檢查兩種 label 是否存在。

**關係類型**

- **METRO_LINK** `(MetroStation)-[:METRO_LINK]->(MetroStation)`
  - `line` String、`travel_time_min` Integer
  - `fare_usd` Float = `round(1.0 + 0.5 × travel_time_min, 2)`（捷運單一票價，無 fare_class 之分）
- **RAIL_LINK** `(NationalRailStation)-[:RAIL_LINK]->(NationalRailStation)`
  - `line` String、`travel_time_min` Integer
  - `fare_standard_usd` Float = `round(2.0 + 1.2 × travel_time_min, 2)`
  - `fare_first_usd` Float = `round(2.0 + 2.0 × travel_time_min, 2)`
- **INTERCHANGE_TO** `(MetroStation)-[:INTERCHANGE_TO]-(NationalRailStation)`
  - `transfer_time_min` Integer = 固定 5（規格未強制，教授確認可自訂合理值）
  - seeding 建**雙向兩條** directed edge，查詢用**無向** `-[:INTERCHANGE_TO]-`

**設計理由**

| 決策 | 選擇 | 理由 |
|------|------|------|
| 分離 MetroStation / NationalRailStation | ✓ | 對齊評分標準（Task 4 / Live A 以 label 名稱檢查） |
| METRO_LINK / RAIL_LINK 分開 | ✓ | 各自把票價模型掛在邊上；路徑查詢可限定 `'METRO_LINK\|RAIL_LINK'` 維持同網 |
| 票價在 seeding 時寫進邊（Q5=A） | ✓ | `apoc.algo.dijkstra` 直接用票價屬性當權重 → fare_class 會真正改變選到的路徑（Live C2），而非只改最後總額 |
| INTERCHANGE_TO 雙向、transfer_time_min=5 | ✓ | 只有 `query_interchange_path` 會走它（跨網）；shortest/cheapest 刻意不含它，使同網不可達時回 found=False |
| 以 station_id 作節點識別 | ✓ | 每個 label 一條 unique constraint；來源 JSON 的穩定外部鍵 |

**拓撲統計**：30 節點（20 MetroStation + 10 NationalRailStation）、66 邊（42 METRO_LINK + 18 RAIL_LINK + 6 INTERCHANGE_TO）。