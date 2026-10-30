# Booking through the hold service

This sequence diagram shows a traveler requesting a quote, placing a hold, and confirming it, including the callback from the Java hold service to `/internal/bookings/from-hold` that creates the Python booking.

```mermaid
sequenceDiagram
    autonumber
    actor T as Traveler
    participant FE as Frontend<br/>(BookingModal + api.ts)
    participant PY as Python backend :8001<br/>(server.py)
    participant QC as Java QuoteController<br/>:8080
    participant HC as Java HoldController
    participant HS as Java HoldService
    participant PC as PythonBackendClient
    participant BK as booking.book_flight<br/>(services/booking.py)
    participant DB as Booking DB

    Note over FE,PY: Vite proxy strips /api, so /api/* reaches :8001/*

    rect rgb(235, 245, 255)
    Note over T,QC: 1. Quote
    T->>FE: Select flight + seat class, "Get quote"
    FE->>PY: POST /api/quotes (createQuote)<br/>{flightId, seatClass, quantity, travelerId, travelerName}
    PY->>QC: POST /api/v1/quotes (httpx, 30s timeout)
    QC->>QC: QuoteService.createQuote<br/>price via PricingService, expires in 24h
    QC-->>PY: 201 Quote {quoteId, pricePerSeat, totalPrice}
    PY-->>FE: Quote JSON
    FE-->>T: Show quote
    end

    rect rgb(240, 255, 240)
    Note over T,HS: 2. Hold
    T->>FE: "Place hold"
    FE->>PY: POST /api/quotes/{quoteId}/holds (createHold)
    PY->>HC: POST /api/v1/quotes/{quoteId}/holds
    HC->>HS: createHold(quoteId)
    HS->>HS: Quote exists and not expired?<br/>Save Hold status=HELD, reservedUntil = now+15m
    HS-->>HC: Hold
    HC-->>PY: 201 Hold {holdId, reservedUntil}
    PY-->>FE: Hold JSON
    FE->>FE: storeHold() in localStorage
    FE-->>T: "Seat held! 15 minutes to confirm"
    Note right of HS: No seat is decremented yet.<br/>Python is not contacted.
    end

    rect rgb(255, 248, 235)
    Note over T,DB: 3. Confirm and callback
    T->>FE: "Confirm booking"
    FE->>PY: POST /api/holds/{holdId}/confirm (confirmHold)
    PY->>HC: POST /api/v1/holds/{holdId}/confirm
    HC->>HS: confirmHold(holdId)
    HS->>HS: Status is HELD and not past reservedUntil?<br/>Load Quote
    HS->>PC: createBookingFromHold({travelerId, travelerName, flightId, seatClass})
    PC->>PY: POST /internal/bookings/from-hold (30s timeout)
    PY->>BK: create_booking_from_hold → book_flight(db, user_id, name, flight_id, seat_class)
    BK->>BK: Validate seat class, flight, seats available, user ID + name match
    alt booking succeeds
        BK->>DB: Decrement seat counter, insert Booking status="booked"
        BK-->>PY: BookingOut
        PY-->>PC: 200 {booking_id, user_id, flight_id, seat_class, status}
        PC-->>HS: BookingResponse
        HS->>HS: Hold status=CONFIRMED<br/>externalBookingReference = booking_id<br/>audit event CONFIRMED
        HS-->>HC: Hold
        HC-->>PY: 200 Hold
        PY-->>FE: Hold JSON
        FE->>FE: removeHold() from localStorage
        FE-->>T: "Booking confirmed! Reference #booking_id"
    else book_flight returns ErrorResponse
        BK-->>PY: ErrorResponse (e.g. NO_SEATS_AVAILABLE, NAME_MISMATCH)
        PY-->>PC: HTTP 400 {error, error_code, details}
        PC-->>HS: throws BookingCreationException
        HS->>HS: Hold status=CONFIRMATION_FAILED<br/>store errorMessage, audit event
        HS-->>HC: throws IllegalStateException
        HC-->>PY: 400 (empty body)
        PY-->>FE: HTTP 200 {"error": "Failed to confirm hold: ..."}
        FE->>FE: assertNotProxyError throws
        FE-->>T: "Failed to confirm booking"
    end
    end
```
