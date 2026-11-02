"""Tests for multi-leg itineraries: search, hold, confirm, list, seed, and migration."""

import sys
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Column, Integer, String, create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import init_db
from models import Base, Booking, Flight, Itinerary, ItineraryLeg, User
from schemas import ErrorResponse, ItineraryRequest
from seed import seed
from services import itinerary


class TestItinerarySearch:
    """Test itinerary search service and endpoints."""

    def test_search_earth_to_europa_seeded(self, db_session):
        """Earth to Europa on 2099-02-01 gives one three-leg route with price 5500000."""
        # Add the 3 legs
        db_session.add_all([
            Flight(
                origin="Earth", destination="Mars",
                departure_time="2099-02-01 09:00", arrival_time="2099-02-01 17:00",
                base_price=1000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
            ),
            Flight(
                origin="Mars", destination="Jupiter",
                departure_time="2099-02-02 13:00", arrival_time="2099-02-02 23:00",
                base_price=2500000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
            ),
            Flight(
                origin="Jupiter", destination="Europa",
                departure_time="2099-02-04 15:00", arrival_time="2099-02-04 19:00",
                base_price=2000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
            )
        ])
        db_session.commit()

        results = itinerary.search_itineraries(db_session, "Earth", "Europa", "2099-02-01")
        assert isinstance(results, list)
        assert len(results) == 1
        itin = results[0]
        assert len(itin.legs) == 3
        assert itin.total_price == 5500000
        assert itin.first_departure == "2099-02-01 09:00"
        assert itin.last_arrival == "2099-02-04 19:00"
        assert itin.legs[0].origin == "Earth"
        assert itin.legs[0].destination == "Mars"
        assert itin.legs[1].origin == "Mars"
        assert itin.legs[1].destination == "Jupiter"
        assert itin.legs[2].origin == "Jupiter"
        assert itin.legs[2].destination == "Europa"

    def test_search_earth_to_mars_via_moon(self, db_session):
        """Earth to Mars on 2099-03-01 returns a two-leg route via Moon."""
        db_session.add_all([
            Flight(
                origin="Earth", destination="Moon",
                departure_time="2099-03-01 08:00", arrival_time="2099-03-01 12:00",
                base_price=500000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
            ),
            Flight(
                origin="Moon", destination="Mars",
                departure_time="2099-03-01 16:00", arrival_time="2099-03-01 23:00",
                base_price=800000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
            )
        ])
        db_session.commit()

        results = itinerary.search_itineraries(db_session, "Earth", "Mars", "2099-03-01")
        assert len(results) == 1
        itin = results[0]
        assert len(itin.legs) == 2
        assert itin.total_price == 1300000
        assert itin.legs[0].destination == "Moon"
        assert itin.legs[1].destination == "Mars"

    def test_search_layover_limits(self, db_session):
        """Story 3 layover boundary tests: 1h59 (out), 2h (in), 72h (in), 72h01 (out)."""
        # First leg: Earth -> Mars arriving 2099-02-01 17:00
        db_session.add(Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-02-01 09:00", arrival_time="2099-02-01 17:00",
            base_price=1000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
        ))
        # Candidate 1: departs 18:59 (1h59m - invalid)
        db_session.add(Flight(
            origin="Mars", destination="Jupiter",
            departure_time="2099-02-01 18:59", arrival_time="2099-02-02 02:00",
            base_price=2000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
        ))
        # Candidate 2: departs 19:00 (2h00m - valid)
        db_session.add(Flight(
            origin="Mars", destination="Jupiter",
            departure_time="2099-02-01 19:00", arrival_time="2099-02-02 03:00",
            base_price=2100000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
        ))
        # Candidate 3: departs 72h later: 2099-02-04 17:00 (72h00m - valid)
        db_session.add(Flight(
            origin="Mars", destination="Jupiter",
            departure_time="2099-02-04 17:00", arrival_time="2099-02-05 01:00",
            base_price=2200000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
        ))
        # Candidate 4: departs 72h01m later: 2099-02-04 17:01 (invalid)
        db_session.add(Flight(
            origin="Mars", destination="Jupiter",
            departure_time="2099-02-04 17:01", arrival_time="2099-02-05 02:00",
            base_price=2300000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.commit()

        results = itinerary.search_itineraries(db_session, "Earth", "Jupiter", "2099-02-01")
        assert len(results) == 2
        departures = [r.legs[1].departure_time for r in results]
        assert "2099-02-01 19:00" in departures
        assert "2099-02-04 17:00" in departures
        assert "2099-02-01 18:59" not in departures
        assert "2099-02-04 17:01" not in departures

    def test_search_no_repeat_locations(self, db_session):
        """Itineraries must never visit the same location twice (e.g. Earth -> Mars -> Earth -> Jupiter)."""
        db_session.add_all([
            Flight(
                origin="Earth", destination="Mars",
                departure_time="2099-02-01 09:00", arrival_time="2099-02-01 17:00",
                base_price=1000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
            ),
            Flight(
                origin="Mars", destination="Earth",
                departure_time="2099-02-02 09:00", arrival_time="2099-02-02 17:00",
                base_price=1000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
            ),
            Flight(
                origin="Earth", destination="Jupiter",
                departure_time="2099-02-03 09:00", arrival_time="2099-02-03 17:00",
                base_price=2000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
            )
        ])
        db_session.commit()

        results = itinerary.search_itineraries(db_session, "Earth", "Jupiter", "2099-02-01")
        assert len(results) == 0

    def test_search_sold_out_legs_excluded(self, db_session):
        """Legs with 0 economy seats available are excluded from search results."""
        db_session.add_all([
            Flight(
                origin="Earth", destination="Mars",
                departure_time="2099-02-01 09:00", arrival_time="2099-02-01 17:00",
                base_price=1000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
            ),
            Flight(
                origin="Mars", destination="Jupiter",
                departure_time="2099-02-02 13:00", arrival_time="2099-02-02 23:00",
                base_price=2500000, economy_seats_available=0, business_seats_available=3, galaxium_seats_available=1
            ),
        ])
        db_session.commit()

        results = itinerary.search_itineraries(db_session, "Earth", "Jupiter", "2099-02-01")
        assert len(results) == 0

    def test_search_sort_order(self, db_session):
        """Results are sorted by total duration (minutes) ascending, then total price ascending."""
        db_session.add_all([
            # Route 1: 24h total duration, price 3000000
            Flight(
                origin="Earth", destination="Mars",
                departure_time="2099-02-01 09:00", arrival_time="2099-02-01 15:00",
                base_price=1500000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
            ),
            Flight(
                origin="Mars", destination="Jupiter",
                departure_time="2099-02-01 18:00", arrival_time="2099-02-02 09:00",
                base_price=1500000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
            ),
            # Route 2: 12h total duration, price 4000000
            Flight(
                origin="Earth", destination="Venus",
                departure_time="2099-02-01 09:00", arrival_time="2099-02-01 13:00",
                base_price=2000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
            ),
            Flight(
                origin="Venus", destination="Jupiter",
                departure_time="2099-02-01 16:00", arrival_time="2099-02-01 21:00",
                base_price=2000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
            ),
        ])
        db_session.commit()

        results = itinerary.search_itineraries(db_session, "Earth", "Jupiter", "2099-02-01")
        assert len(results) == 2
        # Shorter duration first
        assert results[0].total_duration_minutes < results[1].total_duration_minutes
        assert results[0].legs[0].destination == "Venus"

    def test_search_bad_date(self, db_session):
        """Invalid date format returns ErrorResponse INVALID_DATE."""
        result = itinerary.search_itineraries(db_session, "Earth", "Europa", "bad-date")
        assert isinstance(result, ErrorResponse)
        assert result.error_code == "INVALID_DATE"

    def test_search_rest_endpoint(self, client, db_session):
        """GET /itineraries/search via REST client."""
        db_session.add(Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-02-01 09:00", arrival_time="2099-02-01 17:00",
            base_price=1000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.commit()

        resp = client.get("/itineraries/search", params={"origin": "Earth", "destination": "Mars", "date": "2099-02-01"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["total_price"] == 1000000

        # Bad date returns 422
        bad_resp = client.get("/itineraries/search", params={"origin": "Earth", "destination": "Mars", "date": "invalid"})
        assert bad_resp.status_code == 422


class TestItineraryCreateAndConfirm:
    """Test creating and confirming itineraries with mock Java service."""

    @pytest.fixture
    def setup_data(self, db_session):
        """Setup user and 3 connected flights."""
        user = User(name="Alice", email="alice@example.com")
        db_session.add(user)
        f1 = Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-02-01 09:00", arrival_time="2099-02-01 17:00",
            base_price=1000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
        )
        f2 = Flight(
            origin="Mars", destination="Jupiter",
            departure_time="2099-02-02 13:00", arrival_time="2099-02-02 23:00",
            base_price=2500000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
        )
        f3 = Flight(
            origin="Jupiter", destination="Europa",
            departure_time="2099-02-04 15:00", arrival_time="2099-02-04 19:00",
            base_price=2000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
        )
        db_session.add_all([f1, f2, f3])
        db_session.commit()
        return user, [f1, f2, f3]

    def test_create_and_confirm_happy_path(self, db_session, monkeypatch, setup_data):
        """Happy path: create held itinerary, then confirm into bookings."""
        user, flights = setup_data
        quote_counter = 0
        hold_counter = 0
        booking_counter = 100

        def mock_handler(request: httpx.Request):
            nonlocal quote_counter, hold_counter, booking_counter
            url = str(request.url)
            if "/quotes" in url and "/holds" not in url and request.method == "POST":
                quote_counter += 1
                return httpx.Response(200, json={"quoteId": f"Q-{quote_counter}"})
            if "/holds" in url and request.method == "POST" and "/confirm" not in url and "/release" not in url:
                hold_counter += 1
                return httpx.Response(200, json={"holdId": f"H-{hold_counter}"})
            if "/confirm" in url and request.method == "POST":
                booking_counter += 1
                # Create the actual booking in the Python backend DB as the Java service would
                parts = url.split("/")
                hold_id = parts[parts.index("holds") + 1]
                leg = db_session.query(ItineraryLeg).filter(ItineraryLeg.hold_id == hold_id).first()
                fl = db_session.query(Flight).filter(Flight.flight_id == leg.flight_id).first()
                fl.economy_seats_available -= 1
                bk = Booking(
                    booking_id=booking_counter,
                    user_id=user.user_id,
                    flight_id=leg.flight_id,
                    status="booked",
                    booking_time="2099-02-01 10:00",
                    seat_class="economy",
                    price_paid=fl.base_price,
                )
                db_session.add(bk)
                db_session.commit()
                return httpx.Response(200, json={"holdId": hold_id, "externalBookingReference": str(booking_counter)})
            return httpx.Response(404)

        monkeypatch.setattr(itinerary, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(mock_handler)))

        req = ItineraryRequest(
            user_id=user.user_id,
            name=user.name,
            flight_ids=[f.flight_id for f in flights]
        )
        create_res = itinerary.create_itinerary(db_session, req)
        assert not isinstance(create_res, ErrorResponse)
        assert create_res.status == "held"
        assert len(create_res.legs) == 3

        confirm_res = itinerary.confirm_itinerary(db_session, create_res.id)
        assert not isinstance(confirm_res, ErrorResponse)
        assert confirm_res.status == "confirmed"
        for leg in confirm_res.legs:
            assert leg.booking_id is not None
            bk = db_session.query(Booking).filter(Booking.booking_id == leg.booking_id).first()
            assert bk.itinerary_id == create_res.id
            assert bk.status == "booked"

    def test_create_hold_failure_releases_earlier(self, db_session, monkeypatch, setup_data):
        """Hold failure at leg 2 releases leg 1 and returns HOLD_FAILED (502)."""
        user, flights = setup_data
        quote_counter = 0
        released_holds = []

        def mock_handler(request: httpx.Request):
            nonlocal quote_counter
            url = str(request.url)
            if "/quotes" in url and "/holds" not in url and request.method == "POST":
                quote_counter += 1
                return httpx.Response(200, json={"quoteId": f"Q-{quote_counter}"})
            if "/holds" in url and "/release" in url and request.method == "POST":
                parts = url.split("/")
                hold_id = parts[parts.index("holds") + 1]
                released_holds.append(hold_id)
                return httpx.Response(200, json={"status": "RELEASED"})
            if "/holds" in url and request.method == "POST":
                if quote_counter == 2:
                    return httpx.Response(500, json={"error": "Hold failed"})
                return httpx.Response(200, json={"holdId": f"H-{quote_counter}"})
            return httpx.Response(404)

        monkeypatch.setattr(itinerary, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(mock_handler)))

        req = ItineraryRequest(
            user_id=user.user_id,
            name=user.name,
            flight_ids=[f.flight_id for f in flights]
        )
        res = itinerary.create_itinerary(db_session, req)
        assert isinstance(res, ErrorResponse)
        assert res.error_code == "HOLD_FAILED"
        assert "H-1" in released_holds

        # Check failed itinerary recorded in DB
        failed_itin = db_session.query(Itinerary).filter(Itinerary.status == "failed").first()
        assert failed_itin is not None

    def test_create_validation_errors(self, db_session, setup_data):
        """Test name mismatch, invalid flight count, invalid connection, unknown user, sold out."""
        user, flights = setup_data

        # Name mismatch
        res1 = itinerary.create_itinerary(db_session, ItineraryRequest(
            user_id=user.user_id, name="Wrong", flight_ids=[flights[0].flight_id]
        ))
        assert isinstance(res1, ErrorResponse) and res1.error_code == "NAME_MISMATCH"

        # Unknown user
        res2 = itinerary.create_itinerary(db_session, ItineraryRequest(
            user_id=999, name="Alice", flight_ids=[flights[0].flight_id]
        ))
        assert isinstance(res2, ErrorResponse) and res2.error_code == "USER_NOT_FOUND"

        # Four flight ids
        res3 = itinerary.create_itinerary(db_session, ItineraryRequest(
            user_id=user.user_id, name=user.name, flight_ids=[1, 2, 3, 4]
        ))
        assert isinstance(res3, ErrorResponse) and res3.error_code == "INVALID_FLIGHT_COUNT"

        # Invalid connection
        res4 = itinerary.create_itinerary(db_session, ItineraryRequest(
            user_id=user.user_id, name=user.name, flight_ids=[flights[0].flight_id, flights[2].flight_id]
        ))
        assert isinstance(res4, ErrorResponse) and res4.error_code == "INVALID_CONNECTION"

        # Sold out flight
        flights[0].economy_seats_available = 0
        db_session.commit()
        res5 = itinerary.create_itinerary(db_session, ItineraryRequest(
            user_id=user.user_id, name=user.name, flight_ids=[flights[0].flight_id]
        ))
        assert isinstance(res5, ErrorResponse) and res5.error_code == "NO_SEATS_AVAILABLE"


class TestConfirmFailureCompensation:
    """Test compensation on confirmation failure across service and REST."""

    @pytest.fixture
    def setup_data(self, db_session):
        user = User(name="Alice", email="alice@example.com")
        db_session.add(user)
        f1 = Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-02-01 09:00", arrival_time="2099-02-01 17:00",
            base_price=1000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
        )
        f2 = Flight(
            origin="Mars", destination="Jupiter",
            departure_time="2099-02-02 13:00", arrival_time="2099-02-02 23:00",
            base_price=2500000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
        )
        f3 = Flight(
            origin="Jupiter", destination="Europa",
            departure_time="2099-02-04 15:00", arrival_time="2099-02-04 19:00",
            base_price=2000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
        )
        db_session.add_all([f1, f2, f3])
        db_session.commit()
        return user, [f1, f2, f3]

    def test_confirm_failure_leg3_compensates(self, client, db_session, monkeypatch, setup_data):
        """Confirm leg 1 and 2 succeed, leg 3 fails:
        - HTTP 502 with error_code CONFIRM_FAILED
        - itinerary status is failed
        - bookings for legs 1 and 2 have status cancelled
        - economy seats on legs 1 and 2 restored (delta is zero)
        - leg 3 seat count unchanged
        - release call received for leg 3 hold and NOT legs 1 and 2
        - itinerary not in GET /users/{user_id}/itineraries
        """
        user, flights = setup_data
        quote_counter = 0
        hold_counter = 0
        booking_counter = 200
        released_holds = []

        def mock_handler(request: httpx.Request):
            nonlocal quote_counter, hold_counter, booking_counter
            url = str(request.url)
            if "/quotes" in url and "/holds" not in url and request.method == "POST":
                quote_counter += 1
                return httpx.Response(200, json={"quoteId": f"Q-{quote_counter}"})
            if "/holds" in url and "/release" in url and request.method == "POST":
                parts = url.split("/")
                hold_id = parts[parts.index("holds") + 1]
                released_holds.append(hold_id)
                return httpx.Response(200, json={"status": "RELEASED"})
            if "/holds" in url and request.method == "POST" and "/confirm" not in url:
                hold_counter += 1
                return httpx.Response(200, json={"holdId": f"H-{hold_counter}"})
            if "/confirm" in url and request.method == "POST":
                parts = url.split("/")
                hold_id = parts[parts.index("holds") + 1]
                if hold_id == "H-3":
                    # Leg 3 fails confirm
                    return httpx.Response(400, json={"error": "Confirm failed"})
                booking_counter += 1
                leg = db_session.query(ItineraryLeg).filter(ItineraryLeg.hold_id == hold_id).first()
                fl = db_session.query(Flight).filter(Flight.flight_id == leg.flight_id).first()
                fl.economy_seats_available -= 1
                bk = Booking(
                    booking_id=booking_counter,
                    user_id=user.user_id,
                    flight_id=leg.flight_id,
                    status="booked",
                    booking_time="2099-02-01 10:00",
                    seat_class="economy",
                    price_paid=fl.base_price,
                )
                db_session.add(bk)
                db_session.commit()
                return httpx.Response(200, json={"holdId": hold_id, "externalBookingReference": str(booking_counter)})
            return httpx.Response(404)

        monkeypatch.setattr(itinerary, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(mock_handler)))

        init_seats_1 = flights[0].economy_seats_available
        init_seats_2 = flights[1].economy_seats_available
        init_seats_3 = flights[2].economy_seats_available

        # Create itinerary via REST
        create_resp = client.post("/itineraries", json={
            "user_id": user.user_id,
            "name": user.name,
            "flight_ids": [f.flight_id for f in flights]
        })
        assert create_resp.status_code == 200
        itin_id = create_resp.json()["id"]

        # Confirm via REST
        confirm_resp = client.post(f"/itineraries/{itin_id}/confirm")
        assert confirm_resp.status_code == 502
        err_detail = confirm_resp.json()["detail"]
        assert err_detail["error_code"] == "CONFIRM_FAILED"

        # Itinerary status is failed
        itin_db = db_session.query(Itinerary).filter(Itinerary.id == itin_id).first()
        assert itin_db.status == "failed"

        # Bookings for legs 1 and 2 are cancelled
        b1 = db_session.query(Booking).filter(Booking.booking_id == 201).first()
        b2 = db_session.query(Booking).filter(Booking.booking_id == 202).first()
        assert b1.status == "cancelled"
        assert b2.status == "cancelled"

        # Economy seats restored
        db_session.refresh(flights[0])
        db_session.refresh(flights[1])
        db_session.refresh(flights[2])
        assert flights[0].economy_seats_available == init_seats_1
        assert flights[1].economy_seats_available == init_seats_2
        assert flights[2].economy_seats_available == init_seats_3

        # Release called for H-3 and not H-1, H-2
        assert "H-3" in released_holds
        assert "H-1" not in released_holds
        assert "H-2" not in released_holds

        # Not in user's itineraries
        list_resp = client.get(f"/users/{user.user_id}/itineraries")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 0

    def test_confirm_failure_leg1_releases_all(self, client, db_session, monkeypatch, setup_data):
        """First leg fails confirm: no booking created, all holds released, status failed, 502."""
        user, flights = setup_data
        quote_counter = 0
        hold_counter = 0
        released_holds = []

        def mock_handler(request: httpx.Request):
            nonlocal quote_counter, hold_counter
            url = str(request.url)
            if "/quotes" in url and "/holds" not in url and request.method == "POST":
                quote_counter += 1
                return httpx.Response(200, json={"quoteId": f"Q-{quote_counter}"})
            if "/holds" in url and "/release" in url and request.method == "POST":
                parts = url.split("/")
                hold_id = parts[parts.index("holds") + 1]
                released_holds.append(hold_id)
                return httpx.Response(200, json={"status": "RELEASED"})
            if "/holds" in url and request.method == "POST" and "/confirm" not in url:
                hold_counter += 1
                return httpx.Response(200, json={"holdId": f"H-{hold_counter}"})
            if "/confirm" in url and request.method == "POST":
                return httpx.Response(500, json={"error": "Server error"})
            return httpx.Response(404)

        monkeypatch.setattr(itinerary, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(mock_handler)))

        create_resp = client.post("/itineraries", json={
            "user_id": user.user_id,
            "name": user.name,
            "flight_ids": [f.flight_id for f in flights]
        })
        itin_id = create_resp.json()["id"]

        confirm_resp = client.post(f"/itineraries/{itin_id}/confirm")
        assert confirm_resp.status_code == 502
        assert confirm_resp.json()["detail"]["error_code"] == "CONFIRM_FAILED"

        # Check holds H-1, H-2, H-3 were released
        assert set(released_holds) == {"H-1", "H-2", "H-3"}

        # No bookings exist
        assert db_session.query(Booking).count() == 0


class TestItineraryList:
    """Test listing user itineraries."""

    def test_list_itineraries_ordering_and_isolation(self, client, db_session):
        """User itineraries are sorted by first departure date, and separate users isolated."""
        u1 = User(name="Alice", email="alice@example.com")
        u2 = User(name="Bob", email="bob@example.com")
        db_session.add_all([u1, u2])
        db_session.commit()

        f1 = Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-02-10 09:00", arrival_time="2099-02-10 17:00",
            base_price=1000000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
        )
        f2 = Flight(
            origin="Earth", destination="Moon",
            departure_time="2099-02-01 08:00", arrival_time="2099-02-01 12:00",
            base_price=500000, economy_seats_available=6, business_seats_available=3, galaxium_seats_available=1
        )
        db_session.add_all([f1, f2])
        db_session.commit()

        # Itinerary 1: later departure (Feb 10)
        itin1 = Itinerary(user_id=u1.user_id, status="confirmed", total_price=1000000, created_at="2099-02-01T00:00:00Z")
        db_session.add(itin1)
        db_session.commit()
        db_session.add(ItineraryLeg(itinerary_id=itin1.id, position=0, flight_id=f1.flight_id, quote_id="Q-1", hold_id="H-1", booking_id=1))

        # Itinerary 2: earlier departure (Feb 1)
        itin2 = Itinerary(user_id=u1.user_id, status="confirmed", total_price=500000, created_at="2099-02-01T00:00:00Z")
        db_session.add(itin2)
        db_session.commit()
        db_session.add(ItineraryLeg(itinerary_id=itin2.id, position=0, flight_id=f2.flight_id, quote_id="Q-2", hold_id="H-2", booking_id=2))

        # Itinerary 3: failed (should not appear)
        itin3 = Itinerary(user_id=u1.user_id, status="failed", total_price=500000, created_at="2099-02-01T00:00:00Z")
        db_session.add(itin3)

        # Itinerary 4: for Bob
        itin4 = Itinerary(user_id=u2.user_id, status="confirmed", total_price=500000, created_at="2099-02-01T00:00:00Z")
        db_session.add(itin4)
        db_session.commit()
        db_session.add(ItineraryLeg(itinerary_id=itin4.id, position=0, flight_id=f2.flight_id, quote_id="Q-4", hold_id="H-4", booking_id=3))
        db_session.commit()

        # Alice trips
        resp_alice = client.get(f"/users/{u1.user_id}/itineraries")
        assert resp_alice.status_code == 200
        alice_data = resp_alice.json()
        assert len(alice_data) == 2
        # Earliest first: itin2 (Feb 1) before itin1 (Feb 10)
        assert alice_data[0]["id"] == itin2.id
        assert alice_data[1]["id"] == itin1.id

        # Bob trips
        resp_bob = client.get(f"/users/{u2.user_id}/itineraries")
        assert resp_bob.status_code == 200
        bob_data = resp_bob.json()
        assert len(bob_data) == 1
        assert bob_data[0]["id"] == itin4.id

        # Empty trips for user 999
        resp_empty = client.get("/users/999/itineraries")
        assert resp_empty.status_code == 200
        assert resp_empty.json() == []


class TestMigrationAndSeed:
    """Test database column migration and seeding."""

    def test_migration_adds_itinerary_id_column(self, tmp_path):
        """Test init_db() adds itinerary_id column to existing bookings table."""
        db_file = tmp_path / "test_migration.db"
        eng = create_engine(f"sqlite:///{db_file}")

        # Create old schema table for bookings without itinerary_id
        OldBase = declarative_base()

        class OldBooking(OldBase):
            __tablename__ = "bookings"
            booking_id = Column(Integer, primary_key=True, autoincrement=True)
            user_id = Column(Integer, nullable=False)
            flight_id = Column(Integer, nullable=False)
            status = Column(String, nullable=False)
            booking_time = Column(String, nullable=False)
            seat_class = Column(String, nullable=False, default="economy")
            price_paid = Column(Integer, nullable=False)

        OldBase.metadata.create_all(bind=eng)

        # Insert a sample row
        Session = sessionmaker(bind=eng)
        sess = Session()
        sess.add(OldBooking(
            user_id=1, flight_id=1, status="booked",
            booking_time="2099-01-01", seat_class="economy", price_paid=100
        ))
        sess.commit()
        sess.close()

        # Run init_db on the database
        init_db(target_engine=eng)

        # Verify itinerary_id column exists
        insp = inspect(eng)
        col_names = [c["name"] for c in insp.get_columns("bookings")]
        assert "itinerary_id" in col_names

        # Verify data survived
        with eng.connect() as conn:
            rows = conn.execute(text("SELECT booking_id, user_id, itinerary_id FROM bookings")).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == 1
            assert rows[0][2] is None

        # Run init_db second time (idempotency)
        init_db(target_engine=eng)
        insp2 = inspect(eng)
        col_names2 = [c["name"] for c in insp2.get_columns("bookings")]
        assert "itinerary_id" in col_names2

    def test_seed_new_flights_and_idempotency(self, db_session, monkeypatch):
        """Test seed() adds the new flights with 6 economy seats and seeding twice adds nothing."""
        # Use an empty engine for seed test
        test_engine = create_engine("sqlite:///:memory:")
        TestingSession = sessionmaker(bind=test_engine)

        monkeypatch.setattr("seed.engine", test_engine)
        monkeypatch.setattr("seed.SessionLocal", TestingSession)

        seed()

        sess = TestingSession()
        # Verify the connecting flights exist
        europa_flight = sess.query(Flight).filter(Flight.origin == "Jupiter", Flight.destination == "Europa").first()
        assert europa_flight is not None
        assert europa_flight.economy_seats_available == 6
        assert europa_flight.base_price == 2000000

        moon_mars_flight = sess.query(Flight).filter(Flight.origin == "Moon", Flight.destination == "Mars", Flight.departure_time.like("2099-03%")).first()
        assert moon_mars_flight is not None
        assert moon_mars_flight.economy_seats_available == 6

        flight_count_after_first_seed = sess.query(Flight).count()
        sess.close()

        # Seed again
        seed()
        sess2 = TestingSession()
        assert sess2.query(Flight).count() == flight_count_after_first_seed
        sess2.close()
