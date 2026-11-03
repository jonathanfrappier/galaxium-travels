"""Itinerary search utilities for Galaxium Travels."""

from datetime import datetime, timezone
from models import Flight


def parse_time(value: str) -> datetime:
    """Parse a time string into a datetime object.

    Accepts both ISO 8601 format (e.g. '2099-02-01T09:00:00Z') and
    space-separated format (e.g. '2099-02-01 09:00').

    Args:
        value: The time string to parse.

    Returns:
        A datetime object representing the given time.
    """
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unrecognised time format: {value!r}")


def is_valid_connection(arriving: Flight, departing: Flight) -> bool:
    """Determine whether two flights form a valid connection.

    A connection is valid when:
    - ``departing.origin`` matches ``arriving.destination`` (case-insensitive).
    - ``departing.departure_time`` is between 2 and 72 hours (inclusive) after
      ``arriving.arrival_time``.

    Args:
        arriving: The inbound flight.
        departing: The outbound (connecting) flight.

    Returns:
        True if the flights form a valid connection, False otherwise.
    """
    if departing.origin.strip().lower() != arriving.destination.strip().lower():
        return False

    arrival_dt = parse_time(arriving.arrival_time)
    departure_dt = parse_time(departing.departure_time)

    layover_hours = (departure_dt - arrival_dt).total_seconds() / 3600
    return 2 <= layover_hours <= 72
