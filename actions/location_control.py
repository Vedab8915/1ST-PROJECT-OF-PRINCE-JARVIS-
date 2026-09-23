"""Open the in-app globe and navigate to the user's location or a named place."""


def location_control(parameters: dict | None = None, player=None) -> str:
    if player is None or not callable(getattr(player, "show_location", None)):
        return "The in-app globe is unavailable."
    params = parameters or {}
    place = str(params.get("place", "")).strip()
    player.show_location(place)
    return (f"Opening the satellite globe and flying to {place}." if place
            else "Opening the satellite globe and requesting your current location.")


TOOL = {
    "name": "location_control",
    "description": (
        "Displays an interactive satellite globe inside the JARVIS desktop UI, not an external browser. "
        "Use when the user asks where they are, to show their location on a map/globe, or to fly to any named place. "
        "Leave place empty for current location; provide a place name for globe fly-to."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "place": {"type": "STRING", "description": "Place to fly to (city, landmark, address); leave empty to show current device location."}
        },
        "required": [],
    },
    "handler": location_control,
}
