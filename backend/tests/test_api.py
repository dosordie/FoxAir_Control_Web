import unittest
from fastapi.testclient import TestClient
from backend.main import app


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_available_transports(self):
        response = self.client.get("/api/transports")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 4)
        self.assertFalse(response.json()["live_supported"])

    def test_cloud_is_not_faked(self):
        data = self.client.get("/api/dashboard?transport=cloud").json()
        self.assertEqual(data["status"], "unavailable")
        self.assertTrue(all(value is None for value in data["metrics"].values()))

    def test_search(self):
        response = self.client.get("/api/registers?query=D14")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(row["code"] == "D14" for row in response.json()["items"]))

    def test_no_write_endpoint(self):
        response = self.client.post("/api/registers/1158/write", json={"value": 35})
        self.assertIn(response.status_code, (404, 405))

    def test_unknown_transport_rejected(self):
        self.assertEqual(self.client.get("/api/dashboard?transport=unsafe").status_code, 400)


if __name__ == "__main__":
    unittest.main()
