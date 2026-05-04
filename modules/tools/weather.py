from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request


class WeatherTools:
    def __init__(self, default_location: str = "") -> None:
        self.default_location = default_location

    def weather(self, text: str) -> str:
        location = self._extract_location(text) or self.default_location
        if not location:
            return "Tell me a city, for example: weather in Dhaka."

        query = urllib.parse.quote(location)
        url = f"https://wttr.in/{query}?format=3"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                weather = response.read().decode("utf-8").strip()
        except (urllib.error.URLError, TimeoutError):
            return f"I could not reach the weather service for {location}."
        return weather or f"I could not get weather for {location}."

    def _extract_location(self, text: str) -> str:
        import re

        match = re.search(r"\bweather\s+(?:in|for|at)\s+(.+)$", text)
        if not match:
            return ""
        return match.group(1).strip(" ?.")
