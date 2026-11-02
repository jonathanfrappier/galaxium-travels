"""End-to-end tests for multi-leg itineraries."""

import time


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
