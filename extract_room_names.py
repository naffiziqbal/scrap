#!/usr/bin/env python3
"""
Script to extract all room names from merged_hotels.json
"""

import json
from collections import Counter

def extract_room_names(json_file):
    """
    Extract all room names from the hotels JSON file.
    
    Args:
        json_file: Path to the JSON file
    """
    # Read the JSON file
    print(f"Reading {json_file}...")
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extract all room names
    room_names = []
    hotels_with_rooms = 0
    hotels_without_rooms = 0
    
    for hotel in data.get('hotels', []):
        rooms = hotel.get('rooms', [])
        if rooms:
            hotels_with_rooms += 1
            for room in rooms:
                room_name = room.get('name')
                if room_name:
                    room_names.append(room_name)
        else:
            hotels_without_rooms += 1
    
    # Count occurrences
    room_name_counts = Counter(room_names)
    
    # Print statistics
    print(f"\n{'='*60}")
    print(f"Statistics:")
    print(f"  - Total hotels: {len(data.get('hotels', []))}")
    print(f"  - Hotels with rooms: {hotels_with_rooms}")
    print(f"  - Hotels without rooms: {hotels_without_rooms}")
    print(f"  - Total room entries: {len(room_names)}")
    print(f"  - Unique room names: {len(room_name_counts)}")
    print(f"{'='*60}\n")
    
    # Print all unique room names (sorted)
    print("All unique room names (sorted alphabetically):")
    print(f"{'='*60}")
    for room_name in sorted(set(room_names)):
        count = room_name_counts[room_name]
        print(f"  - {room_name} ({count} occurrence{'s' if count > 1 else ''})")
    
    # Save to file
    output_file = 'room_names.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("All Room Names from merged_hotels.json\n")
        f.write("="*60 + "\n\n")
        f.write(f"Total room entries: {len(room_names)}\n")
        f.write(f"Unique room names: {len(room_name_counts)}\n\n")
        f.write("Unique room names (sorted alphabetically):\n")
        f.write("-"*60 + "\n")
        for room_name in sorted(set(room_names)):
            count = room_name_counts[room_name]
            f.write(f"{room_name} ({count} occurrence{'s' if count > 1 else ''})\n")
        f.write("\n" + "="*60 + "\n")
        f.write("All room names (in order of appearance):\n")
        f.write("-"*60 + "\n")
        for room_name in room_names:
            f.write(f"{room_name}\n")
    
    print(f"\n{'='*60}")
    print(f"Room names have been saved to: {output_file}")
    print(f"{'='*60}")
    
    return room_names, room_name_counts

if __name__ == '__main__':
    extract_room_names('merged_hotels.json')

