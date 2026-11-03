# AGENTS.md

This file provides guidance to agents when working with code in this repository.

Three services: Python/FastAPI backend (`:8001`), Java/Spring hold service (`:8080`), React/Vite frontend (`:5173`). Each is run from its own directory; there is no root build.

## Commands

- Backend tests (MUST run from `booking_system_backend/`; `conftest.py` and `testpaths = tests` depend on it):
  - All: `pytest` — single test: `pytest tests/test_rest.py::TestBookEndpoint::test_name` (tests are grouped in `Test*` classes) or `-k name`
  - A pre-existing `.venv` (gitignored) may have been built in Docker (shebangs point to `/app/...`) and be unusable on the host (check `.venv/bin/pytest`); if so recreate it: `rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`. `e2e/run-native.sh` and `start_locally.sh` rely on `.venv/bin/python`.
  - No Python linter: do not install or run ruff (`ruff.toml` exists but the project does not use it).
- Frontend (`booking_system_frontend/`): `npm run lint`, `npm run build` (runs `tsc -b` first). No unit test runner is configured.
- Java (`booking_system_inventory_hold_service/`): `mvn test`, single: `mvn test -Dtest=HoldControllerTest#methodName`. Requires JDK 17 or 21 (Lombok fails on 22+). Tests use H2 in-memory (`application-test.properties`), runtime uses SQLite.
- E2E (repo root): `./test.sh` (= `e2e/run-native.sh`), single: `./test.sh -k confirm`, include slow expiry test: `E2E_RUN_SLOW=1 ./test.sh`. It auto-builds the jar, uses throwaway DBs on ports 18001/18082 and sets hold duration to 1 min. Needs `booking_system_backend/.venv`.
- Run everything locally: `./start.sh` (kills whatever is on 8001/5173/8080 first).

## Non-obvious backend rules

- `server.py` endpoints are the single source of truth: MCP tools are **auto-generated** from FastAPI routes by `FastApiMCP(app)` at the bottom of the file. Add a REST route and it becomes an MCP tool; do not hand-write MCP tools. (`booking_system_backend/README.md` still describes manual MCP tools/`SessionLocal()` — outdated.)
- Route docstrings become MCP tool descriptions seen by AI agents; write them for that audience.
- Services (`services/*.py`) never raise; they return `XOut | ErrorResponse`. Routes check `isinstance(result, ErrorResponse)` and map `error_code` to HTTP status (`*_NOT_FOUND` -> 404, otherwise 409/422). Keep `error_code` strings stable, e2e and routes depend on them.
- `book_flight()` requires `user_id` AND matching `name` (`NAME_MISMATCH` otherwise). Java confirm flow depends on this via `POST /internal/bookings/from-hold` (camelCase payload keys `travelerId`, `travelerName`, `flightId`, `seatClass`; returns 400 on failure).
- Seat counters are three separate columns per flight (`economy_/business_/galaxium_seats_available`), updated in service code with if/elif branches. Multipliers are hardcoded in `services/booking.py` (`SEAT_CLASS_MULTIPLIERS`); prices are `int`.
- `app = FastAPI(root_path="/api")` — frontend calls `/api/*` (Vite proxy strips it). `uvicorn` runs on `0.0.0.0` in `server.py` main and Dockerfile; per `.bob` security rules new code must bind `127.0.0.1`.
- Java proxy endpoints (`/quotes`, `/holds/...`) swallow upstream failures and return `{"error": ...}` with HTTP 200. Check the body.
- DB: `DATABASE_URL` unset -> SQLite `./booking.db`. `SEED_DEMO_DATA` defaults to true (seeds only if empty); seed availability is randomized, so never assert exact seat counts, assert deltas.
- Tests override `get_db` via `server.app.dependency_overrides` and monkeypatch `server.seed`; in-memory SQLite uses `StaticPool`. Reuse the `client`/`db_session` fixtures in `tests/conftest.py`.

## Code style

- Python: 4-space, `snake_case` functions, `PascalCase` classes/Pydantic models, type hints with `X | None` (not `Optional`), `SeatClass` Literal from `schemas.py` for seat classes, imports sorted stdlib/third-party/local. Every public function has a docstring; service docstrings list the `error_code` values they can return and state that expected failures are returned, not raised. Timestamps are ISO strings (`datetime.now(tz=timezone.utc).isoformat()`); flight times are `"YYYY-MM-DD HH:MM"` strings.
- Plan documents go in `plans/` at the repository root.
- API JSON casing differs by service: Python = `snake_case`, Java = `camelCase` (`quoteId`, `holdId`, `externalBookingReference`). Frontend types in `src/types/index.ts` mirror both.
- TypeScript/React: functional components, one per file, named exports re-exported from `components/common/index.ts`; API calls only via `src/services/api.ts` (axios instance whose interceptor rejects with `ErrorResponse` shape `{success:false, error, error_code, details}`); hold state persisted in localStorage via `src/utils/holdStorage.ts` (`galaxium_holds_<userId>`). ESLint flat config (typescript-eslint + react-hooks + react-refresh); `react-refresh` means keep non-component exports out of component files (hence `useUserContext.ts` separate from `useUser.tsx`).
- Tailwind custom tokens: `space-dark`, `space-blue`, `cosmic-purple`, `nebula-pink`, `alien-green`, `solar-orange`, `star-white`. Do not assume default palette names.
- Java: Lombok (`@RequiredArgsConstructor`, `@Builder`, `@Data`, `@Slf4j`), no manual getters/setters; services `@Transactional`; controllers catch `IllegalArgumentException` -> 404 and `IllegalStateException` -> 400 and return empty bodies.

## Do not edit / commit

`booking_system_inventory_hold_service/target/`, `booking_system_frontend/dist/`, `scripts/terraform/.terraform/`, `*.db`, `*.log`, `.venv/`. `.env` is gitignored; frontend uses `VITE_API_URL` (see `.env.example`).
