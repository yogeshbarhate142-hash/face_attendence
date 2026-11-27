import importlib
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock

# Stub DeepFace so API smoke tests do not download ML models.
deepface_module = types.ModuleType("deepface")
deepface_module.DeepFace = MagicMock()
sys.modules["deepface"] = deepface_module

import app as attendance_app


class ApiSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        attendance_app.DB_PATH = os.path.join(self.tmp.name, "test.db")
        attendance_app.FACE_DIR = os.path.join(self.tmp.name, "faces")
        os.makedirs(attendance_app.FACE_DIR, exist_ok=True)
        attendance_app.init_db()
        attendance_app.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = attendance_app.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_signup_validation(self):
        response = self.client.post("/api/org/signup", json={"org_name": "", "email": "", "password": "short"})
        self.assertEqual(response.status_code, 400)

    def test_signup_and_admin_session(self):
        response = self.client.post("/api/org/signup", json={
            "org_name": "Test Organization",
            "email": "admin@example.com",
            "password": "StrongPassword123"
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("organization_code"))

        me = self.client.get("/api/admin/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.get_json()["organization"]["name"], "Test Organization")

        report = self.client.get("/api/admin/report")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.get_json()["member_count"], 0)

    def test_admin_endpoints_require_login(self):
        self.assertEqual(self.client.get("/api/admin/me").status_code, 401)
        self.assertEqual(self.client.get("/api/admin/report").status_code, 401)
        self.assertEqual(self.client.post("/api/admin/members").status_code, 401)

    def test_login_and_logout(self):
        signup = self.client.post("/api/org/signup", json={
            "org_name": "Login Test Org",
            "email": "login@example.com",
            "password": "StrongPassword123"
        })
        self.assertEqual(signup.status_code, 200)

        self.client.post("/api/admin/logout", json={})
        login = self.client.post("/api/admin/login", json={
            "email": "login@example.com",
            "password": "StrongPassword123"
        })
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.get("/api/admin/me").status_code, 200)

        logout = self.client.post("/api/admin/logout", json={})
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(self.client.get("/api/admin/me").status_code, 401)

    def test_invalid_login(self):
        response = self.client.post("/api/admin/login", json={
            "email": "missing@example.com",
            "password": "wrong"
        })
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
