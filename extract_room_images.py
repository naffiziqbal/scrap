import json

# Read the JSON file
with open('georgia_hotels_20251108_220715.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Extract image and gallery from all rooms
rooms_data = []

for hotel in data.get('hotels', []):
    hotel_id = hotel.get('id')
    hotel_title = hotel.get('title')
    
    for room in hotel.get('rooms', []):
        room_info = {
            'hotel_id': hotel_id,
            'hotel_title': hotel_title,
            'room_type': room.get('type'),
            'room_name': room.get('name'),
            'image': room.get('image'),
            'gallery': room.get('gallery', [])
        }
        rooms_data.append(room_info)

# Print the results
print(f"Total rooms found: {len(rooms_data)}\n")
print("=" * 80)

for idx, room in enumerate(rooms_data, 1):
    print(f"\n[{idx}] Hotel: {room['hotel_title']}")
    print(f"    Room: {room['room_name']} ({room['room_type']})")
    print(f"    Image: {room['image']}")
    print(f"    Gallery ({len(room['gallery'])} images):")
    for i, gallery_url in enumerate(room['gallery'], 1):
        print(f"      {i}. {gallery_url}")
    print("-" * 80)

# Also save to a JSON file for easy reference
output_file = 'room_images_extracted.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(rooms_data, f, indent=2, ensure_ascii=False)

print(f"\n\nData also saved to: {output_file}")

