# Project Architecture Rules (Non-Obvious Only)

- Quote -> hold -> booking flow crosses all services: Frontend -> Python proxy (`/quotes`, `/holds/*`) -> Java `/api/v1/*` -> on confirm Java calls Python `/internal/bookings/from-hold`. Python holds no hold state; Java owns holds in its own SQLite DB (`holds.db`), and a scheduler expires them every 60s (`hold.duration.minutes=15`).
- Seat inventory is only decremented in Python at booking creation; holds do not decrement Python seat counters.
- MCP surface is derived from the REST routes, so any route added (including `/internal/*` and proxy routes) is also exposed to AI agents. Consider that when adding routes.
- Frontend stores active holds client-side in localStorage (`galaxium_holds_<userId>`); there is no server endpoint to list a user's holds.
- Two databases per environment: Python (SQLite locally, PostgreSQL via docker compose/cloud) and Java (SQLite always; H2 in tests).
- Deployment: Docker Compose (`docker-compose.yml`, hold service behind `--profile hold-service`), AWS ECS via `scripts/terraform`, IBM Code Engine via `scripts/ibm`.
