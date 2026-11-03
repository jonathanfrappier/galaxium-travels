import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import Flight
from services import itinerary
from services.itinerary_search import is_valid_connection

_flight_ids = itertools.count(1)


def make_flight(origin, destination, departure_time, arrival_time, base_price=1000):
    """Build an in-memory Flight (never added to a database) with a unique flight_id."""
    return Flight(
        flight_id=next(_flight_ids),
        origin=origin,
        destination=destination,
        departure_time=departure_time,
        arrival_time=arrival_time,
        base_price=base_price,
        economy_seats_available=5,
        business_seats_available=3,
        galaxium_seats_available=1,
    )


class FakeQuery:
    """Minimal stand-in for a SQLAlchemy query over a fixed list of Flights.

    filter() is a no-op, so tests must only pass flights that have economy seats.
    """

    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)


class FakeSession:
    """Minimal stand-in for a SQLAlchemy Session that serves the given Flights."""

    def __init__(self, flights):
        self._flights = flights

    def query(self, model):
        return FakeQuery(self._flights)


def search(flights, origin, destination, date):
    """Run search_itineraries against in-memory flights."""
    return itinerary.search_itineraries(FakeSession(flights), origin, destination, date)


class TestIsValidConnection:
    """Test is_valid_connection layover and origin rules."""

    def arriving(self):
        return make_flight("Earth", "Moon", "2099-03-01 08:00", "2099-03-01 12:00")

    def test_layover_exactly_2_hours_is_valid(self):
        """A 2 hour layover is the minimum allowed."""
        departing = make_flight("Moon", "Mars", "2099-03-01 14:00", "2099-03-01 20:00")
        assert is_valid_connection(self.arriving(), departing) is True

    def test_layover_1h59_is_invalid(self):
        """A 1 hour 59 minute layover is too short."""
        departing = make_flight("Moon", "Mars", "2099-03-01 13:59", "2099-03-01 20:00")
        assert is_valid_connection(self.arriving(), departing) is False

    def test_layover_exactly_72_hours_is_valid(self):
        """A 72 hour layover is the maximum allowed."""
        departing = make_flight("Moon", "Mars", "2099-03-04 12:00", "2099-03-04 20:00")
        assert is_valid_connection(self.arriving(), departing) is True

    def test_layover_72h01_is_invalid(self):
        """A 72 hour 1 minute layover is too long."""
        departing = make_flight("Moon", "Mars", "2099-03-04 12:01", "2099-03-04 20:00")
        assert is_valid_connection(self.arriving(), departing) is False

    def test_departure_before_arrival_is_invalid(self):
        """A connection that leaves before the inbound flight lands is invalid."""
        departing = make_flight("Moon", "Mars", "2099-03-01 10:00", "2099-03-01 20:00")
        assert is_valid_connection(self.arriving(), departing) is False

    def test_origin_must_match_destination(self):
        """The departing flight must leave from where the inbound flight landed."""
        departing = make_flight("Venus", "Mars", "2099-03-01 14:00", "2099-03-01 20:00")
        assert is_valid_connection(self.arriving(), departing) is False

    def test_origin_match_ignores_case_and_whitespace(self):
        """Location matching is case-insensitive and ignores surrounding spaces."""
        departing = make_flight(" moon ", "Mars", "2099-03-01 14:00", "2099-03-01 20:00")
        assert is_valid_connection(self.arriving(), departing) is True

    def test_mixed_timestamp_formats(self):
        """ISO and space-separated timestamps can be compared with each other."""
        arriving = make_flight("Earth", "Moon", "2099-03-01T08:00:00Z", "2099-03-01T12:00:00Z")
        departing = make_flight("Moon", "Mars", "2099-03-01 14:00", "2099-03-01 20:00")
        assert is_valid_connection(arriving, departing) is True

        too_soon = make_flight("Moon", "Mars", "2099-03-01 13:59", "2099-03-01 20:00")
        assert is_valid_connection(arriving, too_soon) is False

    def test_iso_boundary_to_the_second(self):
        """ISO timestamps are compared to the second at the layover limits."""
        arriving = make_flight("Earth", "Moon", "2099-03-01T08:00:00Z", "2099-03-01T12:00:00Z")
        just_short = make_flight("Moon", "Mars", "2099-03-01T13:59:59Z", "2099-03-01T20:00:00Z")
        just_long = make_flight("Moon", "Mars", "2099-03-04T12:00:01Z", "2099-03-04T20:00:00Z")
        assert is_valid_connection(arriving, just_short) is False
        assert is_valid_connection(arriving, just_long) is False


class TestSearchItineraries:
    """Test search_itineraries route building, filtering, and ordering."""

    def test_direct_route(self):
        """A single flight on the date is returned as a one-leg route."""
        direct = make_flight("Earth", "Mars", "2099-03-01 08:00", "2099-03-01 16:00", base_price=1000000)

        results = search([direct], "Earth", "Mars", "2099-03-01")

        assert len(results) == 1
        assert [leg.flight_id for leg in results[0].legs] == [direct.flight_id]
        assert results[0].total_price == 1000000
        assert results[0].total_duration_minutes == 8 * 60
        assert results[0].first_departure == "2099-03-01 08:00"
        assert results[0].last_arrival == "2099-03-01 16:00"

    def test_two_leg_route(self):
        """Two flights connected through Moon form one two-leg route."""
        leg1 = make_flight("Earth", "Moon", "2099-03-01 08:00", "2099-03-01 12:00", base_price=500000)
        leg2 = make_flight("Moon", "Mars", "2099-03-01 16:00", "2099-03-01 23:00", base_price=800000)

        results = search([leg1, leg2], "Earth", "Mars", "2099-03-01")

        assert len(results) == 1
        assert [leg.flight_id for leg in results[0].legs] == [leg1.flight_id, leg2.flight_id]
        assert results[0].total_price == 1300000
        assert results[0].total_duration_minutes == 15 * 60

    def test_direct_and_two_leg_routes_are_both_returned(self):
        """A direct flight and a connection to the same destination are both listed."""
        direct = make_flight("Earth", "Mars", "2099-03-01 08:00", "2099-03-01 20:00")
        leg1 = make_flight("Earth", "Moon", "2099-03-01 08:00", "2099-03-01 12:00")
        leg2 = make_flight("Moon", "Mars", "2099-03-01 16:00", "2099-03-01 23:00")

        results = search([direct, leg1, leg2], "Earth", "Mars", "2099-03-01")

        assert sorted(len(r.legs) for r in results) == [1, 2]

    def test_three_leg_route(self):
        """Three connected flights form a three-leg route."""
        leg1 = make_flight("Earth", "Moon", "2099-03-01 08:00", "2099-03-01 12:00")
        leg2 = make_flight("Moon", "Mars", "2099-03-01 16:00", "2099-03-01 23:00")
        leg3 = make_flight("Mars", "Jupiter", "2099-03-02 09:00", "2099-03-02 19:00")

        results = search([leg1, leg2, leg3], "Earth", "Jupiter", "2099-03-01")

        assert len(results) == 1
        assert len(results[0].legs) == 3

    def test_four_leg_route_is_excluded(self):
        """A route that needs four flights is never returned."""
        flights = [
            make_flight("Earth", "Moon", "2099-03-01 08:00", "2099-03-01 12:00"),
            make_flight("Moon", "Mars", "2099-03-01 16:00", "2099-03-01 23:00"),
            make_flight("Mars", "Venus", "2099-03-02 09:00", "2099-03-02 19:00"),
            make_flight("Venus", "Jupiter", "2099-03-02 23:00", "2099-03-03 05:00"),
        ]

        results = search(flights, "Earth", "Jupiter", "2099-03-01")

        assert results == []

    def test_layover_exactly_2_hours_is_included(self):
        """A route with a 2 hour layover is returned."""
        leg1 = make_flight("Earth", "Moon", "2099-03-01 08:00", "2099-03-01 12:00")
        leg2 = make_flight("Moon", "Mars", "2099-03-01 14:00", "2099-03-01 20:00")

        assert len(search([leg1, leg2], "Earth", "Mars", "2099-03-01")) == 1

    def test_layover_1h59_is_excluded(self):
        """A route with a 1 hour 59 minute layover is not returned."""
        leg1 = make_flight("Earth", "Moon", "2099-03-01 08:00", "2099-03-01 12:00")
        leg2 = make_flight("Moon", "Mars", "2099-03-01 13:59", "2099-03-01 20:00")

        assert search([leg1, leg2], "Earth", "Mars", "2099-03-01") == []

    def test_layover_exactly_72_hours_is_included(self):
        """A route with a 72 hour layover is returned."""
        leg1 = make_flight("Earth", "Moon", "2099-03-01 08:00", "2099-03-01 12:00")
        leg2 = make_flight("Moon", "Mars", "2099-03-04 12:00", "2099-03-04 20:00")

        assert len(search([leg1, leg2], "Earth", "Mars", "2099-03-01")) == 1

    def test_layover_72h01_is_excluded(self):
        """A route with a 72 hour 1 minute layover is not returned."""
        leg1 = make_flight("Earth", "Moon", "2099-03-01 08:00", "2099-03-01 12:00")
        leg2 = make_flight("Moon", "Mars", "2099-03-04 12:01", "2099-03-04 20:00")

        assert search([leg1, leg2], "Earth", "Mars", "2099-03-01") == []

    def test_mixed_timestamp_formats(self):
        """Routes mixing ISO and space-separated timestamps are built and measured correctly."""
        leg1 = make_flight("Earth", "Moon", "2099-03-01T08:00:00Z", "2099-03-01T12:00:00Z")
        leg2 = make_flight("Moon", "Mars", "2099-03-01 14:00", "2099-03-01 20:00")

        results = search([leg1, leg2], "Earth", "Mars", "2099-03-01")

        assert len(results) == 1
        assert results[0].total_duration_minutes == 12 * 60
        # Original stored strings are returned unchanged.
        assert results[0].first_departure == "2099-03-01T08:00:00Z"
        assert results[0].last_arrival == "2099-03-01 20:00"

    def test_first_leg_date_matches_iso_format(self):
        """The date filter on the first leg works for ISO timestamps too."""
        on_date = make_flight("Earth", "Mars", "2099-03-01T08:00:00Z", "2099-03-01T16:00:00Z")
        other_date = make_flight("Earth", "Mars", "2099-03-02T08:00:00Z", "2099-03-02T16:00:00Z")

        results = search([on_date, other_date], "Earth", "Mars", "2099-03-01")

        assert [r.legs[0].flight_id for r in results] == [on_date.flight_id]

    def test_sort_by_duration_then_price(self):
        """Routes are ordered by total duration, then by total price."""
        # Via Moon: 08:00 -> 23:00 = 15h, price 1.3M
        moon1 = make_flight("Earth", "Moon", "2099-03-01 08:00", "2099-03-01 12:00", base_price=500000)
        moon2 = make_flight("Moon", "Mars", "2099-03-01 16:00", "2099-03-01 23:00", base_price=800000)
        # Via Venus: 08:00 -> 20:00 = 12h, price 2M
        venus1 = make_flight("Earth", "Venus", "2099-03-01 08:00", "2099-03-01 11:00", base_price=1000000)
        venus2 = make_flight("Venus", "Mars", "2099-03-01 14:00", "2099-03-01 20:00", base_price=1000000)
        # Via Ceres: 08:00 -> 20:00 = 12h, price 1M (same duration as Venus, cheaper)
        ceres1 = make_flight("Earth", "Ceres", "2099-03-01 08:00", "2099-03-01 11:00", base_price=400000)
        ceres2 = make_flight("Ceres", "Mars", "2099-03-01 14:00", "2099-03-01 20:00", base_price=600000)

        results = search(
            [moon1, moon2, venus1, venus2, ceres1, ceres2], "Earth", "Mars", "2099-03-01"
        )

        assert [r.legs[0].destination for r in results] == ["Ceres", "Venus", "Moon"]
        assert [r.total_duration_minutes for r in results] == [12 * 60, 12 * 60, 15 * 60]
        assert [r.total_price for r in results] == [1000000, 2000000, 1300000]
