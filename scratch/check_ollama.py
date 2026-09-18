import requests
import json

def check_ollama(url):
    print(f"Testing Ollama at {url}...")
    try:
        resp = requests.get(f"{url}/api/tags", timeout=3)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("name") for m in data.get("models", [])]
            print(f"Installed Models ({len(models)}): {models}")
            return True, models
        else:
            print(f"Error response: {resp.text}")
            return False, []
    except Exception as e:
        print(f"Connection failed to {url}: {e}")
        return False, []

if __name__ == "__main__":
    ok1, models1 = check_ollama("http://localhost:11434")
    ok2, models2 = check_ollama("http://127.0.0.1:11434")
