"""
Unit tests for the prayers REST handler (DynamoDB + Neon mocked).

Run from repo root:
    conda run -n versiful_backend python -m pytest lambdas/prayers/test_prayers_handler.py -q
or:
    conda run -n versiful_backend python -m unittest discover -s lambdas/prayers -p 'test_*.py'
"""
import json
import os
import sys
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.abspath(os.path.join(_HERE, "..", "shared"))
for p in (_HERE, _SHARED):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("PROJECT_NAME", "versiful")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import prayers_handler as ph  # noqa: E402


def _event(method, route_key, path="/prayers", user_id="user-1", body=None,
           path_params=None, query=None):
    evt = {
        "routeKey": route_key,
        "rawPath": path,
        "requestContext": {
            "http": {"method": method, "path": path},
            "authorizer": {"lambda": {"userId": user_id}} if user_id else {},
        },
        "pathParameters": path_params or {},
        "queryStringParameters": query or {},
    }
    if body is not None:
        evt["body"] = json.dumps(body)
    return evt


def _body(resp):
    return json.loads(resp["body"])


class PrayersHandlerTests(unittest.TestCase):
    def setUp(self):
        self.prayers = mock.MagicMock()
        self.users = mock.MagicMock()
        self._p_patch = mock.patch.object(ph, "prayers_table", self.prayers)
        self._u_patch = mock.patch.object(ph, "users_table", self.users)
        self._p_patch.start()
        self._u_patch.start()
        # Default: premium user.
        self.users.get_item.return_value = {"Item": {"userId": "user-1", "isSubscribed": True, "plan": "premium"}}

    def tearDown(self):
        self._p_patch.stop()
        self._u_patch.stop()

    # --- auth ---
    def test_missing_auth_is_401(self):
        resp = ph.handler(_event("GET", "GET /prayers", user_id=None), None)
        self.assertEqual(resp["statusCode"], 401)
        self.assertEqual(_body(resp)["error"]["code"], "unauthorized")

    def test_options_preflight(self):
        resp = ph.handler(_event("OPTIONS", "OPTIONS /prayers", user_id=None), None)
        self.assertEqual(resp["statusCode"], 200)

    # --- create ---
    def test_create_success_premium(self):
        self.prayers.put_item.return_value = {}
        resp = ph.handler(_event("POST", "POST /prayers", body={"title": "Mom's surgery", "people": ["Mom"], "eventDate": "2026-06-12"}), None)
        self.assertEqual(resp["statusCode"], 201)
        data = _body(resp)["data"]
        self.assertEqual(data["title"], "Mom's surgery")
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["prayCount"], 0)
        self.assertEqual(data["people"], ["Mom"])
        self.assertTrue(data["id"])
        self.assertEqual(data["id"], data["prayerId"])
        self.prayers.put_item.assert_called_once()

    def test_create_missing_title_is_400(self):
        resp = ph.handler(_event("POST", "POST /prayers", body={"body": "no title"}), None)
        self.assertEqual(resp["statusCode"], 400)
        self.assertEqual(_body(resp)["error"]["code"], "validation_error")
        self.assertIn("title", _body(resp)["error"]["details"]["fields"])

    def test_create_invalid_event_date_is_400(self):
        resp = ph.handler(_event("POST", "POST /prayers", body={"title": "x", "eventDate": "June 12"}), None)
        self.assertEqual(resp["statusCode"], 400)

    def test_free_user_limit_reached_is_402(self):
        self.users.get_item.return_value = {"Item": {"userId": "user-1", "plan": "free"}}
        self.prayers.query.return_value = {"Count": 3}
        resp = ph.handler(_event("POST", "POST /prayers", body={"title": "fourth"}), None)
        self.assertEqual(resp["statusCode"], 402)
        err = _body(resp)["error"]
        self.assertEqual(err["code"], "limit_reached")
        self.assertEqual(err["details"]["limit"], 3)

    def test_free_user_under_limit_coerces_cadence(self):
        self.users.get_item.return_value = {"Item": {"userId": "user-1", "plan": "free"}}
        self.prayers.query.return_value = {"Count": 1}
        self.prayers.put_item.return_value = {}
        resp = ph.handler(_event("POST", "POST /prayers", body={"title": "ok", "reminderCadence": "daily"}), None)
        self.assertEqual(resp["statusCode"], 201)
        self.assertEqual(_body(resp)["data"]["reminderCadence"], "none")

    # --- list ---
    def test_list_returns_collection(self):
        self.prayers.query.return_value = {
            "Items": [
                {"userId": "user-1", "prayerId": "a", "title": "A", "status": "active", "createdAt": "2026-06-01T00:00:00Z"},
                {"userId": "user-1", "prayerId": "b", "title": "B", "status": "active", "createdAt": "2026-06-02T00:00:00Z"},
            ],
        }
        resp = ph.handler(_event("GET", "GET /prayers"), None)
        self.assertEqual(resp["statusCode"], 200)
        payload = _body(resp)
        self.assertEqual(payload["meta"]["count"], 2)
        self.assertIsNone(payload["meta"]["nextCursor"])
        # newest-first by createdAt
        self.assertEqual(payload["data"]["items"][0]["prayerId"], "b")

    def test_list_with_next_cursor(self):
        self.prayers.query.return_value = {
            "Items": [{"userId": "user-1", "prayerId": "a", "title": "A", "status": "active", "createdAt": "2026-06-01T00:00:00Z"}],
            "LastEvaluatedKey": {"userId": "user-1", "prayerId": "a"},
        }
        resp = ph.handler(_event("GET", "GET /prayers", query={"limit": "1"}), None)
        self.assertIsNotNone(_body(resp)["meta"]["nextCursor"])

    def test_list_invalid_status_is_400(self):
        resp = ph.handler(_event("GET", "GET /prayers", query={"status": "bogus"}), None)
        self.assertEqual(resp["statusCode"], 400)

    # --- update ---
    def test_update_not_owned_is_404(self):
        self.prayers.get_item.return_value = {}
        resp = ph.handler(_event("PUT", "PUT /prayers/{id}", path="/prayers/x", body={"title": "new"}, path_params={"id": "x"}), None)
        self.assertEqual(resp["statusCode"], 404)
        self.assertEqual(_body(resp)["error"]["code"], "not_found")

    def test_update_success(self):
        self.prayers.get_item.return_value = {"Item": {"userId": "user-1", "prayerId": "x", "title": "old", "status": "active"}}
        self.prayers.update_item.return_value = {"Attributes": {"userId": "user-1", "prayerId": "x", "title": "new", "status": "active"}}
        resp = ph.handler(_event("PUT", "PUT /prayers/{id}", path="/prayers/x", body={"title": "new"}, path_params={"id": "x"}), None)
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(_body(resp)["data"]["title"], "new")

    def test_update_no_fields_is_400(self):
        self.prayers.get_item.return_value = {"Item": {"userId": "user-1", "prayerId": "x", "title": "old"}}
        resp = ph.handler(_event("PUT", "PUT /prayers/{id}", path="/prayers/x", body={}, path_params={"id": "x"}), None)
        self.assertEqual(resp["statusCode"], 400)

    # --- answered ---
    def test_answered_success(self):
        self.prayers.get_item.return_value = {"Item": {"userId": "user-1", "prayerId": "x", "title": "Mom", "status": "active"}}
        self.prayers.update_item.return_value = {"Attributes": {"userId": "user-1", "prayerId": "x", "title": "Mom", "status": "answered", "answerNote": "praise!"}}
        with mock.patch.object(ph, "_write_answered_reflection") as wref:
            resp = ph.handler(_event("POST", "POST /prayers/{id}/answered", path="/prayers/x/answered", body={"note": "praise!"}, path_params={"id": "x"}), None)
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(_body(resp)["data"]["status"], "answered")
        wref.assert_called_once()

    def test_answered_not_owned_is_404(self):
        self.prayers.get_item.return_value = {}
        resp = ph.handler(_event("POST", "POST /prayers/{id}/answered", path="/prayers/x/answered", body={"note": "x"}, path_params={"id": "x"}), None)
        self.assertEqual(resp["statusCode"], 404)

    # --- delete ---
    def test_delete_success(self):
        self.prayers.get_item.return_value = {"Item": {"userId": "user-1", "prayerId": "x", "title": "t"}}
        self.prayers.delete_item.return_value = {}
        resp = ph.handler(_event("DELETE", "DELETE /prayers/{id}", path="/prayers/x", path_params={"id": "x"}), None)
        self.assertEqual(resp["statusCode"], 200)
        self.assertTrue(_body(resp)["data"]["deleted"])

    def test_delete_not_owned_is_404(self):
        self.prayers.get_item.return_value = {}
        resp = ph.handler(_event("DELETE", "DELETE /prayers/{id}", path="/prayers/x", path_params={"id": "x"}), None)
        self.assertEqual(resp["statusCode"], 404)


class SavePrayerToolTests(unittest.TestCase):
    def test_save_prayer_callable_success(self):
        import prayer_tools
        with mock.patch.object(prayer_tools, "_table") as t:
            tbl = mock.MagicMock()
            t.return_value = tbl
            res = prayer_tools.save_prayer("user-1", "Mom's surgery", people=["Mom"], event_date="2026-06-12")
        self.assertTrue(res["ok"])
        self.assertEqual(res["title"], "Mom's surgery")
        tbl.put_item.assert_called_once()

    def test_save_prayer_callable_no_user(self):
        import prayer_tools
        res = prayer_tools.save_prayer("", "x")
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "no_user")


if __name__ == "__main__":
    unittest.main()
