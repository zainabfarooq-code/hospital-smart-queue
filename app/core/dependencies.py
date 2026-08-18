from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.database import get_db
from app.models.user import User


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """
    Retrieve the authenticated user from a JWT access token.
    """

    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    subject = payload.get("sub")

    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing the user identifier.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user = db.execute(
            select(User).where(User.id == subject)
        ).scalar_one_or_none()
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identifier in authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with this token no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(required_role: str) -> Callable:
    """
    Create a dependency that restricts an endpoint to a specific role.
    """

    def role_dependency(
        current_user: CurrentUser,
    ) -> User:
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )

        return current_user

    return role_dependency


RequirePatient = Annotated[
    User,
    Depends(require_role("patient")),
]

RequireDoctor = Annotated[
    User,
    Depends(require_role("doctor")),
]

RequireAdmin = Annotated[
    User,
    Depends(require_role("admin")),
]

def require_doctor_or_admin(
    current_user: CurrentUser,
) -> User:
    """
    Allow only authenticated doctors or administrators.
    """
    if current_user.role not in {"doctor", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resource.",
        )

    return current_user


RequireDoctorOrAdmin = Annotated[
    User,
    Depends(require_doctor_or_admin),
]
