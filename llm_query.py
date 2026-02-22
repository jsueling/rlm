import os

import requests

def llm_query(prompt: str) -> str:
    """Queries the local Ollama instance running on the host machine."""

    # host.docker.internal routes traffic from the container to your host machine
    url = "http://host.docker.internal:11434/api/generate"

    payload = {
        "model": os.getenv("OLLAMA_MODEL_NAME"),
        "prompt": prompt,
        "stream": False,
        "options": { "temperature": 0.2 }
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        return f"Sub-Agent Error: {str(e)}"
