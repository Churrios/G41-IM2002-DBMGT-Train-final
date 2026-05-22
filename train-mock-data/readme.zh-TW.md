# Train Ticket Booking System — Mock Data

這個 dataset 建模了一個虛構的大眾運輸系統，包含兩個網路：**city metro** 與 **national rail** 服務。它的用途是資料庫設計與建模練習。

## Networks

**City Metro** — 一個都市運輸網路，包含 4 條路線與 20 個車站。車票在旅行當天購買，不涉及 advance booking 或 seat assignment。有些車站是 metro lines 之間，或 metro 與 national rail 之間的 interchange points。

**National Rail** — 一個城際運輸網路，包含 2 條路線與 10 個車站。車票可以提前預訂，並包含 seat assignment。每條路線都有兩種 service types。票價會依 fare class 與 journey length 而不同。

## Data Domains

**Infrastructure** — 實體車站，以及兩個網路中在它們之間運行的 scheduled services。

**Users** — 可以進行 bookings 與 purchases 的 registered passengers。

**Transactions** — 乘客與系統互動的方式在兩個網路之間不同。National rail 涉及含 seat reservations 的 advance bookings；metro travel 則記錄為 same-day tap-in trips。所有 transactions 都會關聯到一筆 payment record。乘客可以在旅行後留下 feedback。

**Policies and Rules** — 涵蓋兩個網路的 ticket types、refund eligibility、booking rules 與 passenger conduct policies 的文件。

## Files

| File | Description |
|---|---|
| `metro_stations.json` | Metro station data |
| `national_rail_stations.json` | National rail station data |
| `metro_schedules.json` | Metro line schedules and fare structure |
| `national_rail_schedules.json` | National rail schedules and fare structure |
| `national_rail_seat_layouts.json` | National rail 的 coach 與 seat layout templates |
| `registered_users.json` | Registered passenger accounts |
| `bookings.json` | National rail advance bookings |
| `metro_travel_history.json` | Metro tap-in travel records |
| `payments.json` | 所有 transactions 的 payment records |
| `feedback.json` | Post-travel ratings and comments |
| `ticket_types.json` | Ticket type definitions and rules |
| `refund_policy.json` | 依 network、ticket type 與 cancellation window 區分的 refund eligibility |
| `booking_rules.json` | Booking and modification rules |
| `travel_policies.json` | Passenger conduct and luggage policies |
