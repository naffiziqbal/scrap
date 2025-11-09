from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
import random
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

BATUMI_CENTER = (41.650677, 41.636669)  # approx city center lat, lon (not used for UAE)

# Master list of dummy room services to sample from
DUMMY_ROOM_SERVICES: List[str] = [
    "Toilet",
    "Bathtub or shower",
    "Towels",
    "Linens",
    "Socket near the bed",
    "Tile/Marble floor",
    "TV",
    "Heating",
    "Carpeted",
    "Cable channels",
    "Wake-up service",
    "Upper floors accessible by elevator",
    "Upper floors accessible by stairs only",
    "Clothes rack",
    "Toilet paper",
    "Board games/puzzles",
    "Single-room AC for guest accommodation",
    "Inner courtyard view",
    "Air conditioning",
    "Attached bathroom",
    "Flat-screen TV",
    "Soundproof",
    "Free Wifi",
    "Private bathroom",
    "Hair dryer",
    "Free toiletries",
    "Shampoo",
    "Toiletries",
    "Bathroom",
]


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
        # Filter out "See all X facilities" entries
        return [
            str(s).strip() 
            for s in services 
            if isinstance(s, (str, int, float)) 
            and str(s).strip() 
            and not str(s).strip().lower().startswith("see all")
        ]
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

    # Track used images across all rooms to ensure no duplicates
    used_images: set[str] = set()

    for item in rooms_raw:
        if not isinstance(item, dict):
            continue
        room_name = item.get("name") if isinstance(item.get("name"), str) else None
        # Skip entries without a name field - these are pricing variants, not actual rooms
        if not room_name or not room_name.strip():
            continue
        
        description = item.get("description") if isinstance(item.get("description"), str) else None
        price_amount = _to_float(item.get("price_amount")) or _to_float(item.get("price"))

        # Extract highlights as services (max 6)
        highlights = item.get("highlights")
        room_services: List[str] = []
        if isinstance(highlights, list):
            # Filter out "See all X facilities" entries and other non-service items
            room_services = [
                str(h).strip() 
                for h in highlights 
                if isinstance(h, (str, int, float)) 
                and str(h).strip() 
                and not str(h).strip().lower().startswith("see all")
            ]
            # Limit to maximum 6 services
            room_services = room_services[:6]

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

        # Extract room images from the item (check both 'gallery' and 'images' fields)
        room_images_raw = item.get("gallery") or item.get("images")
        room_images: List[str] = []
        if isinstance(room_images_raw, list):
            # Clean and filter room images
            room_images = [
                str(img).strip()
                for img in room_images_raw
                if isinstance(img, (str, int, float)) and str(img).strip()
            ]
        
        # Filter out already used images and assign unique images to this room
        available_room_images = [img for img in room_images if img not in used_images]
        room_gallery: List[str] = []
        
        if available_room_images:
            # Use room images (limit to 6 for gallery)
            room_gallery = available_room_images[:6]
            # Mark these images as used
            used_images.update(room_gallery)
            room_image = room_gallery[0] if room_gallery else ""
        else:
            # Fall back to hotel gallery if room has no unique images
            # Get unused hotel gallery images
            available_hotel_images = [img for img in hotel_gallery if img not in used_images]
            if available_hotel_images:
                # Use up to 6 unused hotel images
                room_gallery = available_hotel_images[:6]
                used_images.update(room_gallery)
                room_image = room_gallery[0] if room_gallery else ""
            else:
                # No unique images available - leave empty rather than reusing
                # This ensures no image is reused twice as required
                room_image = ""
                room_gallery = []

        rooms.append(
            {
                "type": infer_type(room_name),
                "name": room_name,
                "image": room_image,
                "price": round(price_amount, 2) if price_amount is not None else 0.0,
                "quantity": int(quantity),
                "information": description or "",
                "gallery": room_gallery,
                "service": room_services,
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


def sanitize_hotels_from_csv(csv_path: Path, country: str = "Georgia") -> Dict[str, Any]:
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

            # Rooms data is in the column with empty name (between reviews_count and search_city)
            # Try "rooms" first, then empty string as fallback
            rooms_raw = _safe_json_loads(row.get("rooms") or row.get("") or "")
            rooms = _parse_rooms(rooms_raw, gallery)

            search_pricing_raw = _safe_json_loads(row.get("search_pricing") or "")
            price = _derive_price(search_pricing_raw, rooms)

            # Distance calculation (not used for UAE, set to 0)
            # For UAE, we don't calculate distance from a specific center
            distance_km = None

            # Fill derived fields
            category = _derive_category_from_title(title or description)
            image = _first_or_none(gallery) or ""
            # Use actual rating from CSV, fall back to derived rating if not available
            # Convert rating from 10-point scale to 5-point scale (divide by 2)
            csv_rating = _to_float(row.get("rating"))
            if csv_rating is not None:
                rating = csv_rating / 2.0
            else:
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
                "price": round(float(price), 2) if price is not None else 0.0,
                "rating": float(rating),
                "status": "active",
                "service": services,
                "distance": float(distance),
                "rooms": rooms,
            }

            sanitized.append(hotel_entry)

    return {"hotels": sanitized}


def add_room_services_to_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Add randomized services to each room in the data dictionary.

    The function updates each room dictionary by adding a "service" key containing
    a random subset of DUMMY_ROOM_SERVICES. Only adds services if the room doesn't
    already have services (e.g., from highlights in the CSV).
    """
    hotels = data.get("hotels")
    if not isinstance(hotels, list):
        return data

    for hotel in hotels:
        rooms = hotel.get("rooms")
        if not isinstance(rooms, list):
            continue
        for room in rooms:
            # Only add services if room doesn't already have them
            if "service" not in room or not room.get("service"):
                # Choose a random number of services per room
                count = random.randint(6, min(14, len(DUMMY_ROOM_SERVICES)))
                room_services = random.sample(DUMMY_ROOM_SERVICES, k=count)
                room["service"] = room_services

    return data


def add_room_services_to_json(json_path: Path) -> Dict[str, Any]:
    """Load existing sanitized hotels JSON and add randomized services to each room.

    The function updates each room dictionary by adding a "service" key containing
    a random subset of DUMMY_ROOM_SERVICES.
    """
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return add_room_services_to_data(data)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Sanitize hotel data from CSV files and convert to JSON format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert CSV to JSON (output will be input_file.json)
  python sanitize_hotels.py -i hotels.csv

  # Specify output file and country
  python sanitize_hotels.py -i hotels.csv -o output.json -c "UAE"

  # Enhance existing JSON file with room services
  python sanitize_hotels.py -j existing_hotels.json
        """,
    )
    
    # Input/output group
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "-i", "--input",
        type=Path,
        help="Input CSV file to sanitize",
    )
    input_group.add_argument(
        "-j", "--json",
        type=Path,
        help="Existing JSON file to enhance with room services",
    )
    
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output JSON file (defaults to input CSV filename with .json extension)",
    )
    
    parser.add_argument(
        "-c", "--country",
        type=str,
        default="Georgia",
        help="Country name for hotels (default: Georgia)",
    )
    
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    start_time = time.time()
    
    # If JSON file is provided, enhance it with room services
    if args.json:
        json_path = args.json
        if not json_path.exists():
            print(f"Error: JSON file not found: {json_path}", file=sys.stderr)
            sys.exit(1)
        
        print(f"Enhancing existing JSON with room services: {json_path}")
        data = add_room_services_to_json(json_path)
        json_start_time = time.time()
        
        output_path = args.output if args.output else json_path
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        json_write_time = time.time() - json_start_time
        total_time = time.time() - start_time
        print(f"Updated JSON saved to: {output_path}")
        print(f"\nTiming:")
        print(f"  JSON writing: {json_write_time:.3f} seconds")
        print(f"  Total time: {total_time:.3f} seconds")
        return
    
    # Process CSV file
    csv_path = args.input
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Converting CSV to JSON...")
    print(f"  Input: {csv_path}")
    print(f"  Country: {args.country}")
    
    data = sanitize_hotels_from_csv(csv_path, country=args.country)
    csv_processing_time = time.time() - start_time
    
    # Add room services to the data
    print("Adding room services...")
    services_start_time = time.time()
    data = add_room_services_to_data(data)
    services_time = time.time() - services_start_time
    
    # Determine output file path
    if args.output:
        output_file = args.output
    else:
        output_file = csv_path.with_suffix(".json")
    
    json_start_time = time.time()
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    json_write_time = time.time() - json_start_time
    
    total_time = time.time() - start_time
    
    print(f"Output saved to: {output_file}")
    print(f"\nTiming:")
    print(f"  CSV processing: {csv_processing_time:.3f} seconds")
    print(f"  Adding room services: {services_time:.3f} seconds")
    print(f"  JSON writing: {json_write_time:.3f} seconds")
    print(f"  Total time: {total_time:.3f} seconds")


if __name__ == "__main__":
    main()
