"""End-to-end tests for multi-leg itineraries."""

import time

from helpers import seats_available


def test_search_create_confirm_itinerary_flow(client):
    """End-to-end multi-leg flow:
    1. Register user
    2. Search Earth to Europa on 2099-02-01 (finds 3-leg route)
    3. Create held itinerary
    4. Confirm itinerary
    5. Verify itinerary appears under user's itineraries (My trips)
    """
    # 1. Register a dedicated traveler
    email = f"itinerary_e2e_{int(time.time())}@galaxium.test"
    reg_resp = client.post("/register", json={"name": "Alice Explorer", "email": email})
    assert reg_resp.status_code == 200, reg_resp.text
    user = reg_resp.json()
    user_id = user["user_id"]
    user_name = user["name"]

    # 2. Search Earth to Europa on 2099-02-01
    search_resp = client.get(
        "/itineraries/search",
        params={"origin": "Earth", "destination": "Europa", "date": "2099-02-01"}
    )
    assert search_resp.status_code == 200, search_resp.text
    routes = search_resp.json()
    assert len(routes) >= 1, f"Expected at least one route to Europa, got: {routes}"
    route = routes[0]
    assert len(route["legs"]) == 3
    assert route["total_price"] == 5500000

    flight_ids = [leg["flight_id"] for leg in route["legs"]]

    # 3. Create held itinerary
    create_resp = client.post("/itineraries", json={
        "user_id": user_id,
        "name": user_name,
        "flight_ids": flight_ids
    })
    assert create_resp.status_code == 200, create_resp.text
    created_itin = create_resp.json()
    assert created_itin["status"] == "held"
    assert created_itin["total_price"] == 5500000
    assert len(created_itin["legs"]) == 3
    itin_id = created_itin["id"]

    # 4. Confirm itinerary
    confirm_resp = client.post(f"/itineraries/{itin_id}/confirm")
    assert confirm_resp.status_code == 200, confirm_resp.text
    confirmed_itin = confirm_resp.json()
    assert confirmed_itin["status"] == "confirmed"
    for leg in confirmed_itin["legs"]:
        assert leg["booking_id"] is not None

    # 5. List user itineraries
    list_resp = client.get(f"/users/{user_id}/itineraries")
    assert list_resp.status_code == 200, list_resp.text
    user_itineraries = list_resp.json()
    assert len(user_itineraries) == 1
    assert user_itineraries[0]["id"] == itin_id
    assert user_itineraries[0]["status"] == "confirmed"
    assert len(user_itineraries[0]["legs"]) == 3


def test_confirm_failure_rolls_back_itinerary(client, traveler):
    """A failed leg during confirmation rolls back the whole itinerary:
    1. Search Earth to Mars on 2099-03-01 (two legs via Moon)
    2. Create held itinerary
    3. Sell out the second leg by booking its economy seats via POST /book
    4. Confirm itinerary -> fails on leg 2 (HTTP 502, CONFIRM_FAILED)
    5. First leg's economy seat count is restored to its pre-confirm value
    6. Itinerary status is failed (not listed under user itineraries, re-confirm returns 409)
    """
    # 1. Search Earth to Mars on 2099-03-01
    search_resp = client.get(
        "/itineraries/search",
        params={"origin": "Earth", "destination": "Mars", "date": "2099-03-01"},
    )
    assert search_resp.status_code == 200, search_resp.text
    routes = search_resp.json()
    assert len(routes) >= 1, f"Expected at least one route to Mars, got: {routes}"
    route = routes[0]
    assert len(route["legs"]) == 2

    leg1_id = route["legs"][0]["flight_id"]
    leg2_id = route["legs"][1]["flight_id"]

    leg1_seats_before = seats_available(client, leg1_id, "economy")

    # 2. Create held itinerary
    create_resp = client.post(
        "/itineraries",
        json={
            "user_id": traveler["user_id"],
            "name": traveler["name"],
            "flight_ids": [leg1_id, leg2_id],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    created_itin = create_resp.json()
    assert created_itin["status"] == "held"
    itin_id = created_itin["id"]

    # 3. Sell out the second leg's economy seats through POST /book
    leg2_seats = seats_available(client, leg2_id, "economy")
    assert leg2_seats > 0
    for _ in range(leg2_seats):
        book_resp = client.post(
            "/book",
            json={
                "flight_id": leg2_id,
                "user_id": traveler["user_id"],
                "name": traveler["name"],
                "seat_class": "economy",
            },
        )
        assert book_resp.status_code == 200, book_resp.text
    assert seats_available(client, leg2_id, "economy") == 0

    # 4. Confirm itinerary -> fails on leg 2
    confirm_resp = client.post(f"/itineraries/{itin_id}/confirm")
    assert confirm_resp.status_code == 502, confirm_resp.text
    err_data = confirm_resp.json()
    assert err_data.get("detail", {}).get("error_code") == "CONFIRM_FAILED"

    # 5. First leg's economy seat count is back to its value before confirm
    assert seats_available(client, leg1_id, "economy") == leg1_seats_before

    # 6. Itinerary status is failed
    reconfirm_resp = client.post(f"/itineraries/{itin_id}/confirm")
    assert reconfirm_resp.status_code == 409
    detail = reconfirm_resp.json().get("detail", {})
    assert detail.get("error_code") == "INVALID_ITINERARY_STATE"
    assert "failed" in detail.get("details", "")

    list_resp = client.get(f"/users/{traveler['user_id']}/itineraries")
    assert list_resp.status_code == 200
    user_itins = list_resp.json()
    assert not any(itin["id"] == itin_id for itin in user_itins)
