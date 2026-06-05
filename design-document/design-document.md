# TransitFlow — Database Design Document

> IM2002 Final Project | Group 41
> 蔡晟郁 · 黃謙儒 · 蔣耀德

---

# Section 1 — Entity-Relationship Diagram

> 負責人：蔡晟郁

## 1.1 ER Diagram

<!-- 插入 dbdiagram.io / draw.io 匯出的圖片 -->

## 1.2 Entity Overview

| Entity | PK | Key FKs | Representative Fields |
|--------|----|---------|-----------------------|
| `registered_users` | `user_id` | — | `email`, `password`, `is_active` |
| `metro_stations` | `station_id` | `interchange_nr_station_id → national_rail_stations` | `name`, `lines`, `zone` |
| `national_rail_stations` | `station_id` | `interchange_metro_station_id → metro_stations` | `name`, `managed_by` |
| `metro_schedules` | `schedule_id` | `origin_station_id`, `destination_station_id → metro_stations` | `line`, `stops_in_order`, `frequency_min` |
| `national_rail_schedules` | `schedule_id` | `origin_station_id`, `destination_station_id → national_rail_stations` | `line`, `service_type`, `std_base_fare_usd` |
| `seat_layouts` | `(schedule_id, seat_id)` | `schedule_id → national_rail_schedules` | `coach`, `row`, `column`, `fare_class` |
| `bookings` | `booking_id` | `user_id → registered_users`, `schedule_id → national_rail_schedules` | `travel_date`, `seat_id`, `status` |
| `metro_travel_history` | `trip_id` | `user_id → registered_users`, `schedule_id → metro_schedules` | `travel_date`, `amount_usd`, `status` |
| `payments` | `payment_id` | `booking_id → bookings` | `amount_usd`, `method`, `status` |
| `feedback` | `feedback_id` | `user_id → registered_users` | `rating`, `comment`, `submitted_at` |
| `policy_documents` | `id` | — | `title`, `category`, `content`, `embedding` |

---

# Section 2 — Normalisation Justification

> 負責人：蔡晟郁

## 2.1 Normalisation Decisions (3NF)

<!-- 說明 stops_in_order VARCHAR[] 的設計決策 -->
<!-- 說明是哪個 normal form、哪個 functional dependency 驅動了這個決定 -->

## 2.2 De-normalisation Trade-offs

<!-- 說明 available_seats 動態計算（不存欄位）的設計決策 -->
<!-- 或說明 stops_in_order 陣列取代 junction table 的理由 -->

## 2.3 Password Hashing

<!-- 說明 bcrypt 演算法、為何優於 MD5/SHA-1、cost factor、salt 如何防 rainbow table -->

---

# Section 3 — Graph Database Design Rationale

> 負責人：黃謙儒

## 3.1 Node / Relationship / Property 設計選擇

<!-- 說明什麼資料存成 node、relationship、property，各自說明設計理由 -->

## 3.2 Graph vs Relational 論證

<!-- 具體演算法論證：Dijkstra on graph vs SQL recursive CTE -->

## 3.3 查詢類型說明

<!-- 描述 shortest path + interchange path 兩種查詢，說明 graph model 如何使其得以表達 -->

## 3.4 Node Identity

<!-- station_id 作為 node identity 的理由 -->

---

# Section 4 — Vector / RAG Design

> 負責人：蔣耀德

## 4.1 Embedding 對象與 Cosine Similarity

<!-- 說明 policy documents embed 的內容，解釋 cosine similarity 的 magnitude-independent 特性 -->

## 4.2 RAG Pipeline

<!-- 完整描述：query embedding → similarity search → retrieved documents → LLM prompt → answer -->

## 4.3 Embedding Dimension 與 Provider 切換

<!-- 說明 Ollama: 768 / Gemini: 3072；切換 provider 後的 dimension mismatch 問題 -->

---

# Section 5 — AI Tool Usage Evidence

> 負責人：三人共同

> 要求：3–5 個範例，每個須包含 Context、Prompt、Outcome 三欄；至少一個描述 AI 給出錯誤輸出的案例

## Example 1 — Schema Design

**Context:**

**Prompt:**

**Outcome:**

---

## Example 2 — Query Implementation

**Context:**

**Prompt:**

**Outcome:**

---

## Example 3 — Debugging

**Context:**

**Prompt:**

**Outcome:**

---

## Example 4 — AI Output Was Wrong（必填）

**Context:**

**Prompt:**

**Outcome:**

---

## Example 5 — Graph / RAG Design

**Context:**

**Prompt:**

**Outcome:**

---

# Section 6 — Reflection & Trade-offs

> 負責人：三人共同

## 6.1 Design Decisions

### Decision 1：

<!-- 具體設計決策 + 清楚理由，不能只說「我們覺得比較好」 -->

### Decision 2：

<!-- 具體設計決策 + 清楚理由 -->

## 6.2 Production Considerations

<!-- 說明一個 production 系統中需要改變的地方及原因 -->
<!-- 例：connection pooling、schema migration、secret management、indexing strategy -->
