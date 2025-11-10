#!/usr/bin/env python3
"""
Script to check if rooms in Telavi hotels have images
"""

from bs4 import BeautifulSoup
import os
import re
import json

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
        match = re.search(r'^(.+?),\s*Telavi', title.text)
        if match:
            return match.group(1).strip()
    return "Unknown Hotel"

def extract_rooms_with_images(soup):
    """Extract room information including images from HTML"""
    rooms = []
    
    # Find all room rows in the table
    room_rows = soup.find_all('tr', {'data-block-id': True})
    
    # Track rooms we've seen to avoid duplicates
    seen_room_ids = set()
    
    for row in room_rows:
        room_data = {}
        
        # Get room ID
        room_link = row.select_one('.hprt-roomtype-link')
        if room_link:
            room_id = room_link.get('data-room-id')
            if room_id and room_id in seen_room_ids:
                continue  # Skip duplicates
            if room_id:
                seen_room_ids.add(room_id)
                room_data['room_id'] = room_id
            
            # Get room name
            room_name_span = room_link.find('span', class_='hprt-roomtype-icon-link')
            if room_name_span:
                room_name = room_name_span.get_text(strip=True)
                if room_name:
                    room_data['name'] = room_name
        
        # Look for room images
        room_images = []
        
        # Method 1: Look for images in the row
        img_tags = row.find_all('img')
        for img in img_tags:
            img_src = img.get('src') or img.get('data-src') or img.get('data-lazy')
            if img_src and 'hotel' in img_src and img_src not in room_images:
                room_images.append(img_src)
        
        # Method 2: Look in structured data or room lightbox containers
        if room_data.get('room_id'):
            # Find any script tags or data attributes that might contain image URLs
            lightbox = soup.find('div', {'data-room-id': room_data['room_id']})
            if lightbox:
                # Look for any image references in this lightbox
                for img in lightbox.find_all('img'):
                    img_src = img.get('src') or img.get('data-src') or img.get('data-lazy')
                    if img_src and 'hotel' in img_src and img_src not in room_images:
                        room_images.append(img_src)
        
        if room_data.get('name'):
            room_data['images'] = room_images
            room_data['has_images'] = len(room_images) > 0
            room_data['image_count'] = len(room_images)
            rooms.append(room_data)
    
    return rooms

def extract_structured_room_data(page_source):
    """Try to extract room data from JSON-LD structured data"""
    soup = BeautifulSoup(page_source, 'html.parser')
    
    for script in soup.find_all('script', type='application/ld+json'):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            # Check if this has room information
            if isinstance(data, dict):
                # Some hotels might have accommodations listed
                if 'hasRoomType' in data:
                    return data.get('hasRoomType', [])
        except json.JSONDecodeError:
            continue
    
    return []

def main():
    html_dir = 'html_cache'
    all_results = []
    
    total_rooms = 0
    total_rooms_with_images = 0
    total_rooms_without_images = 0
    
    print("Checking room images in Telavi hotels...")
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
            rooms = extract_rooms_with_images(soup)
            
            rooms_with_images = sum(1 for r in rooms if r.get('has_images'))
            rooms_without_images = len(rooms) - rooms_with_images
            
            result = {
                'file': hotel_file,
                'name': hotel_name,
                'total_rooms': len(rooms),
                'rooms_with_images': rooms_with_images,
                'rooms_without_images': rooms_without_images,
                'rooms': rooms
            }
            all_results.append(result)
            
            total_rooms += len(rooms)
            total_rooms_with_images += rooms_with_images
            total_rooms_without_images += rooms_without_images
            
            # Print results
            print(f"\n{hotel_name}")
            print(f"  File: {hotel_file}")
            print(f"  Total rooms: {len(rooms)}")
            print(f"  Rooms WITH images: {rooms_with_images}")
            print(f"  Rooms WITHOUT images: {rooms_without_images}")
            
            if rooms:
                for room in rooms:
                    status = "✓" if room.get('has_images') else "✗"
                    img_count = room.get('image_count', 0)
                    print(f"    {status} {room.get('name', 'Unknown')} - {img_count} image(s)")
            
            print("-"*80)
            
        except Exception as e:
            print(f"Error processing {hotel_file}: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "="*80)
    print(f"SUMMARY")
    print("="*80)
    print(f"Total hotels processed: {len(all_results)}")
    print(f"Total rooms: {total_rooms}")
    print(f"Rooms WITH images: {total_rooms_with_images} ({total_rooms_with_images/total_rooms*100:.1f}%)")
    print(f"Rooms WITHOUT images: {total_rooms_without_images} ({total_rooms_without_images/total_rooms*100:.1f}%)")
    
    # Hotels with rooms missing images
    print("\n" + "="*80)
    print("Hotels with rooms MISSING images:")
    print("="*80)
    hotels_with_issues = [r for r in all_results if r['rooms_without_images'] > 0]
    if hotels_with_issues:
        for result in hotels_with_issues:
            print(f"  {result['name']}: {result['rooms_without_images']}/{result['total_rooms']} rooms missing images")
    else:
        print("  ✓ All rooms in all hotels have images!")
    
    # Save detailed report
    output_file = 'telavi_room_images_report.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    output_txt = 'telavi_room_images_report.txt'
    with open(output_txt, 'w', encoding='utf-8') as f:
        f.write("TELAVI HOTELS - ROOM IMAGE CHECK REPORT\n")
        f.write("="*80 + "\n\n")
        
        for result in all_results:
            f.write(f"{result['name']}\n")
            f.write(f"  File: {result['file']}\n")
            f.write(f"  Total rooms: {result['total_rooms']}\n")
            f.write(f"  Rooms WITH images: {result['rooms_with_images']}\n")
            f.write(f"  Rooms WITHOUT images: {result['rooms_without_images']}\n")
            f.write(f"  Rooms:\n")
            for room in result['rooms']:
                status = "✓" if room.get('has_images') else "✗"
                img_count = room.get('image_count', 0)
                f.write(f"    {status} {room.get('name', 'Unknown')} - {img_count} image(s)\n")
                if room.get('images'):
                    for img_url in room['images'][:2]:  # Show first 2 image URLs
                        f.write(f"        {img_url}\n")
            f.write("\n" + "-"*80 + "\n\n")
        
        f.write("\n" + "="*80 + "\n")
        f.write(f"SUMMARY\n")
        f.write("="*80 + "\n")
        f.write(f"Total hotels: {len(all_results)}\n")
        f.write(f"Total rooms: {total_rooms}\n")
        f.write(f"Rooms WITH images: {total_rooms_with_images} ({total_rooms_with_images/total_rooms*100:.1f}%)\n")
        f.write(f"Rooms WITHOUT images: {total_rooms_without_images} ({total_rooms_without_images/total_rooms*100:.1f}%)\n")
    
    print(f"\n" + "="*80)
    print(f"Detailed report saved to:")
    print(f"  - {output_file}")
    print(f"  - {output_txt}")
    print("="*80)

if __name__ == '__main__':
    main()

