import re

from sqlalchemy.orm import Session

from models import User
from schemas import ErrorResponse, UserOut


def is_valid_email(email: str) -> bool:
    """Check whether an email address has a valid format.

    Returns True if the address matches the expected pattern, otherwise False.
    """
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_pattern, email) is not None


def register_user(db: Session, name: str, email: str) -> UserOut | ErrorResponse:
    """Register a new user with a name and unique email.

    The email is lowercased before validation and storage.

    Returns the created user, or an ErrorResponse with error_code
    INVALID_EMAIL or EMAIL_EXISTS. Does not raise for these failures.
    """
    email = email.lower()
    
    if not is_valid_email(email):
        return ErrorResponse(
            error="Invalid email format",
            error_code="INVALID_EMAIL",
            details=f"Email '{email}' is not a valid email address. Please provide a valid email in the format: example@domain.com"
        )

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return ErrorResponse(
            error="Email already registered",
            error_code="EMAIL_EXISTS",
            details=f"Email '{email}' is already registered. A user with this email already exists in our system. If you're trying to access an existing account, use get_user with the correct name and email to get the user_id."
        )

    new_user = User(name=name, email=email)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return UserOut.model_validate(new_user)


def get_user(db: Session, name: str, email: str) -> UserOut | ErrorResponse:
    """Retrieve a user's information by name and email.

    The email is lowercased before lookup. Both name and email must match.

    Returns the user, or an ErrorResponse with error_code INVALID_EMAIL or
    USER_NOT_FOUND. Does not raise for these failures.
    """
    email = email.lower()
    
    if not is_valid_email(email):
        return ErrorResponse(
            error="Invalid email format",
            error_code="INVALID_EMAIL",
            details=f"Email '{email}' is not a valid email address. Please provide a valid email in the format: example@domain.com"
        )
    
    user = db.query(User).filter(User.name == name, User.email == email).first()
    if not user:
        return ErrorResponse(
            error="User not found",
            error_code="USER_NOT_FOUND",
            details=f"User not found with name '{name}' and email '{email}'. The user may not be registered in our system. Please check the spelling of both name and email, or register the user first."
        )
    return UserOut.model_validate(user)
    

def update_user(db: Session, user_id: int, name: str, email: str) -> UserOut | ErrorResponse:
    """Update an existing user's name and email.

    The new email is lowercased but not format-validated or checked for
    uniqueness.

    Returns the updated user, or an ErrorResponse with error_code
    USER_NOT_FOUND. Does not raise for this failure.
    """
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        return ErrorResponse(
            error="User not found",
            error_code="USER_NOT_FOUND",
            details=f"User with ID {user_id} not found"
        )
    
    # Update user fields without validation
    user.name = name
    user.email = email.lower()
    
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
