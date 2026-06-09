"""
Unit tests for the reflections REST handler (DynamoDB + Neon mocked).

Run from repo root:
    conda run -n versiful_backend python -m pytest lambdas/reflections/test_reflections_handler.py -q
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

import reflections_handler as rh  # noqa: E402


def _event(method, route_key, path="/reflections", user_id="user-1", body=None,
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


class ReflectionsHandlerTests(unittest.TestCase):
    def setUp(self):
        self.users = mock.MagicMock()
        self._u_patch = mock.patch.object(rh, "users_table", self.users)
        self._u_patch.start()
        self.users.get_item.return_value = {"Item": {"userId": "user-1", "isSubscribed": True, "plan": "premium"}}

    def tearDown(self):
        self._u_patch.stop()

    def test_missing_auth_is_401(self):
        resp = rh.handler(_event("GET", "GET /reflections", user_id=None), None)
        self.assertEqual(resp["statusCode"], 401)

    def test_free_user_gated_402(self):
        self.users.get_item.return_value = {"Item": {"userId": "user-1", "plan": "free"}}
        resp = rh.handler(_event("GET", "GET /reflections"), None)
        self.assertEqual(resp["statusCode"], 402)
        self.assertEqual(_body(resp)["error"]["code"], "subscription_required")

    def test_list_neon_down_is_503(self):
        with mock.patch.object(rh.store, "available", return_value=False):
            resp = rh.handler(_event("GET", "GET /reflections"), None)
        self.assertEqual(resp["statusCode"], 503)
        self.assertEqual(_body(resp)["error"]["code"], "service_unavailable")

    def test_list_success(self):
        items = [{"id": "r1", "content": "c", "source": "manual", "verseReference": None, "mood": None, "sessionId": None, "createdAt": "2026-06-01T00:00:00Z"}]
        with mock.patch.object(rh.store, "available", return_value=True), \
             mock.patch.object(rh.store, "list_reflections", return_value={"available": True, "items": items, "nextCursor": None}):
            resp = rh.handler(_event("GET", "GET /reflections"), None)
        self.assertEqual(resp["statusCode"], 200)
        payload = _body(resp)
        self.assertEqual(payload["meta"]["count"], 1)
        self.assertEqual(payload["data"]["items"][0]["id"], "r1")

    def test_list_search_uses_vector(self):
        with mock.patch.object(rh.store, "available", return_value=True), \
             mock.patch.object(rh.store, "search_reflections", return_value={"available": True, "items": [], "nextCursor": None}) as sr:
            resp = rh.handler(_event("GET", "GET /reflections", query={"q": "anxiety"}), None)
        self.assertEqual(resp["statusCode"], 200)
        sr.assert_called_once()

    def test_list_invalid_source_400(self):
        with mock.patch.object(rh.store, "available", return_value=True):
            resp = rh.handler(_event("GET", "GET /reflections", query={"source": "bogus"}), None)
        self.assertEqual(resp["statusCode"], 400)

    def test_create_success(self):
        fake_ms = mock.MagicMock()
        fake_ms.insert_reflection.return_value = "rid-123"
        with mock.patch.object(rh.store, "available", return_value=True), \
             mock.patch.dict(sys.modules, {"memory_store": fake_ms}), \
             mock.patch.object(rh.store, "get_reflection", return_value={"available": True, "item": {"id": "rid-123", "content": "trusting God", "source": "manual", "verseReference": "Isaiah 41:10", "mood": None, "sessionId": None, "createdAt": "2026-06-09T00:00:00Z"}}):
            resp = rh.handler(_event("POST", "POST /reflections", body={"content": "trusting God", "verseReference": "Isaiah 41:10"}), None)
        self.assertEqual(resp["statusCode"], 201)
        data = _body(resp)["data"]
        self.assertEqual(data["id"], "rid-123")
        self.assertEqual(data["source"], "manual")
        fake_ms.insert_reflection.assert_called_once()

    def test_create_missing_content_400(self):
        with mock.patch.object(rh.store, "available", return_value=True):
            resp = rh.handler(_event("POST", "POST /reflections", body={"content": "   "}), None)
        self.assertEqual(resp["statusCode"], 400)

    def test_create_invalid_source_400(self):
        with mock.patch.object(rh.store, "available", return_value=True):
            resp = rh.handler(_event("POST", "POST /reflections", body={"content": "x", "source": "weird"}), None)
        self.assertEqual(resp["statusCode"], 400)

    def test_create_neon_down_503(self):
        with mock.patch.object(rh.store, "available", return_value=False):
            resp = rh.handler(_event("POST", "POST /reflections", body={"content": "x"}), None)
        self.assertEqual(resp["statusCode"], 503)

    def test_create_write_failure_503(self):
        fake_ms = mock.MagicMock()
        fake_ms.insert_reflection.return_value = None  # neon write failed
        with mock.patch.object(rh.store, "available", return_value=True), \
             mock.patch.dict(sys.modules, {"memory_store": fake_ms}):
            resp = rh.handler(_event("POST", "POST /reflections", body={"content": "x"}), None)
        self.assertEqual(resp["statusCode"], 503)

    def test_delete_success(self):
        with mock.patch.object(rh.store, "available", return_value=True), \
             mock.patch.object(rh.store, "delete_reflection", return_value={"available": True, "deleted": True}):
            resp = rh.handler(_event("DELETE", "DELETE /reflections/{id}", path="/reflections/r1", path_params={"id": "r1"}), None)
        self.assertEqual(resp["statusCode"], 200)
        self.assertTrue(_body(resp)["data"]["deleted"])

    def test_delete_not_found_404(self):
        with mock.patch.object(rh.store, "available", return_value=True), \
             mock.patch.object(rh.store, "delete_reflection", return_value={"available": True, "deleted": False}):
            resp = rh.handler(_event("DELETE", "DELETE /reflections/{id}", path="/reflections/r1", path_params={"id": "r1"}), None)
        self.assertEqual(resp["statusCode"], 404)

    def test_delete_neon_down_503(self):
        with mock.patch.object(rh.store, "available", return_value=True), \
             mock.patch.object(rh.store, "delete_reflection", return_value={"available": False, "deleted": False}):
            resp = rh.handler(_event("DELETE", "DELETE /reflections/{id}", path="/reflections/r1", path_params={"id": "r1"}), None)
        self.assertEqual(resp["statusCode"], 503)


class SaveReflectionToolTests(unittest.TestCase):
    def test_save_reflection_callable_success(self):
        import reflection_tools
        fake_ms = mock.MagicMock()
        fake_ms.insert_reflection.return_value = "rid-9"
        with mock.patch.dict(sys.modules, {"memory_store": fake_ms}):
            res = reflection_tools.save_reflection("user-1", "I want to trust the timing", verse_reference="Prov 3:5")
        self.assertTrue(res["ok"])
        self.assertEqual(res["reflectionId"], "rid-9")

    def test_save_reflection_unavailable(self):
        import reflection_tools
        fake_ms = mock.MagicMock()
        fake_ms.insert_reflection.return_value = None
        with mock.patch.dict(sys.modules, {"memory_store": fake_ms}):
            res = reflection_tools.save_reflection("user-1", "content")
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "unavailable")

    def test_save_reflection_missing_content(self):
        import reflection_tools
        res = reflection_tools.save_reflection("user-1", "  ")
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "missing_content")


if __name__ == "__main__":
    unittest.main()
