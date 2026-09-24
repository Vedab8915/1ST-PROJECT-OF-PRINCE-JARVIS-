"""A source-aware situational briefing workflow built from JARVIS web search."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
import csv
import io
from pathlib import Path
import sys
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


_FOCUS_HINTS = {
    "aviation": "aircraft, airport, aviation, flight disruptions",
    "weather": "weather alerts, forecast, severe conditions",
    "security": "public safety, official advisories, major incidents",
    "transport": "road, rail, airport, and public transport disruptions",
    "infrastructure": "power, telecom, water, ports, and critical infrastructure",
    "general": "major current events, public alerts, weather, and transport",
}

_COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _get_json(url: str, timeout: float = 12.0):
    request = Request(url, headers={"User-Agent": "JarvisWorldWatch/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def _fetch_json(url: str, timeout: float = 12.0):
    return _get_json(url, timeout)


def _bearing_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
    a = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return bearing, 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1-a)))


def _compass(degrees: float) -> str:
    return _COMPASS[round(degrees / 45) % 8]


def _resolve_area(area: str) -> tuple[float, float, str]:
    query = urlencode({"q": area, "format": "jsonv2", "limit": 1})
    results = _get_json(f"https://nominatim.openstreetmap.org/search?{query}")
    # Nominatim returns a list; normalize it into the same error path as other feeds.
    if not results:
        raise ValueError(f"Could not find the place '{area}'.")
    item = results[0]
    return float(item["lat"]), float(item["lon"]), item.get("display_name", area)


def _current_location(player) -> tuple[float, float, str]:
    # Reuse JARVIS's existing device-location flow and its permission handling.
    report = player.show_location("", wait_for_report=True, timeout=28.0)
    if not isinstance(report, dict):
        raise ValueError("Device location was unavailable. Allow location access or provide a place name.")
    return float(report["latitude"]), float(report["longitude"]), str(report.get("name") or "your location")


def _route_for(callsign: str) -> str:
    # Route metadata is a best-effort lookup and can be missing or stale.
    try:
        payload = _get_json(f"https://api.adsbdb.com/v0/callsign/{quote(callsign.strip())}", timeout=6.0)
        route = payload.get("response", {}).get("flightroute", {}) if isinstance(payload, dict) else {}
        origin = route.get("origin") or {}
        destination = route.get("destination") or {}
        if origin and destination:
            return f"route {origin.get('iata_code') or origin.get('name', 'unknown')} to {destination.get('iata_code') or destination.get('name', 'unknown')}"
    except Exception:
        pass
    return "route/destination unavailable from public metadata"


def _nearby_flights(params: dict, player=None) -> str:
    lat, lon, label = _get_location(params, player)

    radius_nm = max(5, min(150, int(params.get("radius_nm", 50))))
    limit = max(1, min(8, int(params.get("limit", 5))))
    payload = _get_json(f"https://api.adsb.lol/v2/point/{lat}/{lon}/{radius_nm}")
    aircraft = payload.get("aircraft") or payload.get("ac") or []
    candidates = []
    for plane in aircraft:
        if not isinstance(plane, dict) or not isinstance(plane.get("lat"), (int, float)) or not isinstance(plane.get("lon"), (int, float)):
            continue
        seen_pos = plane.get("seen_pos")
        if isinstance(seen_pos, (int, float)) and seen_pos > 90:
            continue
        bearing, km = _bearing_distance(lat, lon, float(plane["lat"]), float(plane["lon"]))
        candidates.append((km, bearing, plane))
    candidates.sort(key=lambda row: row[0])
    checked = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    if not candidates:
        return f"I found no recently positioned aircraft within {radius_nm} nautical miles of {label}. ADS-B coverage may be limited. Checked {checked}."

    lines = [f"{len(candidates)} recently positioned aircraft found within {radius_nm} NM of {label}; closest {min(limit, len(candidates))} shown. Checked {checked}:"]
    for index, (km, bearing, plane) in enumerate(candidates[:limit]):
        callsign = str(plane.get("flight") or "").strip() or "Callsign unavailable"
        kind = str(plane.get("t") or "aircraft type unavailable")
        reg = str(plane.get("r") or "")
        track = plane.get("track")
        heading = f"heading {_compass(float(track))} ({float(track):.0f}°)" if isinstance(track, (int, float)) else "heading unavailable"
        alt = plane.get("alt_baro")
        altitude = f"{int(alt):,} ft" if isinstance(alt, (int, float)) else "altitude unavailable"
        speed = plane.get("gs")
        speed_text = f"{float(speed):.0f} kt" if isinstance(speed, (int, float)) else "speed unavailable"
        side = _compass(bearing)
        route = _route_for(callsign) if index < 5 and callsign != "Callsign unavailable" else "route/destination unavailable from public metadata"
        lines.append(
            f"{index+1}. {callsign} ({kind}{', ' + reg if reg else ''}); "
            f"{km:.1f} km away, {side} of you (bearing {bearing:.0f}°); {heading}; "
            f"{altitude}; {speed_text}; {route}."
        )
    lines.append("Distance is the straight-line ground distance from the selected location. Live positions come from community ADS-B receivers; coverage and route metadata can be incomplete or delayed.")
    return "\n".join(lines)


def _track_flight(params: dict, player=None) -> str:
    callsign = str(params.get("query", "")).strip().upper()
    if not callsign:
        return "Give me a flight callsign, for example AAL123, or ask for nearby flights to select one."
    payload = _fetch_json(f"https://api.adsb.lol/v2/callsign/{quote(callsign)}")
    aircraft = payload.get("aircraft") or payload.get("ac") or []
    aircraft = [p for p in aircraft if isinstance(p, dict) and isinstance(p.get("lat"), (int, float)) and isinstance(p.get("lon"), (int, float))]
    if not aircraft:
        return f"No current ADS-B position was found for {callsign}. It may be outside receiver coverage or the callsign may differ."
    plane = min(aircraft, key=lambda p: p.get("seen_pos", 9999) if isinstance(p.get("seen_pos"), (int, float)) else 9999)
    out = [f"Current ADS-B contact for {callsign}: position {float(plane['lat']):.5f}, {float(plane['lon']):.5f}; type {plane.get('t', 'unknown')}; registration {plane.get('r', 'unavailable')}; altitude {plane.get('alt_baro', 'unavailable')} ft; speed {plane.get('gs', 'unavailable')} kt; track {plane.get('track', 'unavailable')}°. Seen {plane.get('seen_pos', 'unknown')} seconds ago.", _route_for(callsign)]
    out.append("This is a recent transponder position, not continuous camera tracking.")
    return " ".join(out)


def _get_location(params: dict, player=None) -> tuple[float, float, str]:
    area = str(params.get("area", "")).strip()
    if params.get("latitude") is not None and params.get("longitude") is not None:
        lat, lon = float(params["latitude"]), float(params["longitude"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Coordinates are outside valid latitude/longitude ranges.")
        return lat, lon, area or f"{lat:.4f}, {lon:.4f}"
    if area:
        return _resolve_area(area)
    if player is None or not callable(getattr(player, "show_location", None)):
        raise ValueError("Give me a city/region or allow device location.")
    return _current_location(player)


def _nearby_earthquakes(params: dict, player=None) -> str:
    lat, lon, label = _get_location(params, player)
    radius_km = max(10, min(1000, int(params.get("radius_km", 250))))
    query = urlencode({
        "format": "geojson", "starttime": (datetime.now(timezone.utc)-timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        "latitude": lat, "longitude": lon, "maxradiuskm": radius_km,
        "minmagnitude": max(0.0, float(params.get("min_magnitude", 2.5))), "orderby": "time", "limit": 100,
    })
    data = _fetch_json(f"https://earthquake.usgs.gov/fdsnws/event/1/query?{query}")
    features = data.get("features", [])
    if not features:
        return f"No earthquakes matching the selected magnitude threshold were reported within {radius_km} km of {label} in the past 24 hours. Source: USGS."
    lines = [f"{len(features)} reported earthquakes within {radius_km} km of {label} in the past 24 hours; largest first:"]
    features.sort(key=lambda item: item.get("properties", {}).get("mag") or 0, reverse=True)
    for item in features[:8]:
        p = item.get("properties", {})
        coords = item.get("geometry", {}).get("coordinates", [])
        distance = _bearing_distance(lat, lon, float(coords[1]), float(coords[0]))[1] if len(coords) >= 2 else None
        age = max(0, (datetime.now(timezone.utc).timestamp()*1000 - (p.get("time") or 0))/60000)
        lines.append(f"Magnitude {p.get('mag', 'unknown')}, {p.get('place', 'location unavailable')}, {distance:.0f} km away, about {age:.0f} minutes ago. {p.get('url', '')}" if distance is not None else f"Magnitude {p.get('mag', 'unknown')}, {p.get('place', 'location unavailable')}. {p.get('url', '')}")
    return "\n".join(lines) + "\nSource: USGS Earthquake Hazards Program."


def _weather(params: dict, player=None) -> str:
    lat, lon, label = _get_location(params, player)
    query = urlencode({
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m",
        "hourly": "precipitation_probability,temperature_2m,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset",
        "forecast_days": 2, "timezone": "auto",
    })
    data = _fetch_json(f"https://api.open-meteo.com/v1/forecast?{query}")
    current = data.get("current", {})
    daily = data.get("daily", {})
    hourly = data.get("hourly", {})
    code = current.get("weather_code")
    description = _weather_description(code)
    out = [f"Weather near {label}: {description}, {current.get('temperature_2m', 'N/A')}°C (feels {current.get('apparent_temperature', 'N/A')}°C), humidity {current.get('relative_humidity_2m', 'N/A')}%, wind {current.get('wind_speed_10m', 'N/A')} km/h at {current.get('wind_direction_10m', 'N/A')}°, gusts {current.get('wind_gusts_10m', 'N/A')} km/h."]
    if daily.get("time"):
        out.append(f"Today {daily.get('temperature_2m_min', ['?'])[0]}–{daily.get('temperature_2m_max', ['?'])[0]}°C; sunrise {daily.get('sunrise', ['?'])[0]}, sunset {daily.get('sunset', ['?'])[0]}.")
    if hourly.get("time"):
        idx = next((i for i, t in enumerate(hourly["time"]) if t >= current.get("time", "")), 0)
        probs = hourly.get("precipitation_probability", [])
        temps = hourly.get("temperature_2m", [])
        if probs and temps and idx < len(probs):
            out.append(f"Next forecast hour: {temps[idx]}°C, precipitation chance {probs[idx]}%.")
    out.append(f"Forecast valid around {current.get('time', 'the provider update')}; sourced from Open-Meteo, which combines national weather models.")
    return "\n".join(out)


def _weather_description(code) -> str:
    if code is None:
        return "conditions unavailable"
    if code == 0: return "clear sky"
    if code in (1, 2): return "mostly clear or partly cloudy"
    if code == 3: return "overcast"
    if code in (45, 48): return "fog"
    if code in (51, 53, 55, 56, 57): return "drizzle"
    if code in (61, 63, 65, 66, 67, 80, 81, 82): return "rain or showers"
    if code in (71, 73, 75, 77, 85, 86): return "snow"
    if code in (95, 96, 99): return "thunderstorm"
    return "conditions unavailable"


def _cyclones(params: dict, player=None) -> str:
    data = _fetch_json("https://www.nhc.noaa.gov/CurrentStorms.json")
    storms = data.get("activeStorms", [])
    if not storms:
        return "NOAA reports no active tropical cyclones in its Atlantic and eastern/central Pacific active-storm feed."
    lines = [f"NOAA active tropical cyclone advisories ({len(storms)}):"]
    for storm in storms[:12]:
        name = storm.get("name", "Unnamed system")
        ident = storm.get("id", "")
        classification = storm.get("classification", "")
        lines.append(f"{name} {ident} {classification}. Advisory details: https://www.nhc.noaa.gov/?{ident.lower()}")
    return "\n".join(lines)


def _launches(params: dict, player=None) -> str:
    limit = max(1, min(8, int(params.get("limit", 5))))
    data = _fetch_json(f"https://ll.thespacedevs.com/2.3.0/launches/upcoming/?{urlencode({'limit': limit, 'mode': 'list'})}")
    results = data.get("results", [])
    if not results:
        return "No upcoming launches are currently listed by Launch Library 2."
    lines = ["Upcoming space launches (schedule can change):"]
    for launch in results:
        mission = launch.get("mission") or {}
        provider = launch.get("launch_service_provider") or {}
        pad = launch.get("pad") or {}
        lines.append(f"{launch.get('net', 'date unknown')}: {launch.get('name', 'Unnamed launch')}; {provider.get('name', 'provider unknown')}; {pad.get('name', 'pad unknown')} ({(pad.get('location') or {}).get('name', 'location unknown')}); mission {mission.get('name', 'details unavailable')}. {launch.get('url', '')}")
    return "\n".join(lines) + "\nSource: The Space Devs Launch Library 2. Times are NET estimates and may move."


def _route(params: dict, player=None) -> str:
    origin = str(params.get("origin", "")).strip()
    destination = str(params.get("destination", "")).strip()
    if not origin or not destination:
        return "Please provide both a starting place and destination for directions."
    lat1, lon1, origin_name = _resolve_area(origin)
    lat2, lon2, destination_name = _resolve_area(destination)
    mode = str(params.get("mode", "driving")).lower()
    profile, network = {
        "driving": ("driving", "routed-car"), "walking": ("foot", "routed-foot"),
        "cycling": ("driving", "routed-bike"),
    }.get(mode, ("driving", "routed-car"))
    coords = f"{lon1},{lat1};{lon2},{lat2}"
    url = f"https://routing.openstreetmap.de/{network}/route/v1/{profile}/{coords}?steps=true&overview=false"
    data = _fetch_json(url)
    routes = data.get("routes", [])
    if not routes:
        return f"No {profile} route was found between {origin_name} and {destination_name}."
    route = routes[0]
    steps = (route.get("legs") or [{}])[0].get("steps", [])
    directions = []
    for step in steps[:12]:
        maneuver = step.get("maneuver", {})
        name = step.get("name") or "unnamed road"
        verb = maneuver.get("modifier") or maneuver.get("type", "continue")
        directions.append(f"{verb} on {name}")
    result = f"{profile.title()} route {origin_name} to {destination_name}: {route.get('distance', 0)/1000:.1f} km, about {route.get('duration', 0)/60:.0f} minutes."
    if directions: result += " Steps: " + "; ".join(directions) + "."
    return result + " Route uses OpenStreetMap routing and is not live traffic-aware."


def _osm_inventory(params: dict, player=None) -> str:
    lat, lon, label = _get_location(params, player)
    radius = max(1000, min(50000, int(params.get("radius_km", 10))*1000))
    kind = str(params.get("focus", "infrastructure")).lower()
    tag_query = {
        "infrastructure": '(nwr(around:R,LAT,LON)[man_made~"^(works|communications_tower|surveillance)$"];nwr(around:R,LAT,LON)[waterway=dam];nwr(around:R,LAT,LON)[telecom=datacenter];)',
        "cameras": 'nwr(around:R,LAT,LON)[man_made=surveillance];',
        "alpr": 'nwr(around:R,LAT,LON)[surveillance:type~"(?i)alpr|license_plate|ANPR"];',
        "dams": 'nwr(around:R,LAT,LON)[waterway=dam];',
    }.get(kind, 'nwr(around:R,LAT,LON)[man_made=surveillance];')
    q = f"[out:json][timeout:18];({tag_query.replace('R', str(radius)).replace('LAT', str(lat)).replace('LON', str(lon))});out center tags 80;"
    url = "https://overpass-api.de/api/interpreter?" + urlencode({"data": q})
    data = _fetch_json(url, timeout=25.0)
    items = data.get("elements", [])
    label_kind = {"infrastructure":"mapped infrastructure", "cameras":"mapped public surveillance cameras", "alpr":"mapped ALPR/ANPR camera locations", "dams":"mapped dams"}.get(kind, kind)
    if not items:
        return f"No {label_kind} were returned within {radius//1000} km of {label}. OpenStreetMap coverage and tagging vary."
    lines = [f"{len(items)} {label_kind} mapped within {radius//1000} km of {label}; these are OSM-mapped locations, not live feeds:"]
    for item in items[:12]:
        tags = item.get("tags", {})
        name = tags.get("name") or tags.get("surveillance:type") or tags.get("waterway") or tags.get("man_made") or tags.get("telecom") or "mapped feature"
        lines.append(f"- {name}; {tags.get('operator', 'operator not listed')}")
    return "\n".join(lines) + "\nSource: OpenStreetMap contributors. No camera video or license-plate data is accessed."


def _provider_key(name: str) -> str:
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    try:
        config = json.loads((base / "config" / "api_keys.json").read_text(encoding="utf-8"))
        return str(config.get(name) or "").strip()
    except Exception:
        return ""


def _fires(params: dict, player=None) -> str:
    key = _provider_key("nasa_firms_api_key")
    if not key:
        return "NASA FIRMS active-fire detections need a free NASA FIRMS MAP_KEY. Add it to config/api_keys.json as nasa_firms_api_key to enable this layer."
    lat, lon, label = _get_location(params, player)
    radius = max(5, min(250, int(params.get("radius_km", 50))))
    dlat = radius / 111.0
    dlon = min(180, radius / max(15, 111.0 * math.cos(math.radians(lat))))
    area = f"{lon-dlon},{max(-90,lat-dlat)},{lon+dlon},{min(90,lat+dlat)}"
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{quote(key)}/VIIRS_SNPP_NRT/{quote(area, safe=',-')}/1"
    request = Request(url, headers={"User-Agent": "JarvisWorldWatch/1.0"})
    with urlopen(request, timeout=20) as response:
        csv_text = response.read().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    fires = []
    for row in rows:
        try:
            f_lat, f_lon = float(row["latitude"]), float(row["longitude"])
            bearing, distance = _bearing_distance(lat, lon, f_lat, f_lon)
            fires.append((distance, bearing, row))
        except (KeyError, ValueError, TypeError):
            continue
    fires.sort(key=lambda entry: entry[0])
    if not fires:
        return f"NASA FIRMS reported no VIIRS detections in the past day within about {radius} km of {label}. Satellite detections can miss obscured or small fires and are not ground confirmation."
    lines = [f"NASA FIRMS VIIRS detections near {label} in the past day: {len(fires)} points in the requested area; nearest first."]
    for distance, bearing, row in fires[:8]:
        lines.append(f"{distance:.1f} km {_compass(bearing)}; {row.get('acq_date', '')} {row.get('acq_time', '')} UTC; confidence {row.get('confidence', 'unknown')}; fire radiative power {row.get('frp', 'unknown')} MW.")
    return "\n".join(lines) + "\nNASA FIRMS detections are satellite observations, not confirmation of an active ground fire."


def _satellite_catalog(params: dict, player=None) -> str:
    term = str(params.get("query", "ISS")).strip().lower()
    group = "stations" if any(word in term for word in ("iss", "station", "crew")) else "visual"
    data = _fetch_json(f"https://celestrak.org/NORAD/elements/gp.php?{urlencode({'GROUP': group, 'FORMAT': 'json'})}")
    matches = [obj for obj in data if term in str(obj.get("OBJECT_NAME", "")).lower()]
    if not matches and term in {"iss", "international space station"}:
        matches = [obj for obj in data if "ISS" in str(obj.get("OBJECT_NAME", "")).upper() or str(obj.get("NORAD_CAT_ID", "")) == "25544"]
    if not matches:
        return f"No matching object was found in the CelesTrak {group} orbital-elements group."
    out = ["Current public orbital elements from CelesTrak (not a pass prediction):"]
    for sat in matches[:5]:
        mean_motion = sat.get("MEAN_MOTION")
        period = f"{1440/float(mean_motion):.1f} min" if mean_motion else "unknown period"
        out.append(f"{sat.get('OBJECT_NAME', 'Unknown')}; NORAD ID {sat.get('NORAD_CAT_ID', 'unknown')}; orbital period {period}; epoch {sat.get('EPOCH', 'unknown')}.")
    out.append("Pass rise/peak/set and visual visibility require orbit propagation; this JARVIS action does not calculate those yet.")
    return "\n".join(out)


def _satellite_pass(params: dict, player=None) -> str:
    term = str(params.get("query", "ISS")).strip().lower()
    lat, lon, label = _get_location(params, player)
    group = "stations" if any(word in term for word in ("iss", "station", "crew")) else "visual"
    tle_rows = _fetch_json(f"https://celestrak.org/NORAD/elements/gp.php?{urlencode({'GROUP': group, 'FORMAT': 'json'})}")
    match = next((row for row in tle_rows if term in str(row.get("OBJECT_NAME", "")).lower()), None)
    if match is None and term in {"iss", "international space station"}:
        match = next((row for row in tle_rows if str(row.get("NORAD_CAT_ID", "")) == "25544"), None)
    if match is None:
        return f"I couldn't find '{term}' in CelesTrak's {group} group. Try ISS, Hubble, or a known satellite name."
    try:
        from skyfield.api import EarthSatellite, load, wgs84
    except ImportError:
        return "Satellite pass prediction needs Skyfield. Install the project requirements, then restart JARVIS."
    ts = load.timescale(builtin=True)
    satellite = EarthSatellite.from_omm(ts, match)
    observer = wgs84.latlon(lat, lon)
    start = ts.now()
    end = ts.from_datetime(start.utc_datetime() + timedelta(days=1))
    times, events = satellite.find_events(observer, start, end, altitude_degrees=10.0)
    labels = ("rise", "peak", "set")
    passes, current = [], {}
    for time, event in zip(times, events):
        current[labels[int(event)]] = time.utc_datetime().astimezone().strftime("%H:%M %Z")
        if int(event) == 1:
            topocentric = (satellite - observer).at(time)
            current["altitude"] = f"{topocentric.altaz()[0].degrees:.0f}°"
        if int(event) == 2:
            if all(key in current for key in ("rise", "peak", "set")):
                passes.append(current)
            current = {}
    if not passes:
        return f"No pass above 10° elevation for {match.get('OBJECT_NAME', term)} at {label} in the next 24 hours, according to the current CelesTrak orbital elements."
    lines = [f"Next visible-horizon passes for {match.get('OBJECT_NAME', term)} near {label} (next 24 hours; model-based):"]
    for item in passes[:3]:
        lines.append(f"Rise {item['rise']}, peak {item['peak']} at {item.get('altitude', 'unknown elevation')}, set {item['set']}.")
    lines.append("A pass above 10° is geometrically above the horizon; clouds, buildings, twilight and satellite sunlight affect naked-eye visibility. Orbital elements can be stale.")
    return "\n".join(lines)


def _radio(params: dict, player=None) -> str:
    query = {"name": str(params.get("query") or params.get("area") or "news").strip(), "limit": 8, "hidebroken": "true"}
    data = _fetch_json("https://de1.api.radio-browser.info/json/stations/search?" + urlencode(query))
    if not data:
        return f"No Radio Browser stations found for {query['name']}."
    lines = [f"Radio stations matching {query['name']}:"]
    for i, station in enumerate(data[:8], 1):
        lines.append(f"{i}. {station.get('name', 'Unknown station')} — {station.get('country', 'country unknown')}, {station.get('language', 'language unknown')}; tags {station.get('tags') or 'none'}; {station.get('url_resolved') or station.get('url', '')}")
    if str(params.get("play", "false")).lower() in {"1", "true", "yes"}:
        import webbrowser
        stream = data[0].get("url_resolved") or data[0].get("url")
        if stream and webbrowser.open(stream):
            lines.append(f"Opened the stream for {data[0].get('name', 'the top matching station')} in the default media handler.")
        else:
            lines.append("I found stations but could not open the stream on this machine.")
    return "\n".join(lines) + "\nSource: Radio Browser community directory."


def _data_availability(task: str) -> str:
    if task in {"ships", "vessels"}:
        return "Live vessel AIS data needs an AISStream API key; JARVIS is not configured for that feed yet. I cannot report current ships without that key."
    if task in {"fires", "fire"}:
        return "NASA FIRMS active-fire data needs a NASA FIRMS map key; it is not configured in JARVIS. I will not substitute unverified fire reports for live detections."
    if task in {"traffic", "traffic_flow"}:
        return "JARVIS can provide an OSM driving route, but it has no TomTom live-flow key. I cannot report current traffic speeds or individual vehicle positions."
    if task in {"transit", "buses", "trains", "bikeshare"}:
        return "Live transit and bikeshare feeds are operator- and city-specific. This JARVIS skill does not yet have a configured feed for that location."
    if task in {"cctv", "camera_video", "viewshed", "cockpit", "scene", "director", "sensor_style", "hud", "whiteboard"}:
        return "That God’s Eye View function depends on its interactive globe, camera rendering, or scene state. JARVIS’s current UI-free workflow cannot provide that visual operation."
    return "That public-data layer is not implemented in this JARVIS workflow yet."


def _global_context(params: dict, player=None) -> str:
    lat, lon, label = _get_location(params, player)
    local = {**params, "latitude": lat, "longitude": lon, "area": label}
    sections = [f"JARVIS situation brief for {label} (public-data workflow; no God's Eye View UI):"]
    for title, handler, values in (
        ("AIRCRAFT", _nearby_flights, {**local, "radius_nm": params.get("radius_nm", 50), "limit": 3}),
        ("WEATHER", _weather, local),
        ("EARTHQUAKES", _nearby_earthquakes, {**local, "radius_km": params.get("radius_km", 250), "min_magnitude": params.get("min_magnitude", 3)}),
        ("MAPPED INFRASTRUCTURE", _osm_inventory, {**local, "focus": "infrastructure", "radius_km": 10}),
    ):
        try:
            sections.append(f"\n{title}\n{handler(values, player=player)}")
        except Exception as exc:
            sections.append(f"\n{title}\nFeed unavailable: {exc}")
    sections.append("\nFeeds have different update delays and coverage. Mapped assets are not live activity reports.")
    return "\n".join(sections)


def world_watch(parameters: dict, player=None) -> str:
    """Query a JARVIS-friendly subset of God's Eye View's public data workflows."""
    params = parameters or {}
    task = str(params.get("task", "briefing")).strip().lower().replace(" ", "_")
    focus = str(params.get("focus", "general")).strip().lower()
    handlers = {
        "flight": _nearby_flights, "flights": _nearby_flights, "nearby_flights": _nearby_flights,
        "aircraft": _nearby_flights, "track": _track_flight, "track_flight": _track_flight,
        "earthquakes": _nearby_earthquakes, "quakes": _nearby_earthquakes,
        "weather": _weather, "wind": _weather, "cyclones": _cyclones, "hurricanes": _cyclones,
        "launches": _launches, "space_missions": _launches,
        "satellites": _satellite_pass, "satellite_pass": _satellite_pass,
        "orbit_catalog": _satellite_catalog,
        "route": _route, "directions": _route, "infrastructure": _osm_inventory,
        "cameras": _osm_inventory, "cctv_locations": _osm_inventory,
        "alpr": _osm_inventory, "dams": _osm_inventory,
        "radio": _radio, "stations": _radio, "fires": _fires, "fire": _fires,
    }
    if task in {"global", "global_context", "situation", "situational_briefing"}:
        try:
            return _global_context(params, player=player)
        except Exception as exc:
            return f"Could not build the situation brief: {exc}"
    if task in handlers:
        try:
            if task in {"cameras", "cctv_locations"}: params = {**params, "focus": "cameras"}
            elif task == "alpr": params = {**params, "focus": "alpr"}
            elif task == "dams": params = {**params, "focus": "dams"}
            elif task == "infrastructure": params = {**params, "focus": "infrastructure"}
            return handlers[task](params, player=player)
        except Exception as exc:
            return f"The {task.replace('_', ' ')} lookup failed: {exc}. Check connectivity and try again."
    if task != "briefing":
        return _data_availability(task)
    area = str(params.get("area", "")).strip()
    if not area:
        return "Please provide a city, region, or country to scan."
    if focus not in _FOCUS_HINTS:
        focus = "general"

    if player:
        try:
            player.write_log(f"[WorldWatch] Scanning {area} ({focus})")
        except Exception:
            pass

    from actions.web_search import web_search

    subject = _FOCUS_HINTS[focus]
    news = web_search({"query": f"{subject} in {area}", "mode": "news"}, player=player)
    context = web_search({
        "query": f"Current official alerts and operational status for {area}: {subject}. "
                 "Prefer government, operator, or primary sources; include dates and links.",
        "mode": "research",
    }, player=player)

    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    return (
        f"WORLD WATCH — {area} | Focus: {focus} | Checked: {stamp}\n\n"
        "RECENT REPORTS\n" + str(news) + "\n\n"
        "OFFICIAL / OPERATIONAL CONTEXT\n" + str(context) + "\n\n"
        "This is a web-based public-information scan, not a live sensor feed. "
        "Treat search results as reports; verify urgent or safety-critical details "
        "with the linked official source. Distinguish confirmed facts from estimates."
    )


TOOL = {
    "name": "world_watch",
    "description": (
        "Run location-aware public-data workflows without God's Eye View's interface. "
        "Supported task values: flights/track_flight, weather/wind, earthquakes, cyclones, launches, "
        "satellites (next pass; Skyfield), orbit_catalog, route/directions, infrastructure, cameras "
        "(location tags only), alpr (location tags only), "
        "dams, radio, briefing, global_context. For local queries provide area or coordinates; leave area empty "
        "to use device location when supported. Flights include distance, side, heading, altitude, "
        "speed, callsign/type and best-effort route. Ships/traffic/transit require feeds; fires need "
        "a NASA FIRMS MAP_KEY. "
        "keys and must be reported unavailable unless configured. Visual globe-only operations "
        "such as cockpit, sensor filters, trails, scene director and annotations are not available."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "area": {"type": "STRING", "description": "City, region, or country"},
            "task": {"type": "STRING", "description": "global_context | briefing | flights | track_flight | weather | earthquakes | cyclones | launches | satellites (pass times) | orbit_catalog | fires | route | infrastructure | cameras | alpr | dams | radio | ships | traffic | transit | bikeshare"},
            "latitude": {"type": "NUMBER", "description": "Optional search latitude"},
            "longitude": {"type": "NUMBER", "description": "Optional search longitude"},
            "radius_nm": {"type": "INTEGER", "description": "Nearby flight radius in nautical miles, 5–150; default 50"},
            "limit": {"type": "INTEGER", "description": "Maximum aircraft to report, 1–8; default 5"},
            "focus": {
                "type": "STRING",
                "description": "Briefing: general | aviation | weather | security | transport | infrastructure. Inventory: infrastructure | cameras | alpr | dams",
            },
            "origin": {"type": "STRING", "description": "Starting place for task=route"},
            "destination": {"type": "STRING", "description": "Destination for task=route"},
            "mode": {"type": "STRING", "description": "driving | walking | cycling for task=route"},
            "query": {"type": "STRING", "description": "Satellite or radio search term"},
            "play": {"type": "BOOLEAN", "description": "Open the first matching radio station stream"},
            "min_magnitude": {"type": "NUMBER", "description": "Minimum earthquake magnitude; default 2.5"},
            "radius_km": {"type": "INTEGER", "description": "Search radius for earthquakes or OSM locations in km"},
        },
        "required": [],
    },
    "handler": world_watch,
}
