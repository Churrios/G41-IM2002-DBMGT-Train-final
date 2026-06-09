# Task 6 Extension: Delay Event Logging

This extension implements a real-time delay event logging system that allows users to report station disruptions and query active delays via the chatbot. It naturally complements the graph database's delay ripple analysis.

## Modified Files & Added Components

- **`databases/relational/schema.sql`**
  - Added table: `delay_events`
  - Added index: `idx_delay_events_active`
- **`databases/relational/queries.py`**
  - Added function: `log_delay_event(station_id, severity, description)`
  - Added function: `get_active_delays(station_id)`
  - Added function: `resolve_delay(event_id)`
- **`skeleton/seed_postgres.py`**
  - Added function/logic: Seed sample delay events with various severities.
- **`skeleton/agent.py`**
  - Added tools: `report_delay` and `get_active_delays`
  - Handled in `_execute_tool()`

*Note: All modified files contain the `# TASK 6 EXTENSION:` comment near the top or the modified sections.*
