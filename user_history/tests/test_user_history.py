"""Account/history integration tests against an isolated, disposable MongoDB.

Run: python -m unittest discover -s user_history/tests -p test_user_history.py
No production collection is read or cleared by this suite.
"""
import copy
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

import main
from user_history.accounts import AccountStore, token_hash
from user_history.history_store import HistoryStore

HEADERS = {"X-Crop-Request": "1"}
PASSWORD = "Test-only-harvest-2026"
INPUTS = {"N": 90, "P": 42, "K": 43, "temperature": 20.9, "humidity": 82, "ph": 6.5, "rainfall": 203}
RESULT = {"status": "OK", "crop": "rice", "confidence_label": "High", "top_k": [{"crop": "rice", "probability": 0.93}],
          "input": INPUTS, "reasons": [], "normalized_entropy": 0.1, "margin": 0.8,
          "stability_runs": 40, "stability_change_rate": 0,
          "out_of_range_check": {"distance": 1, "threshold": 4}, "explanation": [], "note": "Test model result"}


class UserHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mongo = MongoClient(os.getenv("TEST_MONGODB_URI", "mongodb://127.0.0.1:27017"),
                               serverSelectionTimeoutMS=2000, tz_aware=True)
        try:
            cls.mongo.admin.command("ping")
        except PyMongoError:
            cls.mongo.close()
            raise unittest.SkipTest("Start MongoDB to run database integration tests")
        cls.database_name = "crop_advisor_tests_" + uuid.uuid4().hex
        cls.db = cls.mongo[cls.database_name]

    @classmethod
    def tearDownClass(cls):
        # This exact random database was created by this test class only.
        assert cls.database_name.startswith("crop_advisor_tests_")
        cls.mongo.drop_database(cls.database_name)
        cls.mongo.close()

    def setUp(self):
        for name in ("users", "sessions", "auth_attempts", "prediction_history"):
            self.db[name].delete_many({})
        self.accounts, self.history = AccountStore(self.db), HistoryStore(self.db)
        self.auth_patch = patch("user_history.routes.get_accounts", return_value=self.accounts)
        self.history_patch = patch("user_history.routes.get_history", return_value=self.history)
        self.auth_patch.start(); self.history_patch.start()
        self.addCleanup(self.auth_patch.stop); self.addCleanup(self.history_patch.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def register(self, client=None, username="farmer_one"):
        client = client or self.client
        response = client.post("/api/auth/register", json={"username": username, "password": PASSWORD}, headers=HEADERS)
        self.assertEqual(response.status_code, 201, response.text)
        return response

    def predict(self, client=None, result=None, source="recommendation"):
        with patch("main.P.predict", side_effect=lambda values: copy.deepcopy(result or RESULT)):
            return (client or self.client).post("/predict", json=INPUTS,
                                               headers={**HEADERS, "X-Activity-Source": source})

    def test_registration_hashes_password_and_grants_only_user_role(self):
        response = self.register()
        self.assertEqual(response.json()["user"]["role"], "user")
        self.assertNotIn("password", response.text)
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie); self.assertIn("SameSite=lax", cookie)
        user = self.db.users.find_one()
        self.assertTrue(user["password_hash"].startswith("$argon2id$"))
        self.assertNotEqual(user["password_hash"], PASSWORD)
        token = self.client.cookies.get("crop_session")
        self.assertIsNotNone(self.db.sessions.find_one({"_id": token_hash(token)}))
        self.assertIsNone(self.db.sessions.find_one({"_id": token}))
        self.assertEqual(self.client.get("/api/auth/me").json()["user"]["username"], "farmer_one")
        duplicate = self.client.post("/api/auth/register", json={"username": "FARMER_ONE", "password": PASSWORD}, headers=HEADERS)
        self.assertEqual(duplicate.status_code, 409)
        escalation = self.client.post("/api/auth/register", json={"username": "administrator", "password": PASSWORD, "role": "admin"}, headers=HEADERS)
        self.assertEqual(escalation.status_code, 422)

    def test_two_devices_share_history_without_sharing_session_tokens(self):
        self.register()
        saved = self.predict().json()
        self.assertTrue(saved["history"]["saved"])
        with TestClient(main.app) as second:
            login = second.post("/api/auth/login", json={"username": "farmer_one", "password": PASSWORD}, headers=HEADERS)
            self.assertEqual(login.status_code, 200)
            self.assertNotEqual(second.cookies.get("crop_session"), self.client.cookies.get("crop_session"))
            records = second.get("/api/history").json()["items"]
            self.assertEqual(records[0]["id"], saved["history"]["id"])
            self.assertEqual(records[0]["inputs"]["ph"], 6.5)
            report = second.get("/api/history/" + records[0]["id"])
            self.assertEqual(report.json()["result"]["top_k"], RESULT["top_k"])

    def test_other_accounts_cannot_read_delete_or_claim_another_history(self):
        self.register(); record_id = self.predict().json()["history"]["id"]
        owner_id = self.client.get("/api/auth/me").json()["user"]["id"]
        with TestClient(main.app) as other:
            self.register(other, "farmer_two")
            self.assertEqual(other.get("/api/history", params={"owner_id": owner_id}).json()["items"], [])
            self.assertEqual(other.get("/api/history/" + record_id).status_code, 404)
            self.assertEqual(other.delete("/api/history/" + record_id, headers=HEADERS).status_code, 404)
        self.assertEqual(self.client.get("/api/history/" + record_id).status_code, 200)

    def test_guest_can_predict_but_cannot_read_private_history(self):
        response = self.predict()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["history"], {"saved": False, "reason": "sign_in_required"})
        self.assertEqual(self.db.prediction_history.count_documents({}), 0)
        self.assertEqual(self.client.get("/api/history").status_code, 401)

    def test_low_confidence_and_refused_predictions_are_saved_honestly(self):
        self.register()
        for status in ("LOW_CONFIDENCE", "OUT_OF_RANGE"):
            result = copy.deepcopy(RESULT); result["status"] = status
            result["reasons"] = ["Test warning"]
            if status == "OUT_OF_RANGE":
                result.update(crop=None, top_k=[], explanation=[])
            response = self.predict(result=result, source="soil-analysis")
            report = self.client.get("/api/history/" + response.json()["history"]["id"]).json()
            self.assertEqual(report["source"], "soil-analysis")
            self.assertEqual(report["result"]["reasons"], ["Test warning"])
            self.assertEqual(report["status"], status)
            if status == "OUT_OF_RANGE": self.assertIsNone(report["probability"])

    def test_pagination_and_individual_delete(self):
        self.register()
        ids = [self.predict().json()["history"]["id"] for _ in range(4)]
        first = self.client.get("/api/history?limit=2").json()
        second = self.client.get("/api/history", params={"limit": 2, "before": first["next_cursor"]}).json()
        self.assertEqual([r["id"] for r in first["items"] + second["items"]], list(reversed(ids)))
        self.assertIsNone(second["next_cursor"])
        self.assertEqual(self.client.delete("/api/history/" + ids[0], headers=HEADERS).status_code, 200)
        self.assertEqual(self.client.get("/api/history/" + ids[0]).status_code, 404)
        self.assertEqual(self.client.get("/api/history?limit=10000").status_code, 422)
        self.assertEqual(self.client.get("/api/history?before=bad").status_code, 400)

    def test_logout_and_expiry_revoke_access(self):
        self.register(); token = self.client.cookies.get("crop_session")
        self.assertEqual(self.client.post("/api/auth/logout", json={}, headers=HEADERS).status_code, 200)
        self.client.cookies.set("crop_session", token)
        self.assertEqual(self.client.get("/api/history").status_code, 401)
        self.client.cookies.clear(); self.register(username="fresh_user")
        token = self.client.cookies.get("crop_session")
        self.db.sessions.update_one({"_id": token_hash(token)}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}})
        self.assertEqual(self.client.get("/api/history").status_code, 401)

    def test_csrf_guards_and_secure_cookie(self):
        body = {"username": "farmer_one", "password": PASSWORD}
        self.assertEqual(self.client.post("/api/auth/register", json=body).status_code, 403)
        self.assertEqual(self.client.post("/api/auth/register", json=body, headers={**HEADERS, "Origin": "https://unrelated.example"}).status_code, 403)
        with TestClient(main.app, base_url="https://testserver") as secure:
            response = self.register(secure)
            self.assertIn("Secure", response.headers["set-cookie"])
            self.assertEqual(secure.post("/predict", json=INPUTS).status_code, 403)

    def test_database_outage_keeps_model_result_and_reports_unsaved_history(self):
        self.register()
        with patch.object(self.history, "save", side_effect=ServerSelectionTimeoutError("test outage")):
            response = self.predict()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["crop"], "rice")
        self.assertEqual(response.json()["history"], {"saved": False, "reason": "storage_unavailable"})
        with patch.object(self.accounts, "find_user", side_effect=ServerSelectionTimeoutError("test outage")):
            self.assertEqual(self.client.get("/api/history").status_code, 503)

    def test_bad_passwords_are_generic_and_login_is_rate_limited(self):
        self.register()
        body = {"username": "farmer_one", "password": "wrong-password-test"}
        responses = [self.client.post("/api/auth/login", json=body, headers=HEADERS) for _ in range(11)]
        self.assertEqual(responses[0].status_code, 401)
        self.assertEqual(responses[0].json()["detail"], "Incorrect username or password.")
        self.assertEqual(responses[-1].status_code, 429)

    def test_new_pages_and_private_responses_do_not_cache(self):
        for route in ("/login", "/register", "/history"):
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.client.get("/api/auth/me").headers["cache-control"], "no-store")


if __name__ == "__main__":
    unittest.main()
