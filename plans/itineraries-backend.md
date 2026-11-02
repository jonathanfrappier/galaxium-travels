# Sub-task 1: backend (Python/FastAPI)

Overview and decisions: [`itineraries-plan.md`](itineraries-plan.md). Read it first.

Status: `[ ] pending`

## Intent

Add itinerary search, all-or-nothing holding through the Java hold service, confirmation into bookings, and a per-user list. Add the tables, the nullable `bookings.itinerary_id` column, and the seed flights that make the done-when scenario work.

## Expected outcomes

- `GET /itineraries/search?origin=Earth&destination=Europa&date=2099-02-01` returns exactly one route, with three legs via Mars and Jupiter, total price 5500000, arrival `2099-02-04 19:00`.
- `GET /itineraries/search?origin=Earth&destination=Mars&date=2099-03-01` returns a two-leg route via Moon.
- `POST /itineraries` creates a `held` itinerary with one Java hold per leg, or releases everything and returns `HOLD_FAILED` (502).
- `POST /itineraries/{itinerary_id}/confirm` turns the holds into bookings tagged with `itinerary_id` and sets the itinerary to `confirmed`. On failure it compensates and returns `CONFIRM_FAILED` (502).
- `GET /users/{user_id}/itineraries` returns the user's confirmed itineraries, earliest first.
- An existing database (created before this change) starts, gets the new column through `init_db()`, and keeps its data.
- Java hold service code is unchanged.

## Todo list

1. **Precondition.** Confirm that `booking_system_backend/services/itinerary_search.py` exists with `parse_time` and `is_valid_connection`. Read the signatures. Stop and tell the user if the file is missing.
2. **Models** (`models.py`): add `Itinerary` (`itineraries`: id, `user_id` FK, `status` held/confirmed/failed, `total_price`, `created_at` ISO string) and `ItineraryLeg` (`itinerary_legs`: id, `itinerary_id` FK, `position`, `flight_id` FK, Java `quote_id`, Java `hold_id`, nullable `booking_id`). Add nullable `Booking.itinerary_id` FK. Keep column style consistent with existing models.
3. **Migration** (`db.py`, `init_db()`): after `create_all`, inspect `bookings`. If `itinerary_id` is missing, add it with `ALTER TABLE`. It must be idempotent and work on SQLite and PostgreSQL. No database rebuild.
4. **Schemas** (`schemas.py`): add request and response models for the itinerary request (`user_id`, `name`, `flight_ids` with 1 to 3 items), the search result (legs, total price, total duration in minutes, first departure, last arrival), and the stored itinerary with its legs. Reuse `FlightOut` data for legs where it fits. Keep `snake_case` and `X | None`.
5. **Seed** (`seed.py`): add the connecting flights, with 10 total seats each so economy is 6.
   - Earth to Mars `2099-02-01 09:00` to `2099-02-01 17:00`, price 1000000.
   - Mars to Jupiter `2099-02-02 13:00` to `2099-02-02 23:00`, price 2500000.
   - Jupiter to Europa `2099-02-04 15:00` to `2099-02-04 19:00`, price 2000000.
   - Earth to Moon and Moon to Mars on 2099-03-01 and 2099-03-02, with a layover that is valid under the 2 to 72 hour rule. Choose times and prices.
   - Write the new rows as `YYYY-MM-DD HH:MM`. Existing seed rows use `YYYY-MM-DDTHH:MM:SSZ`, and `parse_time` accepts both.
   - Check that no seeded combination creates a second Earth to Europa route on 2099-02-01.
6. **Service** (`services/itinerary.py`, new): import `parse_time` and `is_valid_connection` from `services.itinerary_search`.
   - Search: validate the date, load candidate flights with economy seats, build chains of 1 to 3 legs that start on the date, never revisit a location, and pass `is_valid_connection`. Sort by total duration, then total price. Return an empty list when nothing matches. Return `ErrorResponse` `INVALID_DATE` for a bad date.
   - Create: validate user and name (`USER_NOT_FOUND`, `NAME_MISMATCH`), flights (`FLIGHT_NOT_FOUND`), the 1 to 3 limit, connections (`INVALID_CONNECTION`), and economy seats (`NO_SEATS_AVAILABLE`) before any Java call. Then, per leg in order, create a quote and a hold. On any failure, release the holds already made, store the itinerary as `failed`, and return `HOLD_FAILED`. On success store the itinerary as `held` with its legs.
   - Confirm: return `ITINERARY_NOT_FOUND` if missing, return unchanged if already `confirmed`, return `INVALID_ITINERARY_STATE` if `failed`. Confirm each leg's hold in order. Read the booking id from `externalBookingReference` and set `Booking.itinerary_id` and the leg's `booking_id`.
   - Confirm failure: if confirming any leg fails (non-2xx, `httpx.HTTPError`, or a missing booking reference), do these in order, then return `CONFIRM_FAILED`:
     1. Cancel every leg that was already confirmed by calling `booking.cancel_booking(db, booking_id)` for its booking. This sets the booking to `cancelled` and restores the economy seat. The booking rows stay in the database as `cancelled`.
     2. Release the holds of the failing leg and of every leg after it, with the Java release call. Release only holds that are still `HELD`. A hold that is already `CONFIRMED` cannot be released, so it is handled by step 1.
     3. Set the itinerary status to `failed`.
     4. Return `ErrorResponse` with `error_code="CONFIRM_FAILED"`.
     Compensation is best effort. If a cancel or release call itself fails, keep going with the remaining legs, still set the itinerary to `failed`, and log the leg and hold ids (no personal data) so the leftover can be cleaned up. The route maps `CONFIRM_FAILED` to HTTP 502.
   - List: confirmed itineraries for a user, ordered by first leg departure.
   - Java access: one small helper using `httpx` with an explicit timeout, `JAVA_SERVICE_URL` read from the environment (default `http://localhost:8080`), and the README request bodies (`flightId`, `seatClass`, `quantity`, `travelerId`, `travelerName`). Treat any non-2xx or `httpx.HTTPError` as a failed step. Do not import from `server.py`. Do not call the proxy routes. Do not call `book_flight()`.
   - Never raise for expected failures. Do not put upstream error text in client-facing messages or log personal data.
7. **Routes** (`server.py`): add `GET /itineraries/search`, `POST /itineraries`, `POST /itineraries/{itinerary_id}/confirm`, and `GET /users/{user_id}/itineraries`. Map `error_code` to status inside each route, like the existing routes: `*_NOT_FOUND` to 404, `HOLD_FAILED` and `CONFIRM_FAILED` to 502, `NO_SEATS_AVAILABLE`, `NAME_MISMATCH`, and `INVALID_ITINERARY_STATE` to 409, other validation errors to 422. Write docstrings for AI agents because these become MCP tools. Register routes so `/itineraries/search` is not captured by `/itineraries/{itinerary_id}`.
8. **Tests** (`booking_system_backend/tests/`), reusing `client` and `db_session`:
   - Search: Earth to Europa on 2099-02-01 gives one three-leg route with price 5500000; Earth to Mars on 2099-03-01 gives the Moon route; layover at 1h59, 2h, 72h, 72h01 (stories, Story 3); no repeat of a location; sold-out legs excluded; sort order; bad date.
   - Create and confirm, with the Java service replaced by `httpx.MockTransport` (patch the helper that builds the client): happy path, hold failure at leg 2 releases leg 1 and returns `HOLD_FAILED`, name mismatch, four flight ids, invalid connection, unknown user. Assert seat deltas, not absolute counts.
   - Confirm failure (service and REST): book a three-leg itinerary, then make the mock Java confirm succeed for leg 1 and leg 2 (the mock calls `book_flight` or posts to `/internal/bookings/from-hold` through the test `client` so real bookings and seat decrements exist) and fail for leg 3. Assert:
     - the response is HTTP 502 with `error_code` `CONFIRM_FAILED`;
     - the itinerary status is `failed`;
     - the bookings for legs 1 and 2 have status `cancelled`, and no booking is `booked` for the itinerary;
     - economy seats on legs 1 and 2 are back to their value before the confirm (assert the delta is zero);
     - leg 3's seat count is unchanged;
     - the mock received a release call for leg 3's hold and no release call for legs 1 and 2;
     - the itinerary does not appear in `GET /users/{user_id}/itineraries`.
   - Add a second case where the first leg's confirm fails: no booking is created, remaining holds (legs 1 to 3) are released, status is `failed`, and the response is 502 `CONFIRM_FAILED`.
   - Migration: build a database with the old `bookings` table, run `init_db()`, assert the column exists and rows survive, and run it twice.
   - Seed: assert the new flights exist with 6 economy seats and that seeding twice adds nothing.
   - List: ordering, other users' trips hidden, empty list.
9. **E2E** (`e2e/`): one test that registers a user, searches Earth to Europa on 2099-02-01, creates and confirms the itinerary against the real Java service, and finds it in the user's itineraries. Follow `e2e/conftest.py` and `e2e/helpers.py`.
10. **Validate:** run `pytest` from `booking_system_backend/` (see the `.venv` note in `AGENTS.md`), then `./test.sh` from the repo root. Do not run ruff.
11. Update the status line in this file and in `itineraries-plan.md`, and add any notes the frontend sub-task needs (final response shapes, error codes) under "Handoff notes" below.

## Relevant context

- Pattern to follow: [`services/booking.py`](../booking_system_backend/services/booking.py) (`book_flight`, `cancel_booking`).
- Route error mapping pattern: `server.py` lines 157-218. There is no shared mapping helper.
- Java contract: request bodies in [`booking_system_inventory_hold_service/README.md`](../booking_system_inventory_hold_service/README.md). Quote: `POST /api/v1/quotes`. Hold: `POST /api/v1/quotes/{quoteId}/holds`. Confirm: `POST /api/v1/holds/{holdId}/confirm`. Release: `POST /api/v1/holds/{holdId}/release`.
- Java behavior (read from `HoldService.java` and `HoldController.java`): hold creation checks only that the quote exists and has not expired; confirm calls `/internal/bookings/from-hold`, stores the Python `booking_id` in `externalBookingReference`, and on failure sets the hold to `CONFIRMATION_FAILED` and returns an empty 400. A `CONFIRMED` hold cannot be released.
- `/internal/bookings/from-hold` in `server.py` (line 226) is called by Java only. Do not call it from the new code.
- Flight times are strings in two formats. The `/flights` date filter and `services/flight.py` assume `YYYY-MM-DD HH:MM`. Use `parse_time` for all time math. A string prefix match on `YYYY-MM-DD` works for both formats when filtering first legs.
- The seed is in `seed.py`; the lifespan in `server.py` calls `init_db()` then `seed()`.
- Tests: `tests/conftest.py` disables seeding and uses in-memory SQLite with `StaticPool`.
- Files currently modified in the working tree: `db.py`, `seed.py`, `server.py`, `services/booking.py`, `services/flight.py`, `services/user.py`. Read them again before editing.

## Handoff notes

(Filled in when this sub-task is done.)
