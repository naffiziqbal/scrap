from __future__ import annotations

import csv
import json
import math
import re
import sys
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

CSV_PATH = Path("georgia_hotels_20251106_015055.csv")
BATUMI_CENTER = (41.650677, 41.636669)  # approx city center lat, lon


def _safe_json_loads(value: str) -> Any:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    # Normalize doubled quotes that often appear in CSV-escaped JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to fix common CSV-embedded JSON issues by replacing doubled quotes
        fixed = re.sub(r'""', '"', text)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _derive_category_from_title(title: str) -> str:
    lowered = title.lower()
    if any(word in lowered for word in ["apartment", "suite", "studio"]):
        return "Apartment"
    if "guest house" in lowered or "guesthouse" in lowered:
        return "Guesthouse"
    if "hostel" in lowered:
        return "Hostel"
    if "resort" in lowered:
        return "Resort"
    return "Hotel"


def _first_or_none(items: Optional[Iterable[str]]) -> Optional[str]:
    if not items:
        return None
    for x in items:
        if x:
            return x
    return None


def _clean_services(services: Any) -> List[str]:
    if isinstance(services, list):
        return [str(s).strip() for s in services if isinstance(s, (str, int, float)) and str(s).strip()]
    return []


def _parse_rooms(rooms_raw: Any, hotel_gallery: List[str]) -> List[Dict[str, Any]]:
    rooms: List[Dict[str, Any]] = []
    if not isinstance(rooms_raw, list):
        return rooms

    def infer_type(name: Optional[str]) -> str:
        if not name:
            return "Room"
        lowered = name.lower()
        if "suite" in lowered:
            return "Suite"
        if "apartment" in lowered:
            return "Apartment"
        if "studio" in lowered:
            return "Studio"
        if "king" in lowered or "queen" in lowered or "double" in lowered:
            return "Standard"
        return "Room"

    for item in rooms_raw:
        if not isinstance(item, dict):
            continue
        room_name = item.get("name") if isinstance(item.get("name"), str) else None
        description = item.get("description") if isinstance(item.get("description"), str) else None
        price_amount = _to_float(item.get("price_amount")) or _to_float(item.get("price"))

        # Derive quantity from availability options if present
        quantity: int = 1
        availability = item.get("availability")
        if isinstance(availability, list):
            # try to find the largest numeric label or value
            max_val = 1
            for opt in availability:
                if isinstance(opt, dict):
                    candidates = []
                    if "value" in opt:
                        candidates.append(str(opt.get("value")))
                    if "label" in opt:
                        candidates.append(str(opt.get("label")))
                    for c in candidates:
                        m = re.search(r"(\d+)", c)
                        if m:
                            max_val = max(max_val, int(m.group(1)))
            quantity = max_val

        rooms.append(
            {
                "type": infer_type(room_name),
                "name": room_name or "Room",
                "image": _first_or_none(hotel_gallery) or "",
                "price": price_amount or 0.0,
                "quantity": int(quantity),
                "information": description or "",
                "gallery": hotel_gallery[:6],
            }
        )

    return rooms


def _derive_rating_from_services(services: List[str]) -> float:
    # Map number of services to a plausible rating between 3.5 and 5.0
    if not services:
        return 4.0
    score = 3.5 + min(1.5, (len(services) / 50.0) * 1.5)
    return round(score, 2)


def _derive_price(search_pricing: Any, rooms: List[Dict[str, Any]]) -> Optional[float]:
    if isinstance(search_pricing, dict):
        v = _to_float(search_pricing.get("current_price_amount"))
        if v is not None:
            return v
    for room in rooms:
        v = _to_float(room.get("price"))
        if v is not None and v > 0:
            return v
    return None


def sanitize_hotels_from_csv(csv_path: Path = CSV_PATH, country: str = "Georgia") -> Dict[str, Any]:
    sanitized: List[Dict[str, Any]] = []

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = (row.get("title") or "").strip()
            description = (row.get("description") or "").strip()
            url = (row.get("url") or "").strip()
            
            # Get location and city from CSV
            location = (row.get("location") or "").strip()
            city = (row.get("city") or "").strip()
            # If location is empty, use city as fallback
            if not location:
                location = city

            facilities_raw = _safe_json_loads(row.get("facilities") or "")
            services = _clean_services(facilities_raw)

            gallery_raw = _safe_json_loads(row.get("gallery") or "")
            gallery = [g for g in (gallery_raw or []) if isinstance(g, str) and g.strip()]

            latitude = _to_float(row.get("latitude"))
            longitude = _to_float(row.get("longitude"))

            rooms_raw = _safe_json_loads(row.get("rooms") or "")
            rooms = _parse_rooms(rooms_raw, gallery)

            search_pricing_raw = _safe_json_loads(row.get("search_pricing") or "")
            price = _derive_price(search_pricing_raw, rooms)

            # Distance from Batumi center if coords exist
            if latitude is not None and longitude is not None:
                distance_km = _haversine_km(latitude, longitude, BATUMI_CENTER[0], BATUMI_CENTER[1])
            else:
                distance_km = None

            # Fill derived fields
            category = _derive_category_from_title(title or description)
            image = _first_or_none(gallery) or ""
            rating = _derive_rating_from_services(services)
            distance = round(distance_km, 2) if distance_km is not None else 0.0

            # Build id from stable hash of url or title
            basis = url or title or json.dumps([title, description])
            hid = sha1(basis.encode("utf-8")).hexdigest()[:16]

            hotel_entry: Dict[str, Any] = {
                "id": hid,
                "title": title or "Untitled",
                "category": category,
                "description": description or (f"Stay at {title}" if title else ""),
                "image": image,
                "gallery": gallery,
                "location": location,
                "city": city,
                "country": country,
                "latitude": latitude or 0.0,
                "longitude": longitude or 0.0,
                "price": float(price) if price is not None else 0.0,
                "rating": float(rating),
                "status": "active",
                "service": services,
                "distance": float(distance),
                "rooms": rooms,
            }

            sanitized.append(hotel_entry)

    return {"hotels": sanitized}


def main() -> None:
    data = sanitize_hotels_from_csv(CSV_PATH)
    output_file = CSV_PATH.with_suffix(".json")
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Output saved to: {output_file}")


if __name__ == "__main__":
    main()
