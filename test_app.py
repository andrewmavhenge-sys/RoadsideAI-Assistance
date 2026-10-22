import json
import unittest
from unittest.mock import Mock, patch

import requests

import app as roadside_app


VALID_ASSESSMENT = {
    "service_category": "Battery assistance",
    "summary": "The clicking and dashboard lights may indicate an electrical issue.",
    "reported_symptoms": ["Clicking when turning the key", "Dashboard lights work"],
    "possible_explanations": ["A weak battery is one possibility."],
    "severity": "moderate",
    "safety_advice": ["Stay in a safe location."],
    "recommended_action": "Request roadside assistance if the vehicle will not start.",
    "follow_up_questions": ["Are you safely away from traffic?"],
    "uncertainty": "The cause cannot be confirmed from these symptoms alone.",
}


class RoadsideAppTests(unittest.TestCase):
    def setUp(self):
        roadside_app.app.config["TESTING"] = True
        self.client = roadside_app.app.test_client()

    def ollama_response(self, content=None):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "message": {"content": json.dumps(content or VALID_ASSESSMENT)}
        }
        return response

    def assess(self, description="My car clicks but will not start.", vehicle=None):
        return self.client.post(
            "/api/assess",
            json={"description": description, "vehicle": vehicle or {}},
        )

    def test_homepage_renders_assessment_form(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Get my next steps", response.data)
        self.assertIn(b"A LITTLE HELP GOES A LONG WAY", response.data)
        self.assertIn(b"Are you somewhere safe?", response.data)
        self.assertIn(b"else if (content instanceof Node)", response.data)
        self.assertIn(b"2000", response.data)

    def test_rejects_short_description_without_calling_ollama(self):
        with patch.object(roadside_app.requests, "post") as post:
            response = self.assess("short")
        self.assertEqual(response.status_code, 400)
        post.assert_not_called()

    def test_rejects_description_over_2000_characters(self):
        with patch.object(roadside_app.requests, "post") as post:
            response = self.assess("x" * 2001)
        self.assertEqual(response.status_code, 400)
        self.assertIn("2,000", response.get_json()["error"])
        post.assert_not_called()

    def test_accepts_description_at_2000_character_limit(self):
        with patch.object(roadside_app.requests, "post", return_value=self.ollama_response()):
            response = self.assess("x" * 2000)
        self.assertEqual(response.status_code, 200)

    def test_rejects_non_text_description(self):
        response = self.client.post("/api/assess", json={"description": ["not", "text"]})
        self.assertEqual(response.status_code, 400)

    def test_valid_response_has_structured_fields_and_safe_vehicle_context(self):
        with patch.object(roadside_app.requests, "post", return_value=self.ollama_response()) as post:
            response = self.assess(vehicle={"type": "Car", "make_model": "Honda City"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["service_category"], "Battery assistance")
        self.assertIsNone(data["safety_alert"])
        self.assertIn("AI-assisted preliminary assessment", data["ai_disclaimer"])
        model_request = post.call_args.kwargs["json"]
        self.assertIn("Vehicle type: Car", model_request["messages"][1]["content"])
        self.assertFalse(model_request["think"])
        self.assertEqual(model_request["format"]["type"], "object")
        self.assertIn("recommended_action", model_request["format"]["required"])
        self.assertEqual(model_request["options"]["num_ctx"], 2048)
        self.assertEqual(model_request["options"]["num_predict"], 320)
        self.assertEqual(post.call_args.kwargs["timeout"], 50)

    def test_partial_response_gets_safe_defaults_and_legacy_fields_map(self):
        partial = {"category": "Tire assistance", "symptoms": ["Flat tire"]}
        with patch.object(roadside_app.requests, "post", return_value=self.ollama_response(partial)):
            response = self.assess()
        data = response.get_json()
        self.assertEqual(data["service_category"], "Tire assistance")
        self.assertEqual(data["reported_symptoms"], ["Flat tire"])
        self.assertEqual(data["severity"], "moderate")
        self.assertTrue(data["recommended_action"])
        self.assertTrue(data["follow_up_questions"])

    def test_malformed_model_json_returns_friendly_error(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"message": {"content": "not JSON"}}
        with patch.object(roadside_app.requests, "post", return_value=response):
            result = self.assess()
        self.assertEqual(result.status_code, 502)
        self.assertIn("unreadable", result.get_json()["error"])

    def test_safety_rule_detects_all_requested_risk_categories(self):
        description = "Smoke, fuel smell, brake failure, steam after a collision on the highway."
        flags = roadside_app.detect_safety_flags(description)
        self.assertEqual(
            set(flags),
            {"smoke", "fuel_leak", "brake_failure", "overheating", "collision", "traffic"},
        )

    def test_overheating_rule_overrides_routine_model_guidance(self):
        with patch.object(roadside_app.requests, "post", return_value=self.ollama_response()):
            response = self.assess("Steam is coming from the engine and it is overheating.")
        data = response.get_json()
        self.assertEqual(data["severity"], "high")
        self.assertIn("steam", data["safety_alert"]["matched_keywords"])
        self.assertIn("radiator cap", " ".join(data["safety_advice"]))
        self.assertIn("towing", data["recommended_action"])

    def test_emergency_rule_overrides_routine_model_guidance(self):
        with patch.object(roadside_app.requests, "post", return_value=self.ollama_response()):
            response = self.assess("There is smoke coming from the vehicle.")
        data = response.get_json()
        self.assertEqual(data["severity"], "emergency")
        self.assertEqual(data["recommended_action"], "Move away from the vehicle and contact local emergency services.")

    def test_ollama_connection_failure_returns_503(self):
        with patch.object(
            roadside_app.requests,
            "post",
            side_effect=requests.exceptions.ConnectionError(),
        ):
            response = self.assess()
        self.assertEqual(response.status_code, 503)
        self.assertIn("Could not connect", response.get_json()["error"])

    def test_ollama_timeout_returns_504(self):
        with patch.object(
            roadside_app.requests,
            "post",
            side_effect=requests.exceptions.Timeout(),
        ):
            response = self.assess()
        self.assertEqual(response.status_code, 504)

    def test_ollama_http_error_returns_502(self):
        response = Mock()
        response.raise_for_status.side_effect = requests.exceptions.HTTPError()
        with patch.object(roadside_app.requests, "post", return_value=response):
            result = self.assess()
        self.assertEqual(result.status_code, 502)
        self.assertIn("Ollama returned an error", result.get_json()["error"])

    def test_health_route_reports_model_availability(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"models": [{"name": "gemma4:e2b"}]}
        with patch.object(roadside_app.requests, "get", return_value=response):
            result = self.client.get("/api/health")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.get_json()["model_available"])

    def test_health_route_handles_unavailable_ollama(self):
        with patch.object(
            roadside_app.requests,
            "get",
            side_effect=requests.exceptions.ConnectionError(),
        ):
            result = self.client.get("/api/health")
        self.assertEqual(result.status_code, 503)
        self.assertFalse(result.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
