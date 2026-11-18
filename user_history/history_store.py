"""MongoDB persistence for predictions. Every read is scoped to one owner.

The web layer supplies the owner; the browser must never choose another user's
ID. Store the original numeric inputs and model result, not translated labels.
"""
from datetime import datetime, timezone
from threading import Lock

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import DESCENDING


class HistoryStore:
    def __init__(self, database):
        self.collection = database["prediction_history"]
        self._indexed = False
        self._index_lock = Lock()

    def ensure_indexes(self):
        if self._indexed:
            return
        with self._index_lock:
            if not self._indexed:
                self.collection.create_index([("owner_id", 1), ("_id", DESCENDING)], name="owner_recent")
                self._indexed = True

    def save(self, owner_id, inputs, result, source="recommendation"):
        self.ensure_indexes()
        record = {
            "owner_id": owner_id,
            "created_at": datetime.now(timezone.utc),
            "source": source,
            "inputs": inputs,
            "result": result,
        }
        inserted = self.collection.insert_one(record)
        return str(inserted.inserted_id)

    @staticmethod
    def parse_id(value):
        try:
            return ObjectId(value)
        except (InvalidId, TypeError):
            raise ValueError("Invalid history record ID") from None

    @staticmethod
    def serialize(record, detail=False):
        result = record["result"]
        choices = result.get("top_k") or []
        summary = {
            "id": str(record["_id"]),
            "created_at": record["created_at"].isoformat(),
            "source": record["source"],
            "inputs": record["inputs"],
            "crop": result.get("crop"),
            "status": result["status"],
            "confidence_label": result.get("confidence_label"),
            "probability": choices[0]["probability"] if choices else None,
        }
        if detail:
            summary["result"] = result
        return summary

    def list(self, owner_id, limit=20, before=None):
        self.ensure_indexes()
        query = {"owner_id": owner_id}
        if before:
            query["_id"] = {"$lt": self.parse_id(before)}
        records = list(self.collection.find(query).sort("_id", DESCENDING).limit(limit + 1))
        return {
            "items": [self.serialize(record) for record in records[:limit]],
            "next_cursor": str(records[limit - 1]["_id"]) if len(records) > limit else None,
        }

    def get(self, owner_id, record_id):
        record = self.collection.find_one({"_id": self.parse_id(record_id), "owner_id": owner_id})
        return self.serialize(record, detail=True) if record else None

    def delete(self, owner_id, record_id):
        return self.collection.delete_one({"_id": self.parse_id(record_id), "owner_id": owner_id}).deleted_count == 1
