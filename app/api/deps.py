"""FastAPI dependencies: access to the container and admin authentication."""
import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

from app.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def require_admin(
    x_admin_api_key: Optional[str] = Header(None, alias="X-Admin-API-Key"),
    container: Container = Depends(get_container),
) -> bool:
    expected = container.settings.admin_api_key
    if not x_admin_api_key or not secrets.compare_digest(x_admin_api_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorized: Missing or invalid 'X-Admin-API-Key' header.")
    return True
