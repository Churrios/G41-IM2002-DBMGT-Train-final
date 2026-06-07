# Section 1 — Entity-Relationship Diagram

> 負責人：蔡晟郁 | 配分：/25

## 1.1 ER Diagram

![ER Diagram](er-diagram.png)

[ER Diagram (PDF)](er-diagram.pdf)

### dbdiagram.io DSL（貼入工具後匯出圖片）

```
Table registered_users {
  user_id varchar(10) [pk]
  full_name text [not null]
  email varchar(200) [not null, unique]
  password text [not null]
  phone varchar(20)
  date_of_birth date
  secret_question text
  secret_answer text
  registered_at timestamptz
  is_active boolean [not null, default: true]
}

Table metro_stations {
  station_id varchar(10) [pk]
  name text [not null]
  lines varchar(10)[]
  is_interchange_metro boolean
  is_interchange_national_rail boolean
  interchange_nr_station_id varchar(10) [ref: > national_rail_stations.station_id]
}

Table national_rail_stations {
  station_id varchar(10) [pk]
  name text [not null]
  lines varchar(10)[]
  is_interchange_national_rail boolean
  is_interchange_metro boolean
  interchange_metro_station_id varchar(10) [ref: > metro_stations.station_id]
}

Table metro_schedules {
  schedule_id varchar(20) [pk]
  line varchar(5) [not null]
  direction varchar(15) [not null]
  origin_station_id varchar(10) [not null, ref: > metro_stations.station_id]
  destination_station_id varchar(10) [not null, ref: > metro_stations.station_id]
  travel_time_from_origin jsonb [not null]
  first_train_time time [not null]
  last_train_time time [not null]
  frequency_min int [not null]
  base_fare_usd numeric(6,2) [not null]
  per_stop_rate_usd numeric(6,2) [not null]
}

Table metro_schedule_stops {
  schedule_id varchar(20) [not null, ref: > metro_schedules.schedule_id]
  stop_order int [not null]
  station_id varchar(10) [not null, ref: > metro_stations.station_id]

  indexes {
    (schedule_id, stop_order) [pk]
  }
}

Table national_rail_schedules {
  schedule_id varchar(20) [pk]
  line varchar(10) [not null]
  service_type varchar(10) [not null]
  direction varchar(15) [not null]
  origin_station_id varchar(10) [not null, ref: > national_rail_stations.station_id]
  destination_station_id varchar(10) [not null, ref: > national_rail_stations.station_id]
  travel_time_from_origin jsonb [not null]
  first_train_time time [not null]
  last_train_time time [not null]
  frequency_min int [not null]
  std_base_fare_usd numeric(6,2) [not null]
  first_base_fare_usd numeric(6,2) [not null]
}

Table national_rail_schedule_stops {
  schedule_id varchar(20) [not null, ref: > national_rail_schedules.schedule_id]
  stop_order int [not null]
  station_id varchar(10) [not null, ref: > national_rail_stations.station_id]

  indexes {
    (schedule_id, stop_order) [pk]
  }
}

Table seat_layouts {
  schedule_id varchar(20) [not null, ref: > national_rail_schedules.schedule_id]
  seat_id varchar(10) [not null]
  coach varchar(5) [not null]
  row_num int [not null]
  col_char varchar(5) [not null]
  fare_class varchar(10) [not null]

  indexes {
    (schedule_id, seat_id) [pk]
  }
}

Table bookings {
  booking_id varchar(20) [pk]
  user_id varchar(10) [not null, ref: > registered_users.user_id]
  schedule_id varchar(20) [not null, ref: > national_rail_schedules.schedule_id]
  origin_station_id varchar(10) [not null, ref: > national_rail_stations.station_id]
  destination_station_id varchar(10) [not null, ref: > national_rail_stations.station_id]
  travel_date date [not null]
  fare_class varchar(10) [not null]
  seat_id varchar(10) [not null]
  amount_usd numeric(8,2) [not null]
  status varchar(15) [not null]
  booked_at timestamptz
}

Table metro_travel_history {
  trip_id varchar(20) [pk]
  user_id varchar(10) [not null, ref: > registered_users.user_id]
  schedule_id varchar(20) [not null, ref: > metro_schedules.schedule_id]
  origin_station_id varchar(10) [not null, ref: > metro_stations.station_id]
  destination_station_id varchar(10) [not null, ref: > metro_stations.station_id]
  travel_date date [not null]
  amount_usd numeric(8,2) [not null]
  status varchar(15) [not null]
}

// payments.booking_id has no FK: references BK... (national rail bookings)
// or MT... (metro travel history) — intentional dual-reference design
Table payments {
  payment_id varchar(20) [pk]
  booking_id varchar(20) [not null]
  amount_usd numeric(8,2) [not null]
  method varchar(20) [not null]
  status varchar(15) [not null]
  paid_at timestamptz
}

Table feedback {
  feedback_id varchar(20) [pk]
  user_id varchar(10) [ref: > registered_users.user_id]
  rating int [not null]
  comment text
  submitted_at timestamptz
}

Table policy_documents {
  id serial [pk]
  title text [not null]
  category varchar(50)
  content text [not null]
  embedding vector(768)
}
```

---

## 1.2 Entity 說明

| Entity | PK | 主要 FK | 代表性欄位 |
|--------|-----|---------|-----------|
| `registered_users` | `user_id` | — | `email`, `password` (bcrypt), `is_active` |
| `metro_stations` | `station_id` | `interchange_nr_station_id → national_rail_stations` | `name`, `lines[]`, `is_interchange_national_rail` |
| `national_rail_stations` | `station_id` | `interchange_metro_station_id → metro_stations` | `name`, `lines[]`, `is_interchange_metro` |
| `metro_schedules` | `schedule_id` | `origin_station_id`, `destination_station_id → metro_stations` | `line`, `frequency_min`, `base_fare_usd` |
| `metro_schedule_stops` | `(schedule_id, stop_order)` | `schedule_id → metro_schedules`, `station_id → metro_stations` | `stop_order` |
| `national_rail_schedules` | `schedule_id` | `origin_station_id`, `destination_station_id → national_rail_stations` | `service_type`, `std_base_fare_usd`, `first_base_fare_usd` |
| `national_rail_schedule_stops` | `(schedule_id, stop_order)` | `schedule_id → national_rail_schedules`, `station_id → national_rail_stations` | `stop_order` |
| `seat_layouts` | `(schedule_id, seat_id)` | `schedule_id → national_rail_schedules` | `coach`, `fare_class` |
| `bookings` | `booking_id` | `user_id → registered_users`, `schedule_id → national_rail_schedules`, `origin/destination → national_rail_stations` | `travel_date`, `fare_class`, `status` |
| `metro_travel_history` | `trip_id` | `user_id → registered_users`, `schedule_id → metro_schedules`, `origin/destination → metro_stations` | `travel_date`, `amount_usd`, `status` |
| `payments` | `payment_id` | `booking_id`（無 FK：雙參照 BK.../MT...） | `amount_usd`, `method`, `status` |
| `feedback` | `feedback_id` | `user_id → registered_users` | `rating`, `comment` |
| `policy_documents` | `id` | — | `title`, `category`, `embedding` (768d vector) |
