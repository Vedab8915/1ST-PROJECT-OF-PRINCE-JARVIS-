"""Open the JARVIS map, show local weather, and optionally enable live layers."""
import re


def location_control(parameters: dict | None = None, player=None) -> str:
    if player is None or not callable(getattr(player, "show_location", None)):
        return "The in-app globe is unavailable."
    params = parameters or {}
    place = str(params.get("place", "")).strip()
    live_layers = [str(x).strip().lower() for x in (params.get("live_layers") or [])
                   if str(x).strip().lower() in {"flights", "ships"}]
    words = set(re.findall(r"[a-z]+", place.lower()))
    celestial = {"solar", "system", "planets", "sun", "mercury", "venus", "earth",
                 "moon", "luna", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"}
    if words & celestial:
        player.show_location(place)
        return (f"Opened the NASA solar-system view for {place}." if place
                else "Opened the NASA solar-system view.")

    report = player.show_location(place, wait_for_report=True, timeout=28.0, live_layers=live_layers)
    if not isinstance(report, dict):
        return "The map is open, but location or weather details did not arrive. Check location permission and internet access."

    name = str(report.get("name") or "Selected location")
    region = str(report.get("region") or "")
    lat, lon = report.get("latitude"), report.get("longitude")
    summary = f"Location: {name}{', ' + region if region and region.lower() not in name.lower() else ''}."
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        summary += f" Coordinates: {lat:.5f}, {lon:.5f}."
    weather = report.get("weather")
    if isinstance(weather, dict):
        summary += (f" Current weather: {weather.get('description', 'conditions unavailable')}, "
                    f"{weather.get('temperature_c', 'unknown')}°C, feels like "
                    f"{weather.get('feels_like_c', 'unknown')}°C, humidity "
                    f"{weather.get('humidity_percent', 'unknown')}%, wind "
                    f"{weather.get('wind_kmh', 'unknown')} km/h.")
        low, high = weather.get("today_low_c"), weather.get("today_high_c")
        if isinstance(low, (int, float)) and isinstance(high, (int, float)):
            summary += f" Today's range: {low}–{high}°C."
    else:
        summary += " Current weather details are unavailable."
    if live_layers:
        summary += " Live map layers requested: " + ", ".join(live_layers) + ". Click a contact on the map to follow its live position and trail."
    return summary


TOOL = {
    "name": "location_control",
    "description": (
        "Displays an interactive satellite globe inside the JARVIS desktop UI, not an external browser. "
        "Use when the user asks where they are, to show their location on the JARVIS map, or to fly to any named place. "
        "When they ask to visually see live aircraft or ships, call this with live_layers containing 'flights' and/or 'ships'; leave place empty for nearby contacts. "
        "For Earth locations it also returns the resolved place name, coordinates and current weather. "
        "Use place='solar system' or a body name (Moon, Mars, Jupiter, etc.) to open NASA's interactive solar-system viewer. "
        "Leave place empty for current device location."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "place": {"type": "STRING", "description": "Place to fly to (city, landmark, address); leave empty to show current device location."},
            "live_layers": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Optional visual live map layers: flights, ships"},
        },
        "required": [],
    },
    "handler": location_control,
}
