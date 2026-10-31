"""
Comprehensive Test Suite for OCPI 2.2.1 Roaming Integration.
Verifies FastAPI router registration, version discovery, credentials exchange,
module endpoints, token authentication, error handling, and regression safety.
"""
import asyncio
from datetime import datetime, timezone
import importlib.metadata
import os
import sys
import unittest
from unittest import mock

# Provide required mocks for uninstalled dependencies before importing modules
importlib.metadata.version = lambda pkg: '2.2.0'
for mod in [
    'cryptography', 'cryptography.x509', 'cryptography.x509.oid',
    'cryptography.hazmat', 'cryptography.hazmat.primitives',
    'cryptography.hazmat.primitives.asymmetric', 'cryptography.hazmat.primitives.hashes',
    'cryptography.hazmat.primitives.serialization',
    'state.postgres', 'state.redis', 'state.settings',
    'events.bus', 'events.types', 'email_validator', 'bcrypt'
]:
    sys.modules[mod] = mock.MagicMock()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from api.main import app
from ocpi.main import ocpi_response, ocpi_error, verify_ocpi_token


class MockAsyncContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class TestOCPIIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.test_token = "valid_roaming_token_secret_123"

    def setUp(self):
        # Configure database mock for each test
        self.mock_conn = mock.AsyncMock()

        from state.postgres import db
        db.read.return_value = MockAsyncContext(self.mock_conn)
        db.write.return_value = MockAsyncContext(self.mock_conn)

        # Default partner lookup behavior:
        # If token matches self.test_token, return active partner; else None
        async def fetchrow_side_effect(query, *args):
            if "ocpp.ocpi_partners" in query and "token_a = $1" in query:
                token = args[0]
                if token == self.test_token:
                    return {
                        "party_id": "MSP",
                        "country_code": "DE",
                        "name": "Test eMSP Partner",
                        "token_a": self.test_token,
                        "token_b": "partner_b_token",
                        "status": "active",
                        "metadata": '{"roaming_fee_kwh": 0.05}',
                    }
                return None
            elif "ocpp.ocpi_locations" in query and "WHERE id = $1" in query:
                if args[0] == "LOC001":
                    return {
                        "id": "LOC001",
                        "name": "Central Plaza Charger",
                        "address": "Kerkstraat 10",
                        "city": "Amsterdam",
                        "country": "NLD",
                        "last_updated": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    }
                return None
            elif "ocpp.ocpi_tokens" in query and "uid = $1" in query:
                if args[0] == "TAG_VALID":
                    return {
                        "country_code": "DE",
                        "party_id": "MSP",
                        "uid": "TAG_VALID",
                        "type": "RFID",
                        "auth_id": "RFID-001",
                        "issuer": "Test eMSP",
                        "valid": True,
                        "whitelist": "ALWAYS",
                        "last_updated": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    }
                return None
            return None

        async def fetch_side_effect(query, *args):
            if "ocpp.ocpi_locations" in query:
                return [
                    {
                        "id": "LOC001",
                        "name": "Central Plaza Charger",
                        "address": "Kerkstraat 10",
                        "city": "Amsterdam",
                        "country": "NLD",
                        "coordinates": [52.37, 4.89],
                        "last_updated": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    }
                ]
            elif "ocpp.connectors" in query:
                return [
                    {
                        "id": "CP001",
                        "connector_id": 1,
                        "status": "Available",
                    }
                ]
            elif "ocpp.sessions" in query:
                return [
                    {
                        "id": "11111111-2222-3333-4444-555555555555",
                        "charge_point": "CP001",
                        "connector_id": 1,
                        "auth_id": "TAG_VALID",
                        "auth_method": "rfid",
                        "start_time": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
                        "stop_time": datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
                        "energy_kwh": 22.5,
                        "status": "completed",
                    }
                ]
            elif "ocpp.cdrs" in query:
                return [
                    {
                        "id": "22222222-3333-4444-5555-666666666666",
                        "session_id": "11111111-2222-3333-4444-555555555555",
                        "charge_point": "CP001",
                        "connector_id": 1,
                        "auth_method": "rfid",
                        "auth_id": "TAG_VALID",
                        "start_time": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
                        "stop_time": datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
                        "energy_kwh": 22.5,
                        "duration_min": 60.0,
                        "cost": {"total": 8.75},
                        "created_at": datetime(2026, 1, 1, 11, 5, tzinfo=timezone.utc),
                    }
                ]
            elif "ocpp.tariffs" in query:
                return [
                    {
                        "id": "TAR_DEFAULT",
                        "name": "Standard AC Tariff",
                        "currency": "EUR",
                        "energy_rate": 0.35,
                        "time_rate": 0.0,
                        "idle_rate": 0.0,
                        "flat_fee": 1.0,
                        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    }
                ]
            return []

        self.mock_conn.fetchrow.side_effect = fetchrow_side_effect
        self.mock_conn.fetch.side_effect = fetch_side_effect
        self.mock_conn.execute.return_value = "OK"

    # -------------------------------------------------------------------------
    # 1. Route Registration & OpenAPI Schema Verification
    # -------------------------------------------------------------------------
    def test_ocpi_routes_registered_in_app(self):
        """Verify that all intended OCPI 2.2.1 routes exist on the main FastAPI application."""
        registered_paths = app.openapi()["paths"].keys()

        expected_ocpi_paths = [
            "/ocpi/versions",
            "/ocpi/2.2.1",
            "/ocpi/2.2.1/details",
            "/ocpi/2.2.1/credentials",
            "/ocpi/2.2.1/locations",
            "/ocpi/2.2.1/locations/{country_code}/{party_id}/{location_id}",
            "/ocpi/2.2.1/sessions",
            "/ocpi/2.2.1/cdrs",
            "/ocpi/2.2.1/tariffs",
            "/ocpi/2.2.1/tokens/{country_code}/{party_id}/{token_uid}",
        ]

        for expected in expected_ocpi_paths:
            self.assertIn(
                expected,
                registered_paths,
                f"Missing expected OCPI path '{expected}' in registered application routes",
            )

    def test_non_ocpi_endpoints_remain_functional(self):
        """Ensure existing Core endpoints like /health remain unaffected."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "ocpp-core")

    # -------------------------------------------------------------------------
    # 2. Version Discovery & Version Details
    # -------------------------------------------------------------------------
    def test_version_discovery_endpoint(self):
        """GET /ocpi/versions returns available OCPI versions."""
        response = self.client.get("/ocpi/versions")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status_code"], 1000)
        self.assertEqual(payload["status_message"], "Success")

        data = payload["data"]
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["version"], "2.2.1")
        self.assertTrue(data[0]["url"].endswith("/ocpi/2.2.1"))

    def test_version_details_endpoint(self):
        """GET /ocpi/2.2.1 returns registered module endpoints and roles."""
        response = self.client.get("/ocpi/2.2.1")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status_code"], 1000)

        data = payload["data"]
        self.assertEqual(data["version"], "2.2.1")
        identifiers = {ep["identifier"]: ep["role"] for ep in data["endpoints"]}

        expected_modules = {
            "credentials": "SENDER",
            "locations": "SENDER",
            "sessions": "SENDER",
            "cdrs": "SENDER",
            "tariffs": "SENDER",
            "tokens": "RECEIVER",
        }
        for mod, role in expected_modules.items():
            self.assertIn(mod, identifiers)
            self.assertEqual(identifiers[mod], role)

        # Test alias /ocpi/2.2.1/details
        alias_resp = self.client.get("/ocpi/2.2.1/details")
        self.assertEqual(alias_resp.status_code, 200)
        self.assertEqual(alias_resp.json()["data"], data)

    # -------------------------------------------------------------------------
    # 3. Credentials Handshake (Onboarding)
    # -------------------------------------------------------------------------
    def test_credentials_handshake_registration(self):
        """POST /ocpi/2.2.1/credentials registers a new partner and returns CPO credentials."""
        handshake_payload = {
            "token": "emsp_incoming_token_xyz",
            "url": "https://emsp.example.com/ocpi/versions",
            "roles": [
                {
                    "role": "EMSP",
                    "party_id": "MSP",
                    "country_code": "DE",
                    "business_details": {"name": "Test eMSP Partner"},
                }
            ],
        }
        response = self.client.post("/ocpi/2.2.1/credentials", json=handshake_payload)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status_code"], 1000)

        data = payload["data"]
        self.assertIn("token", data)
        self.assertTrue(data["url"].endswith("/ocpi/versions"))
        self.assertEqual(data["roles"][0]["role"], "CPO")

    def test_credentials_handshake_missing_fields_returns_2001(self):
        """POST /ocpi/2.2.1/credentials returns OCPI status 2001 on missing required fields."""
        incomplete_payload = {"token": "only_token"}
        response = self.client.post("/ocpi/2.2.1/credentials", json=incomplete_payload)
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["status_code"], 2001)

    # -------------------------------------------------------------------------
    # 4. Authentication Enforcement & Security
    # -------------------------------------------------------------------------
    def test_protected_endpoint_without_token_returns_401(self):
        """Protected endpoints without Authorization header must return HTTP 401."""
        response = self.client.get("/ocpi/2.2.1/locations")
        self.assertEqual(response.status_code, 401)
        self.assertIn("Missing or invalid Authorization header", response.text)

    def test_protected_endpoint_with_invalid_token_returns_401(self):
        """Protected endpoints with unrecognized token must return HTTP 401."""
        headers = {"Authorization": "Token invalid_or_unregistered_token"}
        response = self.client.get("/ocpi/2.2.1/locations", headers=headers)
        self.assertEqual(response.status_code, 401)
        self.assertIn("Invalid OCPI token", response.text)

    def test_protected_endpoint_with_valid_token_succeeds(self):
        """Protected endpoints with valid token succeed."""
        headers = {"Authorization": f"Token {self.test_token}"}
        response = self.client.get("/ocpi/2.2.1/locations", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status_code"], 1000)

    # -------------------------------------------------------------------------
    # 5. Module Endpoints: Locations, Sessions, CDRs, Tariffs, Tokens
    # -------------------------------------------------------------------------
    def test_get_locations_list_and_details(self):
        """GET /ocpi/2.2.1/locations returns published locations with EVSEs and connectors."""
        headers = {"Authorization": f"Token {self.test_token}"}
        response = self.client.get("/ocpi/2.2.1/locations", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "LOC001")
        self.assertEqual(data[0]["evses"][0]["status"], "AVAILABLE")

        # Single location details
        detail_resp = self.client.get("/ocpi/2.2.1/locations/NL/OCP/LOC001", headers=headers)
        self.assertEqual(detail_resp.status_code, 200)
        self.assertEqual(detail_resp.json()["data"]["id"], "LOC001")

        # Unknown location returns OCPI 2003
        unknown_resp = self.client.get("/ocpi/2.2.1/locations/NL/OCP/NONEXISTENT", headers=headers)
        self.assertEqual(unknown_resp.json()["status_code"], 2003)

    def test_get_sessions(self):
        """GET /ocpi/2.2.1/sessions returns charging session records."""
        headers = {"Authorization": f"Token {self.test_token}"}
        response = self.client.get("/ocpi/2.2.1/sessions", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["kwh"], 22.5)
        self.assertEqual(data[0]["status"], "COMPLETED")

    def test_get_cdrs(self):
        """GET /ocpi/2.2.1/cdrs returns billing reconciliation records."""
        headers = {"Authorization": f"Token {self.test_token}"}
        response = self.client.get("/ocpi/2.2.1/cdrs", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["total_energy"], 22.5)
        self.assertEqual(data[0]["total_cost"], 8.75)

    def test_get_tariffs_with_partner_markup(self):
        """GET /ocpi/2.2.1/tariffs returns tariffs with partner roaming fee applied."""
        headers = {"Authorization": f"Token {self.test_token}"}
        response = self.client.get("/ocpi/2.2.1/tariffs", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        # Base 0.35 + Roaming fee 0.05 = 0.40
        components = data[0]["elements"][0]["price_components"]
        self.assertEqual(components[0]["price"], 0.40)

    def test_tokens_crud(self):
        """Tokens module allows querying, pushing (PUT), and updating (PATCH) tokens."""
        headers = {"Authorization": f"Token {self.test_token}"}

        # GET existing token
        get_resp = self.client.get("/ocpi/2.2.1/tokens/DE/MSP/TAG_VALID", headers=headers)
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["data"]["uid"], "TAG_VALID")

        # PUT token
        put_payload = {
            "type": "RFID",
            "auth_id": "RFID-999",
            "issuer": "Test eMSP",
            "valid": True,
            "whitelist": "ALWAYS",
        }
        put_resp = self.client.put("/ocpi/2.2.1/tokens/DE/MSP/TAG_NEW", json=put_payload, headers=headers)
        self.assertEqual(put_resp.status_code, 200)
        self.assertEqual(put_resp.json()["status_code"], 1000)

        # PATCH token
        patch_resp = self.client.patch(
            "/ocpi/2.2.1/tokens/DE/MSP/TAG_NEW",
            json={"valid": False},
            headers=headers,
        )
        self.assertEqual(patch_resp.status_code, 200)

    # -------------------------------------------------------------------------
    # 6. Management vs Roaming Isolation & Unknown Paths
    # -------------------------------------------------------------------------
    def test_unknown_path_returns_404(self):
        """Nonexistent OCPI paths return HTTP 404."""
        response = self.client.get("/ocpi/nonexistent_module")
        self.assertEqual(response.status_code, 404)

    def test_internal_mgmt_api_isolated_from_roaming_token(self):
        """Roaming partner token cannot access internal CPO management endpoint."""
        headers = {"Authorization": f"Token {self.test_token}"}
        # /api/v1/ocpi/partners requires MANAGEMENT_API_KEY, not partner token
        response = self.client.get("/api/v1/ocpi/partners", headers=headers)
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
