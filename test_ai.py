import requests
import json

OLLAMA_URL = "http://localhost:11434/api/chat"

payload = {
    "model": "gemma4:e2b",
    "messages": [
        {
            "role": "system",
            "content": (
                "You are RoadsideAI, a cautious roadside assistance "
                "assistant. Do not claim certainty about mechanical faults. "
                "Ask follow-up questions when information is insufficient."
            )
        },
        {
            "role": "user",
            "content": (
                "My car will not start. The dashboard lights work, "
                "but I hear clicking when I turn the key. "
                "Recommend an assistance category and explain the uncertainty."
            )
        }
    ],
    "stream": False
}

def main():
    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=50
        )

        response.raise_for_status()

        data = response.json()

        print("\n--- ROADSIDEAI AI RESPONSE ---\n")
        print(data["message"]["content"])

    except requests.exceptions.RequestException as error:
        print("Could not connect to Ollama:", error)


if __name__ == "__main__":
    main()