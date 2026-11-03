# Project Coding Rules (Non-Obvious Only)

- New backend capability = one FastAPI route in `booking_system_backend/server.py` (placed above the `FastApiMCP(app)` line). The MCP tool is generated automatically; never write a separate MCP tool.
- Service functions in `booking_system_backend/services/` must return `Out | ErrorResponse` (never raise) and the route must translate `error_code` to an HTTP status.
- Never use `str(exception)` in client-facing errors in new code (security rule); log server-side and return a generic message. Existing Java proxy routes in `server.py` do the opposite; don't copy that.
- Cross-service payloads: Java <-> Python use camelCase keys for hold -> booking (`travelerId`, `travelerName`, `flightId`, `seatClass`). Changing either side requires updating `PythonBackendClient.java`, `/internal/bookings/from-hold`, and `e2e/test_holds.py`.
- Backend tests must be run from `booking_system_backend/`; e2e tests must not assume seed counts (see `e2e/helpers.py::find_flight_with_seats`).
- Frontend: put API calls in `src/services/api.ts`, types in `src/types/index.ts`; treat HTTP 200 bodies containing `error` as failures for quote/hold endpoints.
