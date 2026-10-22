import json
import os
from flask import Flask, render_template, request, jsonify
import requests

app = Flask(__name__)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e2b")
REQUEST_TIMEOUT = 50
MAX_DESCRIPTION_LENGTH = 2000
ASSESSMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "service_category": {"type": "string", "maxLength": 80},
        "summary": {"type": "string", "maxLength": 180},
        "reported_symptoms": {
            "type": "array",
            "items": {"type": "string", "maxLength": 80},
            "maxItems": 2,
        },
        "possible_explanations": {
            "type": "array",
            "items": {"type": "string", "maxLength": 80},
            "maxItems": 2,
        },
        "severity": {"type": "string", "enum": ["low", "moderate", "high", "emergency"]},
        "safety_advice": {
            "type": "array",
            "items": {"type": "string", "maxLength": 120},
            "maxItems": 2,
        },
        "recommended_action": {"type": "string", "maxLength": 160},
        "follow_up_questions": {
            "type": "array",
            "items": {"type": "string", "maxLength": 100},
            "maxItems": 2,
        },
        "uncertainty": {"type": "string", "maxLength": 160},
    },
    "required": [
        "service_category",
        "summary",
        "reported_symptoms",
        "possible_explanations",
        "severity",
        "safety_advice",
        "recommended_action",
        "follow_up_questions",
        "uncertainty",
    ],
    "additionalProperties": False,
}


def detect_safety_flags(description):
    """Return deterministic high-risk categories and matched user wording."""
    checks = {
        "fire": ("fire", "flames", "burning car", "vehicle is burning"),
        "smoke": ("smoke", "smoking from", "smoke coming"),
        "fuel_leak": (
            "fuel leak", "petrol leak", "gasoline leak", "smell of fuel",
            "smell petrol", "smell gasoline", "fuel smell",
        ),
        "overheating": ("steam", "overheating", "temperature gauge", "hot engine", "coolant"),
        "collision": ("crash", "collision", "accident", "hit a"),
        "traffic": (
            "in the middle of the road", "blocking traffic", "on the highway",
            "on motorway", "traffic lane", "dangerous traffic",
        ),
        "brake_failure": ("brake failure", "brakes failed", "brakes are not working", "brake pedal"),
    }
    text = (description or "").casefold()
    return {
        category: matched
        for category, terms in checks.items()
        if (matched := next((term for term in terms if term in text), None))
    }


def safety_overrides(flags):
    advice = []
    action = "Arrange roadside assistance if the vehicle cannot be driven safely."
    severity = "high" if flags else "moderate"

    if "fire" in flags:
        severity = "emergency"
        advice += [
            "Move everyone well away from the vehicle and traffic; do not approach or open the bonnet.",
            "Contact local emergency services from a safe location."
        ]
        action = "Move away from the vehicle and contact local emergency services."
    if "smoke" in flags:
        severity = "emergency"
        advice += [
            "Move everyone away from the vehicle and traffic; do not investigate the source of the smoke.",
            "Contact local emergency services from a safe location."
        ]
        action = "Move away from the vehicle and contact local emergency services."
    if "fuel_leak" in flags:
        severity = "emergency"
        advice += [
            "Avoid flames, smoking, and anything that could create a spark.",
            "Move everyone away from the vehicle and traffic; do not inspect or repair a suspected leak.",
            "Contact local emergency services from a safe location."
        ]
        action = "Keep clear of the vehicle and contact local emergency services."
    if "overheating" in flags:
        if severity not in ("emergency",):
            severity = "high"
        advice += [
            "Pull over somewhere safe and switch off the engine when safe to do so.",
            "Stay clear of traffic and allow the engine to cool completely.",
            "Never open a hot radiator cap or coolant reservoir, and do not touch hot engine components.",
            "Do not attempt roadside repairs in an unsafe location or continue driving while it is overheating.",
            "Request professional roadside assistance or towing."
        ]
        if action.startswith("Arrange") and severity != "emergency":
            action = "Request roadside assistance or towing; do not continue driving while overheating."
    if "traffic" in flags:
        severity = "emergency"
        advice += [
            "Move away from moving traffic if you can do so safely; do not attempt roadside repairs.",
            "Contact local emergency services if you are in immediate danger."
        ]
        if action.startswith("Arrange"):
            action = "Move to a safe location and contact local emergency services if in immediate danger."
    if "collision" in flags:
        severity = "emergency"
        advice += [
            "Move away from traffic and damaged parts of the vehicle if it is safe to do so.",
            "Contact local emergency services, especially if anyone is injured or there is immediate danger.",
            "Do not drive a vehicle that may be structurally damaged."
        ]
        action = "Move to a safe location and contact local emergency services."
    if "brake_failure" in flags:
        if severity != "emergency":
            severity = "high"
        advice += [
            "Do not drive the vehicle; stop in a safe place if it is moving.",
            "Request professional roadside assistance or towing."
        ]
        if action.startswith("Arrange"):
            action = "Do not drive; request professional roadside assistance or towing."

    return severity, list(dict.fromkeys(advice)), action


def normalize_assessment(data, description):
    if not isinstance(data, dict):
        raise ValueError("AI response was not a JSON object.")

    def text_value(*keys, default, limit):
        value = next((data[key] for key in keys if key in data), default)
        if not isinstance(value, (str, int, float)):
            return default
        return str(value).strip()[:limit] or default

    def string_list(value):
        if isinstance(value, list):
            return [str(item).strip()[:300] for item in value if str(item).strip()][:8]
        if isinstance(value, str) and value.strip():
            return [value.strip()[:300]]
        return []

    allowed_severity = {"low", "moderate", "high", "emergency"}
    severity = str(data.get("severity", "moderate")).lower()
    if severity not in allowed_severity:
        severity = "moderate"

    flags = detect_safety_flags(description)
    result = {
        "service_category": text_value("service_category", "category", default="General roadside assistance", limit=100),
        "summary": text_value("summary", default="The symptoms need further assessment.", limit=700),
        "reported_symptoms": string_list(data.get("reported_symptoms", data.get("symptoms"))),
        "possible_explanations": string_list(data.get("possible_explanations", data.get("possible_causes"))),
        "severity": severity,
        "safety_advice": string_list(data.get("safety_advice", data.get("safety_instructions"))),
        "recommended_action": text_value("recommended_action", "action", default="If the vehicle is not safe to drive, request roadside assistance.", limit=500),
        "follow_up_questions": string_list(data.get("follow_up_questions", data.get("questions"))),
        "uncertainty": text_value("uncertainty", default="The cause cannot be confirmed from the description alone.", limit=400),
        "ai_disclaimer": "AI-assisted preliminary assessment only; this is not a confirmed mechanical diagnosis.",
        "safety_alert": None
    }

    override_severity, override_advice, override_action = safety_overrides(flags)
    # Deterministic safety rules take precedence over model-generated advice.
    if flags:
        rank = {"low": 0, "moderate": 1, "high": 2, "emergency": 3}
        if rank[override_severity] > rank[result["severity"]]:
            result["severity"] = override_severity
        result["safety_advice"] = list(dict.fromkeys(override_advice + result["safety_advice"]))[:10]
        result["recommended_action"] = override_action
        result["safety_alert"] = {
            "matched_keywords": list(flags.values()),
            "message": "A safety-related symptom was recognized. Follow the immediate guidance below before considering possible causes."
        }
    if not result["reported_symptoms"]:
        result["reported_symptoms"] = [description.strip()[:250]]
    if not result["follow_up_questions"]:
        result["follow_up_questions"] = [
            "Are you and your passengers safe and away from traffic?",
            "What warning lights or unusual sounds have you noticed?"
        ]
    return result


@app.get("/")
def index():
    return render_template("index.html", model=OLLAMA_MODEL)


@app.get("/api/health")
def health():
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=4)
        response.raise_for_status()
        models = response.json().get("models", [])
        model_names = [m.get("name", "") for m in models]
        model_available = any(name == OLLAMA_MODEL or name.startswith(OLLAMA_MODEL + ":") for name in model_names)
        return jsonify({"ok": True, "ollama": "connected", "model": OLLAMA_MODEL, "model_available": model_available})
    except (requests.exceptions.RequestException, ValueError, TypeError, AttributeError):
        return jsonify({"ok": False, "ollama": "disconnected", "model": OLLAMA_MODEL, "model_available": False}), 503


@app.post("/api/assess")
def assess():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Please submit a valid assessment form."}), 400
    raw_description = payload.get("description", "")
    if not isinstance(raw_description, str):
        return jsonify({"error": "Please enter a text description of the breakdown."}), 400
    description = raw_description.strip()

    if len(description) < 8:
        return jsonify({"error": "Please describe the breakdown in a little more detail (at least 8 characters)."}), 400
    if len(description) > MAX_DESCRIPTION_LENGTH:
        return jsonify({"error": "Please keep the description under 2,000 characters."}), 400

    vehicle = payload.get("vehicle", {})
    if not isinstance(vehicle, dict):
        vehicle = {}

    vehicle_details = []
    for key, label in [
        ("type", "Vehicle type"), ("make_model", "Make/model"),
        ("powertrain", "Powertrain"), ("can_move", "Can it move?"),
    ]:
        value = str(vehicle.get(key, "")).strip()
        if value:
            vehicle_details.append(f"{label}: {value}")
    context = description
    if vehicle_details:
        context += "\n\nAdditional vehicle details:\n" + "\n".join(vehicle_details)

    system_prompt = """
You are RoadsideAI, a cautious roadside-assistance triage assistant.
Return ONLY valid JSON with these keys:
service_category (string), summary (string), reported_symptoms (array of strings),
possible_explanations (array of strings), severity (one of low, moderate, high, emergency),
safety_advice (array of strings), recommended_action (string),
follow_up_questions (array of strings), uncertainty (string).

Rules:
- First prioritize immediate safety and occupant safety, not diagnosing the car.
- Distinguish symptoms the user reported from possible causes.
- Never claim a cause is confirmed from a short description.
- Do not recommend driving if symptoms may make the vehicle unsafe.
- Never instruct a user to open a hot radiator/coolant cap or touch hot components.
- For fire, smoke, fuel leaks, collision damage, or dangerous roadside positioning, prioritize moving away from danger and contacting local emergency services.
- For overheating with steam, advise stopping safely, switching off the engine when safe, staying clear of traffic, never opening hot coolant parts, and requesting assistance or towing.
- Ask whether the driver and passengers are safe and away from traffic.
- Never encourage risky inspections or roadside repairs.
- Do not claim that help has been dispatched, a booking made, or a provider contacted.
- Keep the language concise, calm, and practical.
- Return only the JSON object, with no reasoning or commentary.
- Keep values brief and limit each list to at most two short items.
- If key facts are missing, ask follow-up questions.
- Uncertainty must be plain language, not a made-up percentage.
"""

    user_prompt = f"Assess this reported vehicle problem:\n{context}"
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "stream": False,
                "format": ASSESSMENT_SCHEMA,
                "think": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "options": {
                    "temperature": 0.2,
                    "num_ctx": 2048,
                    "num_predict": 320,
                }
            },
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        response_data = response.json()
        raw = response_data.get("message", {}).get("content", "") if isinstance(response_data, dict) else ""
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("AI response did not contain JSON.")
        data = json.loads(raw)
        result = normalize_assessment(data, context)
        return jsonify(result)
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not connect to Ollama. Make sure Ollama is running and try again."}), 503
    except requests.exceptions.Timeout:
        return jsonify({"error": "The local AI took too long to respond. Please try again."}), 504
    except (json.JSONDecodeError, ValueError):
        return jsonify({"error": "The AI returned an unreadable response. Please try again."}), 502
    except requests.exceptions.RequestException:
        return jsonify({"error": "Ollama returned an error. Check that the model is installed and available."}), 502
    except Exception:
        app.logger.exception("Unexpected assessment error")
        return jsonify({"error": "Something went wrong while creating the assessment."}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
