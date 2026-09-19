import pywhatkit
import requests
import re
import urllib.parse

def test_yt_search(query):
    print(f"Testing search for: {query}")
    # Method 1: pywhatkit search
    try:
        url = pywhatkit.playonyt(query, open_video=False)
        print(f"pywhatkit URL: {url}")
    except Exception as e:
        print(f"pywhatkit error: {e}")

    # Method 2: Direct HTTP request
    try:
        encoded = urllib.parse.quote(query)
        search_url = f"https://www.youtube.com/results?search_query={encoded}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(search_url, headers=headers, timeout=5)
        video_ids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", resp.text)
        if video_ids:
            print(f"Found video ID via requests: {video_ids[0]}")
            print(f"Full URL: https://www.youtube.com/watch?v={video_ids[0]}")
        else:
            print("No video IDs found in HTML response")
    except Exception as e:
        print(f"Requests error: {e}")

if __name__ == "__main__":
    test_yt_search("Ik Mulaqaat")
