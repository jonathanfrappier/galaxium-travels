# Sub-task 2: frontend (React/Vite)

Overview and decisions: [`itineraries-plan.md`](itineraries-plan.md). Read it first. Depends on the backend sub-task: [`itineraries-backend.md`](itineraries-backend.md), including its "Handoff notes".

Status: `[ ] pending`

## Intent

Let a signed-in user search for multi-leg trips, book one in a single click, and see their trips.

## Expected outcomes

- A **Trips** link in the header next to **Flights**, in both the desktop and the mobile navigation, active on `/trips`.
- `/trips` has a search form (origin, destination, date), one trip timeline per result, a **Book trip** button on each result, and a **My trips** section.
- **Book trip** creates the itinerary and confirms it in one click. There is no separate confirm step.
- After a successful booking, the trip appears under My trips without a page reload.
- An empty search shows a "no routes found" message. A user with no trips sees "no trips yet".
- Failed bookings show the backend error and leave My trips unchanged.
- `npm run lint` and `npm run build` pass.

## Todo list

1. **Types** (`src/types/index.ts`): add types that mirror the backend itinerary search result, itinerary request, and stored itinerary (`snake_case`, same as the Python schemas). Reuse existing `Flight` and `ErrorResponse`.
2. **API client** (`src/services/api.ts`): add search, create, confirm, and list-by-user functions. Use the existing axios instance and its error interceptor. Do not call the Java proxy routes (`/quotes`, `/holds/*`), and do not use `holdStorage`.
3. **Timeline component** (new file under `src/components/`, for example `trips/TripTimeline.tsx`): one component per file, named export. Shows legs in order with origin, destination, departure, arrival, layover duration between legs, total price, and total travel time. Use the Tailwind tokens from `AGENTS.md` (`space-blue`, `cosmic-purple`, `alien-green`, and so on). If a `components/common/index.ts` style re-export fits, follow it.
4. **Page** (`src/pages/Trips.tsx`, named export `Trips`):
   - Search form: origin, destination, date (`YYYY-MM-DD`). Loading, error, and empty states.
   - Result list: one timeline plus a **Book trip** button each.
   - **Book trip** flow: if no user is signed in, open the existing `UserIdentification` modal as `Flights.tsx` does, then continue. Otherwise call create, then confirm, with the user's `user_id` and `name` and the leg flight ids. Disable the button while the request runs. Show the backend `error` and `details` on failure.
   - **My trips** section: shown when signed in; loads the user's itineraries on mount and after each successful booking; shows each trip with the timeline, status, and total price; empty message when none.
   - Use `useUser` from `src/hooks/useUserContext.ts`.
5. **Routing** (`src/App.tsx`): add the `/trips` route.
6. **Header** (`src/components/layout/Header.tsx`): add the Trips link after Flights in both navs, with the same active styling.
7. **Validate:** `npm run lint` and `npm run build` from `booking_system_frontend/`. No unit test runner exists, so do a manual check with `./start.sh` after resetting the local database: sign in as Alice, search Earth to Europa on 2099-02-01, book it, and confirm it appears under My trips. Report that check to the user. If services cannot be started in the environment, say so.
8. Update the status line in this file and in `itineraries-plan.md`.

## Relevant context

- Router: `src/App.tsx` (routes inside `UserProvider` and `Layout`).
- Header: `src/components/layout/Header.tsx`. Flights link at lines 46-55 (desktop) and 119-128 (mobile).
- Page patterns: `src/pages/Flights.tsx` (login prompt before booking, loading and retry) and `src/pages/MyBookings.tsx`.
- API client: `src/services/api.ts`. Base URL is `VITE_API_URL` or `/api`; the Vite proxy forwards `/api` to `localhost:8001` and strips the prefix. The interceptor rejects with `{success:false, error, error_code, details}`.
- ESLint uses `react-refresh`, so keep non-component exports out of component files.
- Backend error codes to show clearly: `HOLD_FAILED`, `CONFIRM_FAILED`, `NO_SEATS_AVAILABLE`, `NAME_MISMATCH`, `INVALID_CONNECTION`.
- Seed data only loads into an empty database, so reset the local database before the manual check.

## Handoff notes

(Filled in when this sub-task is done.)
