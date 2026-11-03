# Trust Boundary Audit: Itinerary Endpoints

- Standard: OWASP ASVS 4.0 (V5.1.2, V5.1.3, V11.1.4, V11.1.5)
- Scope: `POST /itineraries` and `POST /itineraries/{itinerary_id}/confirm`
- Files reviewed: `booking_system_backend/server.py`, `booking_system_backend/schemas.py`, `booking_system_backend/services/itinerary.py` (plus `is_valid_connection` / `parse_time` in `services/itinerary_search.py`, which the service calls)
- Out of scope: authentication and authorization (the app has none yet)
- Method: static review. The Java hold service was not reviewed, so behavior on that side is noted as an assumption where it matters.

## Phase 1: Trust boundary map

### POST /itineraries (`server.py:246`, `itinerary.py:184`)

| Client-controlled field | Schema (`schemas.py:90`) | What the server does with it |
|---|---|---|
| `user_id` | `int`, unbounded | Looked up in `users` with `name` (`itinerary.py:207`). Stored on the `Itinerary` row and sent to the Java service as `travelerId`. |
| `name` | `str`, no length limit | Compared to the registered name. Sent to Java as `travelerName`. Echoed in the `NAME_MISMATCH` error. |
| `flight_ids` | `list[int]`, no size or item limit | Count checked after parsing (`itinerary.py:199`). Each ID is queried, checked for connections and seats, then turned into one quote and one hold per leg. |
| Extra JSON keys | Pydantic default (ignored) | Dropped. Never reach the DB models. |

Server-derived values: `total_price` (sum of `base_price` from the DB, `itinerary.py:258`), `status`, `created_at`, `seatClass` (hardcoded `"economy"`), `quantity` (hardcoded `1`), `quote_id` and `hold_id` (from Java).

### POST /itineraries/{itinerary_id}/confirm (`server.py:269`, `itinerary.py:374`)

| Client-controlled field | Schema | What the server does with it |
|---|---|---|
| `itinerary_id` (path) | `int`, unbounded | Looked up in `itineraries`. State is read, then a confirm call goes to Java for every leg. The row is then set to `confirmed` or `failed`. |

There is no request body. All other values come from stored rows.

## Phase 2: Control results

| Control | Result | Notes |
|---|---|---|
| V5.1.2 Mass parameter assignment | PASS | `ItineraryRequest` has only `user_id`, `name`, `flight_ids`. `status`, `total_price`, `hold_id`, `booking_id` and `created_at` cannot be set by the client. Unknown keys are ignored. |
| V5.1.3 Allow-list input validation | FAIL | See F-1 and F-2. |
| V11.1.4 Limits on excessive business requests | FAIL | See F-3 and F-4. |
| V11.1.5 Business logic limits against abuse | FAIL | See F-5. The client cannot set its own price, so the price part of this control passes. |

## Phase 3: Findings

### F-1: Unbounded integers and strings reach the database layer

- Rule: V5.1.3
- Severity: Medium
- File and line: `schemas.py:90-93`; `server.py:270`
- Issue: `user_id`, `flight_ids` items and `itinerary_id` are plain `int`, and `name` is a plain `str`, with no range or length limits. An integer above 2^63-1 makes the SQLite driver raise `OverflowError` (reproduced in a `python:3.12-slim` container), which becomes an unhandled HTTP 500. A very long `name` is stored and forwarded to the Java service unchanged.
- Fix: Use `Field(gt=0, le=...)` on the IDs, `Field(min_length=1, max_length=...)` on `name`, and `Path(gt=0, le=...)` on `itinerary_id`.

### F-2: Flight list is not validated as a list of expected values

- Rule: V5.1.3
- Severity: Low
- File and line: `schemas.py:93`; `itinerary.py:199`, `itinerary.py:241-247`
- Issue: `flight_ids` has no `min_length`, `max_length` or item bounds. Oversized lists are parsed in full before the 1 to 3 check runs. `create_itinerary` also skips the no-repeated-location rule that `search_itineraries` enforces (`itinerary.py:131-134`, `150-158`), so a client can hold chains such as A->B, B->A that the search never offers.
- Fix: Declare `flight_ids: list[int] = Field(min_length=1, max_length=3)` and apply the same distinct-locations check in `create_itinerary`.

### F-3: No limit on holds or itineraries per user

- Rule: V11.1.4
- Severity: High
- File and line: `itinerary.py:199-338` (no per-user check anywhere); `server.py:246`
- Issue: A client can call `POST /itineraries` repeatedly. Each call places up to 3 holds in the Java service, one economy seat per leg. A single user, or a script, can hold all economy inventory on chosen flights until the holds expire. Nothing checks for existing `held` itineraries, duplicate flight sets or a request rate.
- Fix: Reject creation when the user already has more than a small fixed number of `held` itineraries (or a held itinerary on the same flight), and add rate limiting on this route.

### F-4: Failed attempts write unbounded rows

- Rule: V11.1.4
- Severity: Low
- File and line: `itinerary.py:298-318`
- Issue: Every `HOLD_FAILED` outcome persists a new `Itinerary` row with status `failed`, plus legs. Repeated failing requests grow the tables without limit.
- Fix: Cap stored failed itineraries per user or skip persisting them (log the failure instead).

### F-5: Confirm is not atomic, and bookings are not checked against business rules

- Rule: V11.1.5 (also V11.1.4)
- Severity: Medium for the race (assumes the Java service rejects a second confirm of the same hold, which was not verified); Medium for the flight-time check
- File and line: `itinerary.py:395-398`, `itinerary.py:416-475`; `itinerary.py:226-256`
- Issue: Two parts.
  1. The status check at `itinerary.py:395` and the later write at `itinerary.py:478` are separate, with no lock or conditional update. Two concurrent confirms of the same `held` itinerary both pass the check. If the second one fails at Java, it releases holds that the first call just confirmed (`itinerary.py:454`) and marks the itinerary `failed` (`itinerary.py:467`). A caller can therefore turn a successful booking into an inconsistent `failed` state.
  2. `create_itinerary` never checks that flights depart in the future, and the same traveler can hold overlapping or duplicate itineraries. `confirm_itinerary` also never compares the stored `total_price` with what the bookings actually charged.
- Fix: Claim the itinerary with an atomic `UPDATE ... SET status='confirming' WHERE id=? AND status='held'` and proceed only if one row changed; also reject flights whose departure time is in the past at create time.

## Observation outside the four controls

- `itinerary.py:218` puts the registered name of an existing user into the `NAME_MISMATCH` response, so a caller who guesses a `user_id` can read that user's name. Remove the registered name from the message. This is an information disclosure issue, not authentication, so it is listed here only for follow-up.

## Summary

| ID | Rule | Severity |
|---|---|---|
| F-1 | V5.1.3 | Medium |
| F-2 | V5.1.3 | Low |
| F-3 | V11.1.4 | High |
| F-4 | V11.1.4 | Low |
| F-5 | V11.1.5 | Medium |
