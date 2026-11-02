"""Itinerary service for Galaxium Travels multi-leg bookings."""

from datetime import datetime, timezone
import logging
import os

import httpx
from sqlalchemy.orm import Session

from models import Booking, Flight, Itinerary, ItineraryLeg, User
from schemas import (
    ErrorResponse,
    FlightOut,
    ItineraryLegOut,
    ItineraryOut,
    ItineraryRequest,
    ItinerarySearchResult,
)
from services import booking
from services.itinerary_search import is_valid_connection, parse_time

logger = logging.getLogger(__name__)

JAVA_SERVICE_URL = os.getenv("JAVA_SERVICE_URL", "http://localhost:8080")


def get_http_client() -> httpx.Client:
    """Create and return an HTTP client with configured timeout."""
    return httpx.Client(timeout=30.0)


def _flight_to_out(f: Flight) -> FlightOut:
    """Convert a Flight DB model to a FlightOut schema with computed prices."""
    return FlightOut(
        flight_id=f.flight_id,
        origin=f.origin,
        destination=f.destination,
        departure_time=f.departure_time,
        arrival_time=f.arrival_time,
        base_price=f.base_price,
        economy_seats_available=f.economy_seats_available,
        business_seats_available=f.business_seats_available,
        galaxium_seats_available=f.galaxium_seats_available,
        economy_price=f.base_price,
        business_price=int(f.base_price * 2.5),
        galaxium_price=f.base_price * 5,
    )


def _itinerary_to_out(db: Session, itinerary: Itinerary) -> ItineraryOut:
    """Convert an Itinerary DB model to an ItineraryOut schema."""
    legs = (
        db.query(ItineraryLeg)
        .filter(ItineraryLeg.itinerary_id == itinerary.id)
        .order_by(ItineraryLeg.position.asc())
        .all()
    )
    legs_out = []
    for leg in legs:
        flight = db.query(Flight).filter(Flight.flight_id == leg.flight_id).first()
        flight_out = _flight_to_out(flight) if flight else None
        legs_out.append(
            ItineraryLegOut(
                id=leg.id,
                itinerary_id=leg.itinerary_id,
                position=leg.position,
                flight_id=leg.flight_id,
                quote_id=leg.quote_id,
                hold_id=leg.hold_id,
                booking_id=leg.booking_id,
                flight=flight_out,
            )
        )
    return ItineraryOut(
        id=itinerary.id,
        user_id=itinerary.user_id,
        status=itinerary.status,
        total_price=itinerary.total_price,
        created_at=itinerary.created_at,
        legs=legs_out,
    )


def search_itineraries(
    db: Session, origin: str, destination: str, date: str
) -> list[ItinerarySearchResult] | ErrorResponse:
    """Search for 1 to 3 leg flight itineraries from origin to destination on date.

    Date refers to the UTC departure date of the first leg in YYYY-MM-DD format.
    Returns a list of search results sorted by total duration and then total price,
    or an ErrorResponse with error_code INVALID_DATE on invalid date format.
    Does not raise for expected failures.
    """
    try:
        # Validate date format YYYY-MM-DD
        datetime.strptime(date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return ErrorResponse(
            error="Invalid date format",
            error_code="INVALID_DATE",
            details="The search date must be formatted as YYYY-MM-DD.",
        )

    norm_origin = origin.strip().lower()
    norm_destination = destination.strip().lower()

    # Load candidate flights with economy seats
    all_flights = db.query(Flight).filter(Flight.economy_seats_available > 0).all()

    first_leg_candidates = [
        f
        for f in all_flights
        if f.origin.strip().lower() == norm_origin
        and parse_time(f.departure_time).strftime("%Y-%m-%d") == date
    ]

    valid_chains: list[list[Flight]] = []

    # 1. Direct flights (1 leg)
    for f1 in first_leg_candidates:
        if f1.destination.strip().lower() == norm_destination:
            valid_chains.append([f1])

    # 2. 2-leg itineraries
    for f1 in first_leg_candidates:
        for f2 in all_flights:
            if f2.flight_id == f1.flight_id:
                continue
            if f2.destination.strip().lower() != norm_destination:
                continue
            # Check repeat locations
            locations = [f1.origin.strip().lower(), f1.destination.strip().lower(), f2.destination.strip().lower()]
            if len(set(locations)) != 3:
                continue
            if is_valid_connection(f1, f2):
                valid_chains.append([f1, f2])

    # 3. 3-leg itineraries
    for f1 in first_leg_candidates:
        for f2 in all_flights:
            if f2.flight_id == f1.flight_id:
                continue
            if not is_valid_connection(f1, f2):
                continue
            for f3 in all_flights:
                if f3.flight_id in (f1.flight_id, f2.flight_id):
                    continue
                if f3.destination.strip().lower() != norm_destination:
                    continue
                # Check repeat locations
                locations = [
                    f1.origin.strip().lower(),
                    f1.destination.strip().lower(),
                    f2.destination.strip().lower(),
                    f3.destination.strip().lower(),
                ]
                if len(set(locations)) != 4:
                    continue
                if is_valid_connection(f2, f3):
                    valid_chains.append([f1, f2, f3])

    results: list[ItinerarySearchResult] = []
    for chain in valid_chains:
        first_dep_dt = parse_time(chain[0].departure_time)
        last_arr_dt = parse_time(chain[-1].arrival_time)
        duration_minutes = int((last_arr_dt - first_dep_dt).total_seconds() / 60)
        total_price = sum(f.base_price for f in chain)

        results.append(
            ItinerarySearchResult(
                legs=[_flight_to_out(f) for f in chain],
                total_price=total_price,
                total_duration_minutes=duration_minutes,
                first_departure=chain[0].departure_time,
                last_arrival=chain[-1].arrival_time,
            )
        )

    # Sort by total duration (minutes), then total price
    results.sort(key=lambda r: (r.total_duration_minutes, r.total_price))
    return results


def create_itinerary(
    db: Session, request: ItineraryRequest
) -> ItineraryOut | ErrorResponse:
    """Create a held itinerary with 1 to 3 legs using the Java hold service.

    Validates user, name, flight count, connections, and available economy seats
    before contacting the Java hold service. Per leg, creates a quote and a hold.
    On failure, releases all holds created so far, marks the itinerary as failed,
    and returns HOLD_FAILED.

    Returns the held itinerary, or an ErrorResponse with error_code
    INVALID_FLIGHT_COUNT, USER_NOT_FOUND, NAME_MISMATCH, FLIGHT_NOT_FOUND,
    INVALID_CONNECTION, NO_SEATS_AVAILABLE, or HOLD_FAILED.
    Does not raise for expected failures.
    """
    if len(request.flight_ids) < 1 or len(request.flight_ids) > 3:
        return ErrorResponse(
            error="Invalid flight count",
            error_code="INVALID_FLIGHT_COUNT",
            details="Itinerary must contain 1 to 3 flights.",
        )

    # Check user exists and name matches
    user = (
        db.query(User)
        .filter(User.user_id == request.user_id, User.name == request.name)
        .first()
    )
    if not user:
        existing_user = db.query(User).filter(User.user_id == request.user_id).first()
        if existing_user:
            return ErrorResponse(
                error="Name mismatch",
                error_code="NAME_MISMATCH",
                details=f"User ID {request.user_id} exists but name '{request.name}' does not match registered name '{existing_user.name}'.",
            )
        return ErrorResponse(
            error="User not found",
            error_code="USER_NOT_FOUND",
            details=f"User with ID {request.user_id} is not registered in our system.",
        )

    # Validate flights exist
    flights: list[Flight] = []
    flights_by_id = {}
    for fid in request.flight_ids:
        fl = db.query(Flight).filter(Flight.flight_id == fid).first()
        if not fl:
            return ErrorResponse(
                error="Flight not found",
                error_code="FLIGHT_NOT_FOUND",
                details=f"Flight with ID {fid} does not exist.",
            )
        flights.append(fl)
        flights_by_id[fid] = fl

    # Validate connections between successive legs
    for i in range(len(flights) - 1):
        if not is_valid_connection(flights[i], flights[i + 1]):
            return ErrorResponse(
                error="Invalid connection",
                error_code="INVALID_CONNECTION",
                details=f"Flights {flights[i].flight_id} and {flights[i + 1].flight_id} do not form a valid connection.",
            )

    # Check economy seats available on every leg
    for fl in flights:
        if fl.economy_seats_available < 1:
            return ErrorResponse(
                error="No economy seats available",
                error_code="NO_SEATS_AVAILABLE",
                details=f"Flight {fl.flight_id} has no available seats in economy class.",
            )

    total_price = sum(fl.base_price for fl in flights)
    held_quotes_and_holds: list[tuple[int, int, str, str]] = []  # (pos, flight_id, quote_id, hold_id)

    client = get_http_client()
    hold_error = False
    try:
        for idx, fl in enumerate(flights):
            quote_payload = {
                "flightId": fl.flight_id,
                "seatClass": "economy",
                "quantity": 1,
                "travelerId": request.user_id,
                "travelerName": request.name,
            }
            q_resp = client.post(f"{JAVA_SERVICE_URL}/api/v1/quotes", json=quote_payload)
            if q_resp.status_code >= 300 or "quoteId" not in q_resp.json():
                hold_error = True
                break
            quote_id = q_resp.json()["quoteId"]

            h_resp = client.post(f"{JAVA_SERVICE_URL}/api/v1/quotes/{quote_id}/holds")
            if h_resp.status_code >= 300 or "holdId" not in h_resp.json():
                hold_error = True
                break
            hold_id = h_resp.json()["holdId"]

            held_quotes_and_holds.append((idx, fl.flight_id, quote_id, hold_id))
    except Exception as exc:
        logger.warning("Java hold service error: %s", exc)
        hold_error = True

    if hold_error:
        # Release holds already created
        for _, _, _, h_id in held_quotes_and_holds:
            try:
                client.post(f"{JAVA_SERVICE_URL}/api/v1/holds/{h_id}/release")
            except Exception as rel_err:
                logger.warning("Failed to release hold %s: %s", h_id, rel_err)
        client.close()

        failed_itinerary = Itinerary(
            user_id=request.user_id,
            status="failed",
            total_price=total_price,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
        )
        db.add(failed_itinerary)
        db.commit()
        db.refresh(failed_itinerary)

        for pos, fid, qid, hid in held_quotes_and_holds:
            db.add(
                ItineraryLeg(
                    itinerary_id=failed_itinerary.id,
                    position=pos,
                    flight_id=fid,
                    quote_id=qid,
                    hold_id=hid,
                )
            )
        db.commit()

        return ErrorResponse(
            error="Failed to hold itinerary legs",
            error_code="HOLD_FAILED",
            details="Could not secure inventory holds for all flights in the itinerary.",
        )

    client.close()

    itinerary = Itinerary(
        user_id=request.user_id,
        status="held",
        total_price=total_price,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )
    db.add(itinerary)
    db.commit()
    db.refresh(itinerary)

    legs_out = []
    for pos, fid, qid, hid in held_quotes_and_holds:
        leg = ItineraryLeg(
            itinerary_id=itinerary.id,
            position=pos,
            flight_id=fid,
            quote_id=qid,
            hold_id=hid,
        )
        db.add(leg)
        db.commit()
        db.refresh(leg)
        fl = flights_by_id[fid]
        legs_out.append(
            ItineraryLegOut(
                id=leg.id,
                itinerary_id=itinerary.id,
                position=leg.position,
                flight_id=leg.flight_id,
                quote_id=leg.quote_id,
                hold_id=leg.hold_id,
                booking_id=leg.booking_id,
                flight=_flight_to_out(fl),
            )
        )

    return ItineraryOut(
        id=itinerary.id,
        user_id=itinerary.user_id,
        status=itinerary.status,
        total_price=itinerary.total_price,
        created_at=itinerary.created_at,
        legs=legs_out,
    )


def confirm_itinerary(db: Session, itinerary_id: int) -> ItineraryOut | ErrorResponse:
    """Confirm a held itinerary by confirming all its leg holds in the Java service.

    On confirmation failure on any leg:
    1. Cancels already confirmed legs with booking.cancel_booking(db, booking_id).
    2. Releases holds of the failing leg and subsequent legs.
    3. Sets itinerary status to 'failed'.
    4. Returns CONFIRM_FAILED.

    Returns the confirmed itinerary, or an ErrorResponse with error_code
    ITINERARY_NOT_FOUND, INVALID_ITINERARY_STATE, or CONFIRM_FAILED.
    Does not raise for expected failures.
    """
    itinerary = db.query(Itinerary).filter(Itinerary.id == itinerary_id).first()
    if not itinerary:
        return ErrorResponse(
            error="Itinerary not found",
            error_code="ITINERARY_NOT_FOUND",
            details=f"Itinerary with ID {itinerary_id} not found.",
        )

    if itinerary.status == "confirmed":
        return _itinerary_to_out(db, itinerary)

    if itinerary.status != "held":
        return ErrorResponse(
            error="Invalid itinerary state",
            error_code="INVALID_ITINERARY_STATE",
            details=f"Itinerary {itinerary_id} is in status '{itinerary.status}' and cannot be confirmed.",
        )

    legs = (
        db.query(ItineraryLeg)
        .filter(ItineraryLeg.itinerary_id == itinerary_id)
        .order_by(ItineraryLeg.position.asc())
        .all()
    )

    confirmed_legs: list[tuple[ItineraryLeg, int]] = []  # (leg, booking_id)
    failed_idx: int | None = None
    client = get_http_client()

    for idx, leg in enumerate(legs):
        try:
            resp = client.post(f"{JAVA_SERVICE_URL}/api/v1/holds/{leg.hold_id}/confirm")
            if resp.status_code >= 300:
                failed_idx = idx
                break
            data = resp.json()
            ref = data.get("externalBookingReference")
            if not ref:
                failed_idx = idx
                break
            booking_id = int(ref)
            leg.booking_id = booking_id

            # Tag the booking with the itinerary_id
            bk = db.query(Booking).filter(Booking.booking_id == booking_id).first()
            if bk:
                bk.itinerary_id = itinerary.id
            db.commit()
            confirmed_legs.append((leg, booking_id))
        except Exception as exc:
            logger.warning("Confirm hold failed on leg %s (hold %s): %s", leg.id, leg.hold_id, exc)
            failed_idx = idx
            break

    if failed_idx is not None:
        # 1. Cancel confirmed bookings to restore seats
        for c_leg, b_id in confirmed_legs:
            try:
                booking.cancel_booking(db, b_id)
            except Exception as c_err:
                logger.warning(
                    "Compensation: failed to cancel booking %s for leg %s: %s",
                    b_id,
                    c_leg.id,
                    c_err,
                )
        # 2. Release unconfirmed / failing holds
        for unconf_leg in legs[failed_idx:]:
            try:
                client.post(f"{JAVA_SERVICE_URL}/api/v1/holds/{unconf_leg.hold_id}/release")
            except Exception as rel_err:
                logger.warning(
                    "Compensation: failed to release hold %s for leg %s: %s",
                    unconf_leg.hold_id,
                    unconf_leg.id,
                    rel_err,
                )
        client.close()

        # 3. Mark itinerary as failed
        itinerary.status = "failed"
        db.commit()

        # 4. Return CONFIRM_FAILED
        return ErrorResponse(
            error="Failed to confirm itinerary",
            error_code="CONFIRM_FAILED",
            details="One or more flight holds could not be confirmed.",
        )

    client.close()
    itinerary.status = "confirmed"
    db.commit()
    db.refresh(itinerary)
    return _itinerary_to_out(db, itinerary)


def get_user_itineraries(db: Session, user_id: int) -> list[ItineraryOut]:
    """Retrieve all confirmed itineraries for a specific user, ordered by first departure."""
    itineraries = (
        db.query(Itinerary)
        .filter(Itinerary.user_id == user_id, Itinerary.status == "confirmed")
        .all()
    )

    result_tuples = []
    for itin in itineraries:
        first_leg = (
            db.query(ItineraryLeg)
            .filter(ItineraryLeg.itinerary_id == itin.id, ItineraryLeg.position == 0)
            .first()
        )
        if first_leg:
            fl = db.query(Flight).filter(Flight.flight_id == first_leg.flight_id).first()
            dep_time = parse_time(fl.departure_time) if fl else datetime.min.replace(tzinfo=timezone.utc)
        else:
            dep_time = datetime.min.replace(tzinfo=timezone.utc)
        result_tuples.append((dep_time, _itinerary_to_out(db, itin)))

    result_tuples.sort(key=lambda t: t[0])
    return [itin_out for _, itin_out in result_tuples]
