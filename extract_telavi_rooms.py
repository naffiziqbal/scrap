#!/usr/bin/env python3
"""
Script to extract room information from Telavi hotel HTML files
"""

from bs4 import BeautifulSoup
import os
import re

# List of Telavi hotel HTML files
telavi_hotels = [
    "boutique-kviria-telavi.html",
    "chateau-mere.html",
    "chateau-mosmieri.html",
    "communal-telavi.html",
    "esquisse-boutique.html",
    "guest-house-telavi.html",
    "hestia-wine-and-view-telavi-kakheti-georgia.html",
    "holiday-inn-telavi.html",
    "mestvireni.html",
    "old-telavi-resort-amp-spa-zuzumbo.html",
    "qvevrebi.html",
    "schuchmann-wines-chateau-and-spa.html",
    "seventeen-rooms.html",
    "tita-homes.html"
]

def extract_hotel_name(soup):
    """Extract hotel name from HTML"""
    title = soup.find('title')
    if title:
        # Extract hotel name from title (format: "Hotel Name, Telavi (updated prices 2025)")
        match = re.search(r'^(.+?),\s*Telavi', title.text)
        if match:
            return match.group(1).strip()
    return "Unknown Hotel"

def extract_rooms(soup):
    """Extract room information from HTML"""
    rooms = []
    
    # Find all room type links
    room_links = soup.find_all('a', class_='hprt-roomtype-link')
    
    for link in room_links:
        # Get room name from the link text
        room_name_span = link.find('span', class_='hprt-roomtype-icon-link')
        if room_name_span:
            room_name = room_name_span.get_text(strip=True)
            if room_name and room_name not in rooms:
                rooms.append(room_name)
    
    return rooms

def main():
    html_dir = 'html_cache'
    all_results = []
    total_rooms = 0
    
    print("Extracting room information from Telavi hotels...")
    print("="*80)
    
    for hotel_file in telavi_hotels:
        file_path = os.path.join(html_dir, hotel_file)
        
        if not os.path.exists(file_path):
            print(f"Warning: {hotel_file} not found")
            continue
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract hotel name and rooms
            hotel_name = extract_hotel_name(soup)
            rooms = extract_rooms(soup)
            
            result = {
                'file': hotel_file,
                'name': hotel_name,
                'rooms': rooms,
                'room_count': len(rooms)
            }
            all_results.append(result)
            total_rooms += len(rooms)
            
            # Print results
            print(f"\n{hotel_name}")
            print(f"  File: {hotel_file}")
            print(f"  Number of rooms: {len(rooms)}")
            if rooms:
                print(f"  Rooms:")
                for i, room in enumerate(rooms, 1):
                    print(f"    {i}. {room}")
            else:
                print(f"  (No rooms found)")
            print("-"*80)
            
        except Exception as e:
            print(f"Error processing {hotel_file}: {e}")
    
    # Summary
    print("\n" + "="*80)
    print(f"SUMMARY")
    print("="*80)
    print(f"Total hotels processed: {len(all_results)}")
    print(f"Total rooms found: {total_rooms}")
    print(f"Average rooms per hotel: {total_rooms/len(all_results):.1f}")
    
    # Hotels with most rooms
    print("\n" + "="*80)
    print("Hotels sorted by number of rooms:")
    print("="*80)
    sorted_results = sorted(all_results, key=lambda x: x['room_count'], reverse=True)
    for result in sorted_results:
        print(f"{result['room_count']:2d} rooms - {result['name']}")
    
    # Save to file
    output_file = 'telavi_hotels_rooms.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("TELAVI HOTELS - ROOM INFORMATION\n")
        f.write("="*80 + "\n\n")
        
        for result in all_results:
            f.write(f"{result['name']}\n")
            f.write(f"  File: {result['file']}\n")
            f.write(f"  Number of rooms: {result['room_count']}\n")
            if result['rooms']:
                f.write(f"  Rooms:\n")
                for i, room in enumerate(result['rooms'], 1):
                    f.write(f"    {i}. {room}\n")
            else:
                f.write(f"  (No rooms found)\n")
            f.write("\n" + "-"*80 + "\n\n")
        
        f.write("\n" + "="*80 + "\n")
        f.write(f"SUMMARY\n")
        f.write("="*80 + "\n")
        f.write(f"Total hotels: {len(all_results)}\n")
        f.write(f"Total rooms: {total_rooms}\n")
        f.write(f"Average rooms per hotel: {total_rooms/len(all_results):.1f}\n\n")
        
        f.write("Hotels sorted by number of rooms:\n")
        f.write("-"*80 + "\n")
        for result in sorted_results:
            f.write(f"{result['room_count']:2d} rooms - {result['name']}\n")
    
    print(f"\n" + "="*80)
    print(f"Results saved to: {output_file}")
    print("="*80)

if __name__ == '__main__':
    main()

