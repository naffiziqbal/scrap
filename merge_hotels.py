#!/usr/bin/env python3
"""
Script to merge two hotel JSON files into a single file.
"""

import json
from datetime import datetime
from pathlib import Path

def merge_hotel_files(file1_path, file2_path, output_path=None):
    """
    Merge two hotel JSON files into a single file.
    
    Args:
        file1_path: Path to the first JSON file
        file2_path: Path to the second JSON file
        output_path: Path for the output file (optional)
    """
    # Read first file
    print(f"Reading {file1_path}...")
    with open(file1_path, 'r', encoding='utf-8') as f:
        data1 = json.load(f)
    
    # Read second file
    print(f"Reading {file2_path}...")
    with open(file2_path, 'r', encoding='utf-8') as f:
        data2 = json.load(f)
    
    # Combine hotels arrays (handle both dict and list formats)
    if isinstance(data1, dict):
        hotels1 = data1.get('hotels', [])
    else:
        hotels1 = data1
    
    if isinstance(data2, dict):
        hotels2 = data2.get('hotels', [])
    else:
        hotels2 = data2
    
    merged_hotels = hotels1 + hotels2
    
    # Create merged data
    merged_data = {
        'hotels': merged_hotels
    }
    
    # Generate output filename if not provided
    if output_path is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = f'merged_hotels_{timestamp}.json'
    
    # Write merged data to file
    print(f"Writing merged data to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(merged_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nMerge complete!")
    print(f"  - Hotels from file 1: {len(hotels1)}")
    print(f"  - Hotels from file 2: {len(hotels2)}")
    print(f"  - Total hotels: {len(merged_hotels)}")
    print(f"  - Output file: {output_path}")
    
    return output_path

if __name__ == '__main__':
    # File paths
    georgia_file = 'georgia_hotels_20251109_125140.json'
    uae_file = 'uae_hotels_20251109_150018.json'
    output_file = 'merged_hotels.json'
    
    # Merge the files
    merge_hotel_files(georgia_file, uae_file, output_file)

