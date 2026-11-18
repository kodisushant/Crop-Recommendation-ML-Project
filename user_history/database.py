"""Shared MongoDB connection for server-side app data.

Keep credentials in environment variables, never in browser JavaScript. A short
operation timeout prevents an unavailable database from hanging the crop model.
"""
import os
from functools import lru_cache

from pymongo import MongoClient


@lru_cache(maxsize=1)
def get_database():
    client = MongoClient(
        os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017"),
        appname="crop-advisor",
        serverSelectionTimeoutMS=2000,
        connectTimeoutMS=2000,
        socketTimeoutMS=3000,
        timeoutMS=4000,
        tz_aware=True,
        connect=False,
    )
    return client[os.getenv("MONGODB_DATABASE", "crop_advisor")]


def close_database():
    if get_database.cache_info().currsize:
        get_database().client.close()
        get_database.cache_clear()
