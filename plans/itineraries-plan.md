# Multi-leg itineraries: plan overview

Requirements: [`docs/itinerary-stories.md`](../docs/itinerary-stories.md), overridden where this plan says so (see "Deviations from the stories").

Sub-task files (implement in this order, one at a time):

1. [`itineraries-backend.md`](itineraries-backend.md): Python backend (DB, seed, search, hold/confirm flow, routes, tests). Status: `[x] completed`
2. [`itineraries-frontend.md`](itineraries-frontend.md): React `/trips` page, header link, API client. Status: `[x] completed`

## Goal

A passenger books one trip made of up to three flights, for example Earth to Europa via Mars and Jupiter. A trip books every leg or none of them.

Done when: searching Earth to Europa on 2099-02-01 returns one three-leg route, and a signed-in user can book it from the `/trips` page and see it under My trips.

## Approach

```
Frontend /trips
  -> Python GET /itineraries/search           (pure DB read, no Java)
  -> Python POST /itineraries                 (per leg: Java quote, then Java hold; all or nothing)
  -> Python POST /itineraries/{id}/confirm    (per leg: Java confirm -> Java calls Python /internal/bookings/from-hold)
  -> Python GET /users/{user_id}/itineraries  (My trips)
```

- A new service module `booking_system_backend/services/itinerary.py` holds search, create, confirm, and list. It follows the pattern in `services/booking.py`: return a result or an `ErrorResponse`, never raise for expected failures, with docstrings that list the `error_code` values.
- The existing `booking_system_backend/services/itinerary_search.py` is written by the user before implementation starts. The new service imports `parse_time(value)` and `is_valid_connection(arriving, departing)` from it. Do not create, stub, or edit that file.
- The Java hold service is called directly with `httpx` for every quote, hold, release, and confirm, using the request bodies in `booking_system_inventory_hold_service/README.md`. The proxy routes in `server.py` are not reused because they return HTTP 200 on errors. The Java service is not changed.
- Confirming a hold already creates the booking through `/internal/bookings/from-hold`. The new code never calls `book_flight()` for a leg. It only tags the booking Java created with the itinerary.

## Decisions

| Topic | Decision |
|-------|----------|
| Result size | 1 to 3 legs. Direct flights are included in search results. |
| First leg date | Compared in UTC against the first leg's departure date. |
| Layovers | Judged by `is_valid_connection`, which the user supplies. Spec: at least 2 hours and at most 72 hours. |
| Repeat visits | An itinerary never visits the same location twice (from the stories). |
| Sort | Total travel time (first departure to last arrival, layovers included), then total price. |
| Price | Sum of each leg's economy `base_price`. Seat class is always economy. |
| Seat availability in search | Legs with no economy seats are left out. |
| Early seat check | `POST /itineraries` checks economy availability on every leg before holding, and returns `NO_SEATS_AVAILABLE` (409). The Java service does not check seats at quote or hold time, so without this a sold-out leg only fails at confirm. |
| Hold failure | Release earlier holds, mark the itinerary `failed`, return `HOLD_FAILED` with HTTP 502. |
| Confirm failure | Confirm is not atomic in Java, so a leg can fail after earlier legs are booked. If confirming any leg fails: cancel the legs already confirmed with `booking.cancel_booking` (restores seats), release the remaining holds (the failing leg and those after it), mark the itinerary `failed`, and return `CONFIRM_FAILED` with HTTP 502. Compensation is best effort and is covered by a dedicated test (see the backend sub-task). |
| Idempotent confirm | Confirming an already confirmed itinerary returns it unchanged. |
| My trips content | `GET /users/{user_id}/itineraries` returns confirmed itineraries only, ordered by first departure. Held and failed ones are not bookings. |
| Authorization | The app has no authentication today. `POST /itineraries/{id}/confirm` takes no user and trusts the itinerary id. This matches the existing `/cancel/{booking_id}`. Out of scope here. |

## Deviations from the stories

These come from the request and override `docs/itinerary-stories.md`. The stories file is not edited.

- Stories say results show 2 or 3 legs. Request says 1 to 3.
- Stories say the Java quote and hold flow is not used. Request says every leg is held through the Java hold service.
- Stories expect `NO_SEATS_AVAILABLE` when a leg is sold out. The request defines `HOLD_FAILED` (502) for a failed hold. Sold-out legs are caught by the early seat check above, which keeps `NO_SEATS_AVAILABLE` (409).
- Stories seed only the Europa route. Request also seeds Earth to Mars via Moon on 2099-03-01.
- Story 2 expects Earth to Europa on 2099-03-01 to be empty. This still holds because the Moon route only reaches Mars.

## Cross-cutting notes

- MCP tools are generated from the REST routes (`FastApiMCP(app)`), so every new route is also exposed to AI agents. Write route docstrings for that audience.
- Seed data loads only into an empty database. Existing local databases must be reset to see the new flights. The schema change itself does not need a reset.
- Do not bind anything to `0.0.0.0` in new code. Do not edit `target/`, `dist/`, `*.db`, or `.venv/`.
- Validation commands: `pytest` from `booking_system_backend/`; `npm run lint` and `npm run build` from `booking_system_frontend/`; `./test.sh` from the repo root.

## Open items for the implementer

- `services/itinerary_search.py` does not exist yet. The backend sub-task cannot start until the user has created it.
- The argument types `is_valid_connection(arriving, departing)` accepts are not known yet. Read the file first. If it takes `datetime` objects, convert the stored time strings with `parse_time` before calling it. If it takes strings, pass the stored `arrival_time` and `departure_time` as they are.
