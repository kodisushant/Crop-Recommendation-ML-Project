"""Ordinary user accounts and revocable, server-side login sessions.

Passwords use Argon2id. The browser gets a random HttpOnly session cookie;
MongoDB stores only its hash. Registering never grants an administrator role.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from threading import Lock

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from pymongo import ReturnDocument

PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_PASSWORD = PASSWORDS.hash(secrets.token_urlsafe(32))
SESSION_SECONDS = 7 * 24 * 60 * 60


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AccountStore:
    def __init__(self, database):
        self.users = database["users"]
        self.sessions = database["sessions"]
        self.attempts = database["auth_attempts"]
        self._indexed = False
        self._lock = Lock()

    def ensure_indexes(self):
        if self._indexed:
            return
        with self._lock:
            if not self._indexed:
                self.users.create_index("username_key", unique=True)
                self.sessions.create_index("expires_at", expireAfterSeconds=0)
                self.attempts.create_index("expires_at", expireAfterSeconds=0)
                self._indexed = True

    def allow_attempt(self, address, action, username=""):
        """Bound password work using shared MongoDB counters, even across workers."""
        self.ensure_indexes()
        now = datetime.now(timezone.utc)
        bucket = int(now.timestamp()) // 900
        limits = [(f"{address}:{action}:{bucket}", 50 if action == "login" else 10)]
        if action == "login":
            limits.append((f"{address}:{action}:{username}:{bucket}", 10))
        for key, limit in limits:
            attempt = self.attempts.find_one_and_update(
                {"_id": token_hash(key)},
                {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": now + timedelta(minutes=30)}},
                upsert=True, return_document=ReturnDocument.AFTER,
            )
            if attempt["count"] > limit:
                return False
        return True

    @staticmethod
    def public_user(user):
        return {"id": str(user["_id"]), "username": user["username"], "role": "user"}

    def register(self, username, password):
        self.ensure_indexes()
        user = {"username": username, "username_key": username.casefold(),
                "password_hash": PASSWORDS.hash(password), "role": "user",
                "created_at": datetime.now(timezone.utc)}
        inserted = self.users.insert_one(user)
        user["_id"] = inserted.inserted_id
        return user

    def authenticate(self, username, password):
        self.ensure_indexes()
        user = self.users.find_one({"username_key": username.casefold()})
        try:
            PASSWORDS.verify(user["password_hash"] if user else DUMMY_PASSWORD, password)
        except VerificationError:
            return None
        if user and PASSWORDS.check_needs_rehash(user["password_hash"]):
            self.users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": PASSWORDS.hash(password)}})
        return user

    def create_session(self, user_id):
        token = secrets.token_urlsafe(32)
        self.sessions.insert_one({"_id": token_hash(token), "user_id": user_id,
                                  "expires_at": datetime.now(timezone.utc) + timedelta(seconds=SESSION_SECONDS)})
        return token

    def find_user(self, token):
        # Validate expiry on every request; TTL cleanup is asynchronous.
        session = self.sessions.find_one({"_id": token_hash(token),
                                          "expires_at": {"$gt": datetime.now(timezone.utc)}})
        return self.users.find_one({"_id": session["user_id"]}) if session else None

    def logout(self, token):
        self.sessions.delete_one({"_id": token_hash(token)})
