from fastapi import Header, HTTPException, status

from .config import get_settings


def require_write_key(x_a2a_api_key: str | None = Header(default=None)) -> str:
    configured = get_settings().dev_api_key
    if not configured or x_a2a_api_key != configured:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "A2A_UNAUTHORIZED", "message": "A valid X-A2A-API-Key is required."})
    return "development-api-key"
