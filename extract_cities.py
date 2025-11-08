#!/usr/bin/env python3
"""
Script to extract all cities from merged_hotels.json
"""

import json
from collections import Counter

def extract_cities(json_file):
    """
    Extract all cities from the hotels JSON file.
    
    Args:
        json_file: Path to the JSON file
    """
    # Read the JSON file
    print(f"Reading {json_file}...")
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extract all cities
    cities = []
    hotels_with_city = 0
    hotels_without_city = 0
    
    for hotel in data.get('hotels', []):
        city = hotel.get('city')
        if city:
            cities.append(city)
            hotels_with_city += 1
        else:
            hotels_without_city += 1
    
    # Count occurrences
    city_counts = Counter(cities)
    
    # Print statistics
    print(f"\n{'='*60}")
    print(f"Statistics:")
    print(f"  - Total hotels: {len(data.get('hotels', []))}")
    print(f"  - Hotels with city: {hotels_with_city}")
    print(f"  - Hotels without city: {hotels_without_city}")
    print(f"  - Unique cities: {len(city_counts)}")
    print(f"{'='*60}\n")
    
    # Print all unique cities (sorted) with counts
    print("All cities (sorted alphabetically with hotel counts):")
    print(f"{'='*60}")
    for city in sorted(city_counts.keys()):
        count = city_counts[city]
        print(f"  - {city}: {count} hotel{'s' if count > 1 else ''}")
    
    # Save to file
    output_file = 'cities.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("All Cities from merged_hotels.json\n")
        f.write("="*60 + "\n\n")
        f.write(f"Total hotels: {len(data.get('hotels', []))}\n")
        f.write(f"Hotels with city: {hotels_with_city}\n")
        f.write(f"Hotels without city: {hotels_without_city}\n")
        f.write(f"Unique cities: {len(city_counts)}\n\n")
        f.write("Cities (sorted alphabetically with hotel counts):\n")
        f.write("-"*60 + "\n")
        for city in sorted(city_counts.keys()):
            count = city_counts[city]
            f.write(f"{city}: {count} hotel{'s' if count > 1 else ''}\n")
        f.write("\n" + "="*60 + "\n")
        f.write("Cities sorted by hotel count (descending):\n")
        f.write("-"*60 + "\n")
        for city, count in city_counts.most_common():
            f.write(f"{city}: {count} hotel{'s' if count > 1 else ''}\n")
    
    print(f"\n{'='*60}")
    print(f"Cities have been saved to: {output_file}")
    print(f"{'='*60}")
    
    return cities, city_counts

if __name__ == '__main__':
    extract_cities('merged_hotels.json')

