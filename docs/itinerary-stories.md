# Multi-leg itineraries: user stories

## Request

Travelers heading to the outer moons book every connection as a separate single-flight booking and hope the times line up. We want one booking that connects up to three flights, with layovers between 2 and 72 hours. A trip books every leg or none of them, and travelers see their booked trips in a My trips list.

## Assumptions

Each of these needs confirmation from the team. Change the stories if any is wrong.

- A search date means the date the first leg departs, in UTC.
- Search results show itineraries of 2 or 3 legs. Direct flights keep using the existing flight list.
- Layover limits are inclusive: exactly 2 hours and exactly 72 hours are allowed.
- An itinerary never visits the same location twice.
- The traveler books through the Python backend directly. The quote and hold flow in the Java service is not used for itineraries in this release.
- Itinerary price is the sum of the economy `base_price` of each leg. There is no discount.
- My trips lists itinerary bookings only. Existing single-flight bookings do not appear there.
- Seed data only loads into an empty database, so existing local databases must be reset to see the new flights.
- Demo user Alice has user_id 1 and Bob has user_id 2, as created by the current seed.

## Out of scope

- Changing or cancelling a booked trip.
- Seat classes other than economy.
- More than three legs.
- Quotes and holds for itineraries.
- Showing existing single-flight bookings in My trips.
- Discounts, baggage, or any pricing other than the sum of leg prices.

## Stories

### Story 1: Seed flights for an outer-moon route

As a tester or demo user, I want the seeded schedule to include a connecting route to Europa, so that multi-leg search has real data to show.

Proposed seed flights. Each has 10 total seats, which the existing seed logic splits into 6 economy seats:

| Leg | Route | Departs (UTC) | Arrives (UTC) | Base price |
|-----|-------|---------------|---------------|-----------|
| 1 | Earth to Mars | 2099-02-01 09:00 | 2099-02-01 17:00 | 1000000 |
| 2 | Mars to Jupiter | 2099-02-02 13:00 | 2099-02-02 23:00 | 2500000 |
| 3 | Jupiter to Europa | 2099-02-04 15:00 | 2099-02-04 19:00 | 2000000 |

The layovers are 20 hours at Mars and 40 hours at Jupiter.

Acceptance criteria:

- Given an empty database, When the app starts with `SEED_DEMO_DATA` true, Then a flight Earth to Mars departing 2099-02-01 09:00, a flight Mars to Jupiter departing 2099-02-02 13:00, and a flight Jupiter to Europa departing 2099-02-04 15:00 each exist with 6 economy seats available.
- Given a database that already has users, When the app starts, Then no flights are added and the flight count is unchanged.

### Story 2: Search for multi-leg itineraries

As a traveler, I want to search from an origin to a destination on a date and see connecting routes, so that I can find a way to the outer moons without matching flights by hand.

Acceptance criteria:

- Given the seeded flight schedule, When a traveler searches Earth to Europa on 2099-02-01, Then the results include a three-leg route via Mars and Jupiter.
- Given the seeded flight schedule, When a traveler searches Earth to Europa on 2099-02-01, Then the three-leg route shows a total price of 5500000 and an arrival of 2099-02-04 19:00.
- Given the seeded flight schedule, When a traveler searches Earth to Europa on 2099-03-01, Then the results are empty and the page says no routes were found.
- Given the only path from Earth to Saturn needs four flights, When a traveler searches Earth to Saturn on 2099-02-01, Then the results are empty.

### Story 3: Enforce layover limits

As a traveler, I want only itineraries with sensible layovers, so that I never have to run to a connection or wait for days.

Test setup: leg 1 is Earth to Mars arriving 2099-02-01 17:00, and a Mars to Jupiter flight is the candidate second leg.

Acceptance criteria:

- Given the second leg departs 2099-02-01 18:59 (1 hour 59 minutes after arrival), When a traveler searches Earth to Jupiter on 2099-02-01, Then the itinerary is not in the results.
- Given the second leg departs 2099-02-01 19:00 (exactly 2 hours), When a traveler searches Earth to Jupiter on 2099-02-01, Then the itinerary is in the results.
- Given the second leg departs 2099-02-04 17:00 (exactly 72 hours), When a traveler searches Earth to Jupiter on 2099-02-01, Then the itinerary is in the results.
- Given the second leg departs 2099-02-04 17:01 (72 hours 1 minute), When a traveler searches Earth to Jupiter on 2099-02-01, Then the itinerary is not in the results.

### Story 4: Book an itinerary, all legs or none

As a traveler, I want to book every leg of a route in one action, so that I am never stranded with only part of a trip.

Acceptance criteria:

- Given Alice (user_id 1) and the three Story 1 flights with 6 economy seats each, When Alice books that itinerary with name "Alice", Then one trip is created with three economy bookings, each of the three flights has 5 economy seats left, and the trip price is 5500000.
- Given the Jupiter to Europa leg has 0 economy seats, When Alice books the Earth to Europa itinerary, Then the response is an error with `error_code` NO_SEATS_AVAILABLE naming the Jupiter to Europa leg, no trip or booking is created, and the Earth to Mars and Mars to Jupiter seat counts are unchanged.
- Given the Mars to Jupiter leg has 0 economy seats, When Alice books the Earth to Europa itinerary, Then the response is an error with `error_code` NO_SEATS_AVAILABLE, no trip or booking is created, and the Earth to Mars seat count is unchanged.

### Story 5: Reject invalid booking requests

As a traveler, I want an invalid itinerary request to be refused outright, so that I am never charged or seated on a trip that breaks the rules.

Acceptance criteria:

- Given user_id 1 is Alice, When a request books an itinerary with user_id 1 and name "Bob", Then the response is an error with `error_code` NAME_MISMATCH and no seats change on any leg.
- Given a request with seat class "business", When a traveler books an itinerary, Then the response is an error with `error_code` INVALID_SEAT_CLASS and no seats change.
- Given a request lists four flight IDs, When a traveler books it, Then the response is a validation error and no seats change.
- Given a request where leg 2 departs 1 hour 59 minutes after leg 1 arrives, When a traveler books it, Then the response is an error and no seats change.

### Story 6: See booked trips in My trips

As a traveler, I want a My trips list, so that I can review everything I have booked in one place.

Acceptance criteria:

- Given Alice has booked the Story 1 itinerary, When Alice opens My trips, Then one trip is shown with legs Earth to Mars, Mars to Jupiter, Jupiter to Europa in departure order, each with its departure and arrival time, and a total price of 5500000.
- Given Alice has booked two itineraries departing 2099-02-01 and 2099-02-10, When Alice opens My trips, Then the 2099-02-01 trip is listed first.
- Given Bob (user_id 2) has booked no itineraries, When Bob opens My trips, Then the list is empty and the page says he has no trips yet.
- Given Alice has booked an itinerary, When Bob opens My trips, Then Alice's trip is not shown.

## Open questions

1. Should layover limits be inclusive (assumed) or exclusive?
2. Do we need the 15-minute hold step for itineraries in a later release?
3. Should single-flight bookings appear in My trips in a later release?
