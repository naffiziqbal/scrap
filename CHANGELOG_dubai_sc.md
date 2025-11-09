# Changelog: dubai_sc.py Updates from csv_ex.py

**Date:** November 9, 2025  
**Updated File:** `dubai_sc.py`  
**Source File:** `csv_ex.py`

---

## Summary

Updated `dubai_sc.py` to include room-specific image gallery extraction functionality and performance improvements from `csv_ex.py`. These changes enable scraping of room-specific images from modals and improve scraping efficiency.

---

## Detailed Changes

### 1. **Import Additions** (Lines 10-11)
- **Added:** `Keys` and `ActionChains` from selenium.webdriver.common
- **Reason:** Required for modal interaction (opening room galleries and closing with ESC key)

```python
# NEW IMPORTS
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
```

---

### 2. **New Function: `extract_room_gallery_images()`** (Lines 313-454)
- **Type:** New function (142 lines)
- **Purpose:** Extracts room-specific gallery images from a modal that opens when clicking the room name link
- **Key Features:**
  - Scrolls to room link and clicks it to open modal
  - Waits for room photos modal to appear using WebDriverWait
  - Extracts images from multiple sources:
    - CSS background-image in carousel divs
    - Thumbnail images (upgrades from `/square60/` to `/max1024x768/`)
    - Other img tags with validation
  - Handles errors gracefully with fallbacks
  - Closes modal with ESC key in finally block
  - Deduplicates images using a set

**Signature:**
```python
def extract_room_gallery_images(driver: webdriver.Chrome, room_link_element) -> List[str]
```

---

### 3. **Updated Function: `extract_room_options()`** (Lines 457-645)
- **Type:** Modified function
- **Changes:**
  1. **New parameter:** `driver: Optional[webdriver.Chrome] = None`
  2. **Added:** Room gallery image extraction logic (lines 577-633)
  3. **Added:** Room filtering to only include rooms with both name AND gallery images (lines 637-643)
  
**New Logic:**
- Iterates through room rows with enumeration for debugging
- For each room with a name element and driver available:
  - Finds the room name link element using Selenium
  - Tries by room type ID first, then by block_id as fallback
  - Calls `extract_room_gallery_images()` to get images
  - Adds gallery to room data if images found
- **Filtering:** Only adds room to results if it has both:
  - A name
  - Gallery images (non-empty)

**Impact:** This means rooms without gallery images are now excluded from the output.

---

### 4. **New Function: `compare_hotel_vs_room_images()`** (Lines 1208-1248)
- **Type:** New debugging/testing function (41 lines)
- **Purpose:** Prints comparison of hotel gallery images vs room images
- **Features:**
  - Displays hotel title and gallery image count
  - Shows first 5 images from hotel gallery
  - Iterates through rooms showing their galleries
  - Checks for overlap between hotel and room images
  - Provides visual warnings if overlap detected
  
**Note:** This is a utility function for testing/debugging, not called in main execution flow.

---

### 5. **Updated Function: `extract_hotel_details()`** (Lines 882-890)
- **Type:** Modified function
- **Change:** Replaced fixed `time.sleep(5)` with WebDriverWait
- **New Logic:**
  - Uses WebDriverWait to wait for key elements (title, room table, or description) with 10s timeout
  - Falls back to shorter sleep (1s) if timeout occurs
  - More efficient and reliable page loading

**Before:**
```python
driver.get(hotel_url)
time.sleep(5)
```

**After:**
```python
driver.get(hotel_url)
# Wait for page to load using key elements instead of fixed sleep
try:
    WebDriverWait(driver, 10).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "[data-testid='title'], tbody tr[data-block-id], div.hp-description")
    )
except TimeoutException:
    time.sleep(1)
```

- **Updated:** Call to `extract_room_options()` now passes `driver` parameter (line 1189)
  ```python
  rooms = extract_room_options(soup, driver=driver)
  ```

---

### 6. **Updated Function: `main()`** (Lines 1337-1346)
- **Type:** Modified function
- **Changes:**

#### a. Reduced Sleep Time (Line 1338)
- **Before:** `time.sleep(1)` between hotel scrapes
- **After:** `time.sleep(0.3)` with explanatory comment
- **Reason:** Page loads handled by WebDriverWait, so shorter sleep sufficient

#### b. JSON Output Addition (Lines 1342-1346)
- **New:** Saves data as JSON in addition to CSV
- **File naming:** Uses same timestamp as CSV (e.g., `uae_hotels_20251109_003828.json`)
- **Format:** Pretty-printed with indent=2, non-ASCII characters preserved

**New Code:**
```python
# Also save as JSON for easier inspection
json_path = OUTPUT_PATH.with_suffix('.json')
with json_path.open("w", encoding="utf-8") as json_file:
    json.dump(hotel_data, json_file, ensure_ascii=False, indent=2)
print(f"Saved {len(hotel_data)} hotels to {json_path}")
```

---

## Performance Impact

### Improvements
1. **Faster scraping:** Reduced sleep from 1s to 0.3s per hotel (70% reduction)
2. **More reliable:** WebDriverWait ensures pages are loaded before scraping
3. **Smarter waiting:** Only waits as long as needed, not fixed 5 seconds

### Trade-offs
1. **Longer per-hotel time:** Room gallery extraction adds time per hotel (modal interactions)
2. **Fewer rooms per hotel:** Filtering excludes rooms without gallery images
3. **More complex:** Additional modal handling and error cases

---

## Data Quality Impact

### Enhanced
1. **Room images:** Each room now has its own gallery images (not just hotel-level images)
2. **Better filtering:** Only rooms with complete data (name + images) are included
3. **Deduplication:** Image URLs are deduplicated within each room gallery

### Changed
1. **Room count may decrease:** Rooms without clickable name links or gallery images are excluded
2. **More complete data:** Each included room has richer information

---

## Testing Utility Added

The new `compare_hotel_vs_room_images()` function provides:
- Visual comparison of hotel vs room galleries
- Overlap detection between hotel and room images
- First 5 images displayed for quick inspection
- Useful for debugging and validation

---

## Files Created During Run

For each execution, two files are now created:
1. **CSV file:** `uae_hotels_YYYYMMDD_HHMMSS.csv` (existing)
2. **JSON file:** `uae_hotels_YYYYMMDD_HHMMSS.json` (NEW)

Both files contain the same data in different formats.

---

## Compatibility Notes

- **Backward compatible:** All existing functionality preserved
- **New dependencies:** No new external dependencies (uses existing selenium imports)
- **API changes:** `extract_room_options()` signature changed but backward compatible (optional parameter)

---

## Migration Notes

If you have code that depends on the old behavior:

1. **Room count:** Expect fewer rooms per hotel (only those with galleries)
2. **Processing time:** Expect longer scraping times per hotel
3. **Data structure:** Rooms now include `gallery` field with list of image URLs

---

## Summary of Line Counts

- **Total lines changed:** ~200 lines
- **New code added:** ~190 lines
- **Modified existing code:** ~10 lines
- **New function:** `extract_room_gallery_images()` - 142 lines
- **New function:** `compare_hotel_vs_room_images()` - 41 lines
- **Modified:** `extract_room_options()`, `extract_hotel_details()`, `main()`

