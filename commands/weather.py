from __future__ import annotations

import json
import urllib.request
from typing import Optional


class WeatherCommands:
    """Weather forecast helper using Open-Meteo."""

    def get_weather(self, location: str = "Delhi") -> str:
        try:
            url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.load(response)
            if not data.get("results"):
                return f"No weather data found for {location}."
            result = data["results"][0]
            lat = result["latitude"]
            lon = result["longitude"]
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&timezone=auto"
            with urllib.request.urlopen(weather_url, timeout=10) as response:
                weather_data = json.load(response)
            current = weather_data.get("current_weather", {})
            return f"Weather for {location}: temperature {current.get('temperature')}°C, wind {current.get('windspeed')} km/h."
        except Exception as exc:
            return f"Weather lookup failed: {exc}"
