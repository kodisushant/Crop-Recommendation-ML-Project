"""Account and history HTTP endpoints; ownership always comes from the session."""
import logging
import os
import re
from functools import lru_cache
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError, PyMongoError

from .accounts import AccountStore, SESSION_SECONDS
from .database import get_database, close_database
from .history_store import HistoryStore

router = APIRouter(prefix="/api", tags=["Accounts and history"])
log = logging.getLogger("crop-advisor.history")
COOKIE = "crop_session"
UNAVAILABLE = "Account and history storage is unavailable. Please try again."


@lru_cache(maxsize=1)
def get_accounts():
    return AccountStore(get_database())


@lru_cache(maxsize=1)
def get_history():
    return HistoryStore(get_database())


def close_storage():
    get_accounts.cache_clear()
    get_history.cache_clear()
    close_database()


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)


def require_same_origin(request: Request):
    # A cross-site HTML form cannot send this header. No cross-origin CORS
    # permission is enabled. Also reject an explicit foreign Origin.
    if request.headers.get("X-Crop-Request") != "1":
        raise HTTPException(403, "Please reload the page and try again.")
    origin = request.headers.get("origin")
    if origin:
        source, target = urlsplit(origin), urlsplit(str(request.base_url))
        if (source.scheme, source.netloc) != (target.scheme, target.netloc):
            raise HTTPException(403, "Please reload the page and try again.")


def optional_user(request: Request):
    token = request.cookies.get(COOKIE, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return None
    return get_accounts().find_user(token)


def require_user(request: Request):
    try:
        user = optional_user(request)
    except PyMongoError:
        raise HTTPException(503, UNAVAILABLE) from None
    if not user:
        raise HTTPException(401, "Sign in to view your history.")
    return user


def begin_session(request, response, user):
    old_token = request.cookies.get(COOKIE)
    if old_token:
        get_accounts().logout(old_token)
    token = get_accounts().create_session(user["_id"])
    secure = request.url.scheme == "https" or os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=secure, samesite="lax", path="/")
    return {"user": get_accounts().public_user(user)}


def check_attempt(request, action, username):
    address = request.client.host if request.client else "unknown"
    if not get_accounts().allow_attempt(address, action, username.casefold()):
        raise HTTPException(429, "Too many sign-in attempts. Please try again later.")


@router.post("/auth/register", status_code=201, dependencies=[Depends(require_same_origin)])
def register(data: Credentials, request: Request, response: Response):
    try:
        check_attempt(request, "register", data.username)
        user = get_accounts().register(data.username, data.password)
        return begin_session(request, response, user)
    except DuplicateKeyError:
        raise HTTPException(409, "This username is already taken.") from None
    except PyMongoError:
        raise HTTPException(503, UNAVAILABLE) from None


@router.post("/auth/login", dependencies=[Depends(require_same_origin)])
def login(data: Credentials, request: Request, response: Response):
    try:
        check_attempt(request, "login", data.username)
        user = get_accounts().authenticate(data.username, data.password)
        if not user:
            raise HTTPException(401, "Incorrect username or password.")
        return begin_session(request, response, user)
    except PyMongoError:
        raise HTTPException(503, UNAVAILABLE) from None


@router.get("/auth/me")
def me(request: Request):
    try:
        user = optional_user(request)
        return {"user": get_accounts().public_user(user) if user else None}
    except PyMongoError:
        raise HTTPException(503, UNAVAILABLE) from None


@router.post("/auth/logout", dependencies=[Depends(require_same_origin)])
def logout(request: Request, response: Response):
    try:
        token = request.cookies.get(COOKIE)
        if token:
            get_accounts().logout(token)
    except PyMongoError:
        # Do not claim a server session was revoked if storage is unavailable.
        raise HTTPException(503, UNAVAILABLE) from None
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/history")
def history_list(user=Depends(require_user), limit: int = Query(20, ge=1, le=50), before: str | None = None):
    try:
        return get_history().list(str(user["_id"]), limit, before)
    except ValueError:
        raise HTTPException(400, "Invalid history record ID") from None
    except PyMongoError:
        raise HTTPException(503, UNAVAILABLE) from None


@router.get("/history/{record_id}")
def history_detail(record_id: str, user=Depends(require_user)):
    try:
        record = get_history().get(str(user["_id"]), record_id)
    except ValueError:
        raise HTTPException(404, "History entry not found.") from None
    except PyMongoError:
        raise HTTPException(503, UNAVAILABLE) from None
    if not record:
        raise HTTPException(404, "History entry not found.")
    return record


@router.delete("/history/{record_id}", dependencies=[Depends(require_same_origin)])
def history_delete(record_id: str, user=Depends(require_user)):
    try:
        deleted = get_history().delete(str(user["_id"]), record_id)
    except ValueError:
        raise HTTPException(404, "History entry not found.") from None
    except PyMongoError:
        raise HTTPException(503, UNAVAILABLE) from None
    if not deleted:
        raise HTTPException(404, "History entry not found.")
    return {"deleted": True}


def save_prediction_history(request, inputs, result):
    """Database failures must not discard an otherwise valid model response."""
    try:
        user = optional_user(request)
        if not user:
            return {"saved": False, "reason": "sign_in_required"}
        source = request.headers.get("X-Activity-Source", "recommendation")
        if source not in ("recommendation", "soil-analysis"):
            source = "recommendation"
        record_id = get_history().save(str(user["_id"]), inputs, result, source)
        return {"saved": True, "id": record_id}
    except PyMongoError:
        log.warning("Prediction returned but its history could not be saved")
        return {"saved": False, "reason": "storage_unavailable"}
