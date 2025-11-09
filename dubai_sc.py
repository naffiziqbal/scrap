"""
UAE Hotels Scraper with HTML Caching and Batch Processing

This script scrapes hotel data from Booking.com for UAE cities with the following features:

CACHING SYSTEM:
- HTML pages are cached to disk after first download
- Subsequent runs reuse cached HTML (much faster, no re-download)
- Cache directory: ./html_cache/
- Toggle caching with USE_CACHE constant (line ~112)

BENEFITS OF CACHING:
✓ 10-100x faster re-scraping (no network delays)
✓ Can fix extraction bugs without re-downloading
✓ Less likely to trigger anti-bot measures
✓ Inspect cached HTML files manually for debugging

NOTE ON ROOM IMAGES:
- Room-specific images require clicking room links (interactive)
- When using cached HTML, room image extraction is skipped
- To get room images: First run with USE_CACHE = False to download fresh HTML

BATCH PROCESSING:
- Saves progress every 10 hotels
- Creates single CSV file with all results
- JSON backup saved after each batch

USAGE:
1. First run: Downloads HTML and caches it
2. Subsequent runs: Uses cached HTML (super fast)
3. To refresh data: Set USE_CACHE = False or delete html_cache/ directory
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup, SoupStrainer, Tag
import csv
import json
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs, urlencode


def get_output_path() -> Path:
    """Generate output path with timestamp to preserve data from each run."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"uae_hotels_{timestamp}.csv")


def get_cache_dir() -> Path:
    """Get or create the HTML cache directory."""
    cache_dir = Path("html_cache")
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


def get_cached_html_path(url: str) -> Path:
    """Generate a safe filename for caching HTML based on URL."""
    # Extract hotel ID from URL (e.g., /hotel/ae/jumeirah-beach-hotel.html)
    parsed = urlparse(url)
    path_parts = parsed.path.strip('/').split('/')
    
    # Use hotel slug as filename (last part of path without .html)
    if path_parts:
        hotel_slug = path_parts[-1].replace('.html', '').replace('.htm', '')
        # Sanitize filename
        hotel_slug = re.sub(r'[^\w\-]', '_', hotel_slug)
    else:
        # Fallback to hash if can't parse
        hotel_slug = str(hash(url))
    
    cache_dir = get_cache_dir()
    return cache_dir / f"{hotel_slug}.html"


def save_html_to_cache(url: str, html_content: str) -> None:
    """Save HTML content to cache file."""
    cache_path = get_cached_html_path(url)
    try:
        cache_path.write_text(html_content, encoding='utf-8')
        print(f"  💾 Cached HTML to {cache_path.name}")
    except Exception as e:
        print(f"  ⚠️  Failed to cache HTML: {e}")


def load_html_from_cache(url: str) -> Optional[str]:
    """Load HTML content from cache if available."""
    cache_path = get_cached_html_path(url)
    if cache_path.exists():
        try:
            return cache_path.read_text(encoding='utf-8')
        except Exception:
            return None
    return None


def get_cache_stats() -> Dict[str, object]:
    """Get statistics about the HTML cache."""
    cache_dir = get_cache_dir()
    html_files = list(cache_dir.glob("*.html"))
    
    if not html_files:
        return {"cached_files": 0, "total_size_mb": 0}
    
    total_size = sum(f.stat().st_size for f in html_files if f.exists())
    total_size_mb = total_size / (1024 * 1024)
    
    return {
        "cached_files": len(html_files),
        "total_size_mb": round(total_size_mb, 2),
        "cache_dir": str(cache_dir)
    }


def clear_cache() -> None:
    """Clear all cached HTML files."""
    cache_dir = get_cache_dir()
    deleted = 0
    for html_file in cache_dir.glob("*.html"):
        try:
            html_file.unlink()
            deleted += 1
        except Exception:
            pass
    print(f"🗑️  Cleared {deleted} cached HTML files")


OUTPUT_PATH = get_output_path()
MAX_HOTELS = 100
SEARCH_RESULTS_PAGE_SIZE = 25
USE_CACHE = True  # Set to False to always fetch fresh data

BASE_SEARCH_URL = "https://www.booking.com/searchresults.html"
DEFAULT_SEARCH_QUERY = {
    "aid": "304142",
    "label": "gen173nr-10CAEoggI46AdIM1gEaBSIAQGYATO4AQfIAQzYAQPoAQH4AQGIAgGoAgG4AoLdtsgGwAIB0gIkNWY1MDE3MmYtODIxZS00ZDVkLWEzZjEtM2ZmYmU0NTQ5Y2Zj2AIB4AIB",
    "lang": "en-us",
    "sb": "1",
    "src_elem": "sb",
    "src": "country",
    "ss": "United Arab Emirates (UAE)",
    "ssne": "United Arab Emirates (UAE)",
    "ssne_untouched": "United Arab Emirates (UAE)",
    "efdco": "1",
    "dest_id": "221",
    "dest_type": "country",
    "checkin": "2025-11-12",
    "checkout": "2025-11-15",
    "group_adults": "2",
    "group_children": "0",
    "no_rooms": "1",
    "sb_travel_purpose": "leisure",
    "sb_lp": "1",
    "rows": str(SEARCH_RESULTS_PAGE_SIZE),
    "selected_currency": "USD",
}

TITLE_LINK_SELECTOR = "a[data-testid='titleLink'],a[data-testid='title-link']"

# Target cities to extract. Each city should have at least 10 entries.
CITIES: List[str] = [
    "Abu Dhabi",
    "Ajman",
    "Al Ain",
    "Dubai",
    "Fujairah",
    "Ras al Khaimah",
    "Sharjah",
    "Umm Al Quwain"
]


def set_currency_preference(driver: webdriver.Chrome, currency: str = "USD") -> None:
    """Set currency preference by visiting Booking.com with currency parameter and setting cookies."""
    # First, visit the main page to establish domain context (required before setting cookies)
    driver.get("https://www.booking.com")
    time.sleep(1)
    
    # Set currency cookies
    try:
        driver.add_cookie({
            "name": "currency",
            "value": currency,
            "domain": ".booking.com",
            "path": "/",
        })
    except Exception:
        pass  # Cookie might already exist
    
    try:
        driver.add_cookie({
            "name": "b_selected_currency",
            "value": currency,
            "domain": ".booking.com",
            "path": "/",
        })
    except Exception:
        pass  # Cookie might already exist
    
    # Now visit a page with currency parameter to ensure it's applied
    currency_url = f"https://www.booking.com/index.html?selected_currency={currency}"
    driver.get(currency_url)
    time.sleep(2)


def build_driver(headless: bool = True) -> webdriver.Chrome:
    """Create a Chrome WebDriver instance."""

    user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(f"--user-agent={user_agent}")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_cdp_cmd(
        "Network.setUserAgentOverride",
        {"userAgent": user_agent},
    )
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        },
    )
    return driver


def safe_select_text(
    root: BeautifulSoup | Tag,
    selector: str,
    context: BeautifulSoup | Tag | None = None,
) -> Optional[str]:
    """Return stripped text for a CSS selector or None if not found."""

    base = context or root
    element = base.select_one(selector)
    if not element:
        return None
    text = element.get_text(strip=True)
    return text or None


def _normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(value.replace("\xa0", " ").split())
    return cleaned or None


def _unique_non_empty(items: List[Optional[str]]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for item in items:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


PRICE_COMPONENT_PATTERN = re.compile(r"(?P<currency>[^\d\s]+)\s*(?P<amount>[\d.,]+)")


def _to_float(amount_text: str) -> Optional[float]:
    cleaned = amount_text.replace("\xa0", "").strip()
    if not cleaned:
        return None

    cleaned = cleaned.replace(" ", "")

    last_comma = cleaned.rfind(",")
    last_dot = cleaned.rfind(".")

    decimal_sep: Optional[str] = None
    thousands_sep: Optional[str] = None

    if last_comma != -1 and last_dot != -1:
        if last_comma > last_dot:
            decimal_sep = ","
            thousands_sep = "."
        else:
            decimal_sep = "."
            thousands_sep = ","
    elif last_comma != -1:
        fractional = cleaned[last_comma + 1 :]
        if fractional.isdigit() and 0 < len(fractional) <= 2:
            decimal_sep = ","
        else:
            thousands_sep = ","
    elif last_dot != -1:
        fractional = cleaned[last_dot + 1 :]
        if fractional.isdigit() and 0 < len(fractional) <= 2:
            decimal_sep = "."
        else:
            thousands_sep = "."

    if thousands_sep:
        cleaned = cleaned.replace(thousands_sep, "")

    if decimal_sep and decimal_sep != ".":
        cleaned = cleaned.replace(decimal_sep, ".")
    elif decimal_sep is None:
        cleaned = cleaned.replace(",", "").replace(".", "")

    try:
        return float(cleaned)
    except ValueError:
        return None


def _split_price_components(text: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[float]]:
    if not text:
        return None, None, None

    cleaned = text.replace("\xa0", " ").strip()
    match = PRICE_COMPONENT_PATTERN.search(cleaned)
    if not match:
        return None, cleaned or None, None

    currency = match.group("currency").strip() or None
    amount_text = match.group("amount").strip() or None
    amount_value = _to_float(amount_text) if amount_text else None
    return currency, amount_text, amount_value


def extract_price_info(soup: BeautifulSoup) -> Dict[str, object]:
    price_info: Dict[str, object] = {}

    container = soup.select_one("[data-testid='availability-rate-information']")
    breakdown_text: Optional[str] = None

    if container:
        stay_summary = safe_select_text(container, "[data-testid='price-for-x-nights']")
        if stay_summary:
            price_info["stay_summary"] = stay_summary

        taxes = safe_select_text(container, "[data-testid='taxes-and-charges']")
        if taxes:
            price_info["taxes_and_charges"] = taxes

        current_display = safe_select_text(container, "[data-testid='price-and-discounted-price']")
        if current_display:
            currency, amount_text, amount_value = _split_price_components(current_display)
            price_info["current_price_display"] = current_display
            if currency:
                price_info["current_price_currency"] = currency
            if amount_text is not None:
                price_info["current_price_amount_text"] = amount_text
            if amount_value is not None:
                price_info["current_price_amount"] = amount_value

        breakdown_text = safe_select_text(container, "div.bc946a29db")
        if not breakdown_text:
            for candidate in container.select("div"):
                candidate_text = candidate.get_text(" ", strip=True)
                if not candidate_text:
                    continue
                lowered = candidate_text.lower()
                if "original price" in lowered or "current price" in lowered:
                    breakdown_text = candidate_text
                    break

        if breakdown_text:
            price_info["price_breakdown_text"] = breakdown_text
            original_match = re.search(
                r"Original price\s+(?P<value>[^.]+)",
                breakdown_text,
                flags=re.IGNORECASE,
            )
            if original_match:
                original_display = original_match.group("value").strip().rstrip(".")
                currency, amount_text, amount_value = _split_price_components(original_display)
                price_info["original_price_display"] = original_display
                if currency and "original_price_currency" not in price_info:
                    price_info["original_price_currency"] = currency
                if amount_text and "original_price_amount_text" not in price_info:
                    price_info["original_price_amount_text"] = amount_text
                if amount_value is not None and "original_price_amount" not in price_info:
                    price_info["original_price_amount"] = amount_value

            current_match = re.search(
                r"Current price\s+(?P<value>[^.]+)",
                breakdown_text,
                flags=re.IGNORECASE,
            )
            if current_match and "current_price_display" not in price_info:
                current_display_from_breakdown = current_match.group("value").strip().rstrip(".")
                currency, amount_text, amount_value = _split_price_components(current_display_from_breakdown)
                price_info["current_price_display"] = current_display_from_breakdown
                if currency:
                    price_info["current_price_currency"] = currency
                if amount_text:
                    price_info["current_price_amount_text"] = amount_text
                if amount_value is not None:
                    price_info["current_price_amount"] = amount_value

    return {key: value for key, value in price_info.items() if value is not None}


def extract_room_gallery_images(driver: webdriver.Chrome, room_link_element) -> List[str]:
    """Extract room-specific gallery images from a modal that opens when clicking the room name link.
    
    Args:
        driver: Chrome WebDriver instance
        room_link_element: The room name link element (a.hprt-roomtype-link)
        
    Returns:
        List of image URLs for the room gallery
    """
    room_images: List[str] = []
    seen_urls: set[str] = set()
    
    try:
        # Scroll to the room link to ensure it's visible
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", room_link_element)
        time.sleep(0.3)
        
        # Click the room name link to open the modal
        try:
            room_link_element.click()
        except Exception:
            # Fallback to JavaScript click
            try:
                driver.execute_script("arguments[0].click();", room_link_element)
            except Exception:
                return room_images
        
        # Wait for the photo section to appear
        try:
            room_photos_container = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='roomPagePhotos']"))
            )
            time.sleep(0.8)  # Give modal content time to render
        except TimeoutException:
            # Try to close modal and return
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                time.sleep(0.2)
            except Exception:
                pass
            return room_images
        
        # Get the modal HTML and parse with BeautifulSoup
        try:
            modal_html = driver.find_element(By.CSS_SELECTOR, "[data-testid='roomPagePhotos']").get_attribute("outerHTML")
            modal_soup = BeautifulSoup(modal_html, "html.parser")
        except Exception:
            # Fallback: get page source and find the modal
            page_source = driver.page_source
            modal_soup = BeautifulSoup(page_source, "html.parser")
            room_photos_container_soup = modal_soup.select_one("[data-testid='roomPagePhotos']")
            if not room_photos_container_soup:
                try:
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                    time.sleep(0.2)
                except Exception:
                    pass
                return room_images
            modal_soup = room_photos_container_soup
        
        # Extract images from CSS background-image in carousel divs
        # Look for divs with style attribute containing background-image
        carousel_divs = modal_soup.select("div[style*='background-image']")
        for div in carousel_divs:
            style = div.get("style", "")
            # Extract URL from: background-image: url("https://...");
            url_match = re.search(r'url\(["\']?(https://[^"\']+)["\']?\)', style)
            if url_match:
                img_url = url_match.group(1)
                # Decode HTML entities
                img_url = img_url.replace("&quot;", "").replace("&amp;", "&")
                if img_url and img_url not in seen_urls:
                    room_images.append(img_url)
                    seen_urls.add(img_url)
        
        # Extract thumbnail images and upgrade to full size
        # Thumbnails are typically in /square60/ and can be upgraded to /max1024x768/
        thumbnail_imgs = modal_soup.select("img[src*='/square60/']")
        for img in thumbnail_imgs:
            thumb_url = img.get("src") or img.get("data-src") or img.get("data-lazy")
            if thumb_url:
                # Convert thumbnail URL to full-size
                # /square60/ -> /max1024x768/
                full_url = thumb_url.replace("/square60/", "/max1024x768/")
                # Also handle other thumbnail sizes
                full_url = full_url.replace("/square200/", "/max1024x768/")
                full_url = full_url.replace("/square300/", "/max1024x768/")
                full_url = full_url.replace("/max300/", "/max1024x768/")
                
                # Clean up URL
                full_url = full_url.replace("&amp;", "&")
                if full_url.startswith("//"):
                    full_url = "https:" + full_url
                elif full_url.startswith("/"):
                    full_url = "https://www.booking.com" + full_url
                
                if full_url and full_url not in seen_urls and full_url.startswith("http"):
                    room_images.append(full_url)
                    seen_urls.add(full_url)
        
        # Fallback: extract from other img tags
        other_imgs = modal_soup.select("img[src]")
        for img in other_imgs:
            img_url = img.get("src") or img.get("data-src") or img.get("data-lazy")
            if img_url:
                # Skip if already processed as thumbnail
                if "/square60/" in img_url or "/square200/" in img_url or "/square300/" in img_url:
                    continue
                
                # Clean up URL
                img_url = img_url.replace("&amp;", "&")
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                elif img_url.startswith("/"):
                    img_url = "https://www.booking.com" + img_url
                
                # Validate it's actually an image URL
                if img_url and img_url not in seen_urls and img_url.startswith("http"):
                    if (
                        "/images/" in img_url.lower() or 
                        "/image/" in img_url.lower() or
                        any(ext in img_url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]) or
                        "bstatic.com" in img_url.lower() or
                        "booking.com" in img_url.lower()
                    ):
                        room_images.append(img_url)
                        seen_urls.add(img_url)
        
    except Exception as e:
        # Silent failure - return empty list if extraction fails
        pass
    
    finally:
        # Close the modal with ESC key
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.3)
        except Exception:
            pass
    
    return room_images


def extract_room_options(soup: BeautifulSoup, driver: Optional[webdriver.Chrome] = None) -> List[Dict[str, object]]:
    rooms: List[Dict[str, object]] = []
    room_rows = soup.select("tbody tr[data-block-id]")

    for row_idx, row in enumerate(room_rows):
        room_data: Dict[str, object] = {}

        block_id = row.get("data-block-id")
        if block_id:
            room_data["block_id"] = block_id

        rounded_price = row.get("data-hotel-rounded-price")
        if rounded_price:
            try:
                room_data["rounded_price"] = int(rounded_price)
            except ValueError:
                pass

        name_element = row.select_one(".hprt-roomtype-link .hprt-roomtype-icon-link") or row.select_one(
            ".hprt-roomtype-link"
        )
        room_name = _normalize_text(name_element.get_text(" ", strip=True)) if name_element else None
        if room_name:
            room_data["name"] = room_name
        if name_element and name_element.has_attr("id"):
            room_data["room_type_id"] = name_element["id"]

        short_desc = _normalize_text(safe_select_text(row, "p.short-room-desc"))
        if short_desc:
            room_data["description"] = short_desc

        occupancy_text = _normalize_text(safe_select_text(row, ".hprt-table-cell-occupancy .bui-u-sr-only"))
        if occupancy_text:
            room_data["max_occupancy_text"] = occupancy_text

        occupancy_icons = len(row.select(".hprt-table-cell-occupancy .bicon-occupancy"))
        if occupancy_icons:
            room_data["max_occupancy"] = occupancy_icons

        bed_texts = _unique_non_empty(
            [
                _normalize_text(element.get_text(" ", strip=True))
                for element in row.select(
                    ".hprt-roomtype-bed li, .appartment-bed-types-wrapper li, .room-config li"
                )
            ]
        )
        if bed_texts:
            room_data["bed_configuration"] = bed_texts

        highlight_badges = _unique_non_empty(
            [
                _normalize_text(badge.get_text(" ", strip=True))
                for badge in row.select(".hprt-facilities-block .hprt-facilities-facility")
            ]
        )
        if highlight_badges:
            room_data["highlights"] = highlight_badges

        other_facilities = _unique_non_empty(
            [
                _normalize_text(badge.get_text(" ", strip=True))
                for badge in row.select(".hprt-facilities-others .hprt-facilities-facility")
            ]
        )
        if other_facilities:
            room_data["included_facilities"] = other_facilities

        policy_items = _unique_non_empty(
            [
                _normalize_text(item.get_text(" ", strip=True))
                for item in row.select(".hprt-conditions-bui li")
            ]
        )
        if policy_items:
            room_data["policies"] = policy_items

        partner_note = _normalize_text(safe_select_text(row, ".tpi-options--provided-by"))
        if partner_note:
            room_data["partner_note"] = partner_note

        price_display = _normalize_text(safe_select_text(row, ".bui-price-display__value"))
        if price_display:
            room_data["price_display"] = price_display
            currency, amount_text, amount_value = _split_price_components(price_display)
            if currency:
                room_data["price_currency"] = currency
            if amount_text is not None:
                room_data["price_amount_text"] = amount_text
            if amount_value is not None:
                room_data["price_amount"] = amount_value

        price_note = _normalize_text(safe_select_text(row, ".prd-taxes-and-fees-under-price"))
        if price_note:
            room_data["price_note"] = price_note

        availability_select = row.select_one("select.hprt-nos-select")
        if availability_select:
            options: List[Dict[str, object]] = []
            for option in availability_select.find_all("option"):
                option_label = _normalize_text(option.get_text(" ", strip=True))
                option_value = option.get("value")
                if not option_label and option_value is None:
                    continue
                option_entry: Dict[str, object] = {}
                if option_value is not None:
                    option_entry["value"] = option_value
                if option_label:
                    option_entry["label"] = option_label
                if option_entry:
                    options.append(option_entry)
            if options:
                room_data["availability"] = options

        badges = _unique_non_empty(
            [_normalize_text(badge.get_text(" ", strip=True)) for badge in row.select(".bui-badge")]
        )
        if badges:
            room_data["badges"] = badges

        # Extract room gallery images if driver is available
        # Only extract for rooms that have a clickable name link (main room types, not "Unknown" rate packages)
        if driver is not None and name_element:
            try:
                room_name_for_debug = room_data.get("name", f"room {block_id}")
                
                # Find the room name link (a.hprt-roomtype-link) using Selenium
                # First try to find it by room type ID if available
                room_link_element = None
                
                if name_element.has_attr("id"):
                    try:
                        room_type_id = name_element["id"]
                        # Find the link element by finding the anchor within the room type container
                        room_type_elem = driver.find_element(By.ID, room_type_id)
                        # Look for the link within the room type element or its parent
                        try:
                            room_link_element = room_type_elem.find_element(By.CSS_SELECTOR, "a.hprt-roomtype-link")
                        except Exception:
                            # Try finding in parent container
                            try:
                                parent_container = room_type_elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'hprt-roomtype-block')][1]")
                                room_link_element = parent_container.find_element(By.CSS_SELECTOR, "a.hprt-roomtype-link")
                            except Exception:
                                pass
                    except Exception:
                        pass
                
                # Fallback: find by block_id using XPath
                if not room_link_element and block_id:
                    try:
                        room_link_elements = driver.find_elements(
                            By.XPATH,
                            f"//tr[@data-block-id='{block_id}']//a[contains(@class, 'hprt-roomtype-link')]"
                        )
                        if room_link_elements:
                            # Filter for visible and enabled links
                            for link in room_link_elements:
                                try:
                                    if link.is_displayed() and link.is_enabled():
                                        room_link_element = link
                                        break
                                except Exception:
                                    continue
                            # If no visible link found, use the first one
                            if not room_link_element and room_link_elements:
                                room_link_element = room_link_elements[0]
                    except Exception:
                        pass
                
                if room_link_element:
                    room_gallery = extract_room_gallery_images(driver, room_link_element)
                    if room_gallery:
                        room_data["gallery"] = room_gallery
            except Exception:
                # If image extraction fails, continue without images
                pass

        room_data = {key: value for key, value in room_data.items() if value not in (None, [], {})}
        
        # Only add room if it has both a name and gallery images
        room_name = room_data.get("name")
        room_gallery = room_data.get("gallery", [])
        
        if room_data and room_name and room_gallery:
            rooms.append(room_data)
        # Skip rooms without name or without gallery images

    return rooms


def parse_structured_data(page_source: str) -> Dict[str, object]:
    """Extract the first Hotel JSON-LD block from the page if available."""

    for script in BeautifulSoup(
        page_source,
        "html.parser",
        parse_only=SoupStrainer("script", type="application/ld+json"),
    ):
        if not script.string:
            continue
        try:
            parsed = json.loads(script.string)
        except json.JSONDecodeError:
            continue

        if isinstance(parsed, dict) and parsed.get("@type") == "Hotel":
            return parsed
        if isinstance(parsed, list):
            for entry in parsed:
                if isinstance(entry, dict) and entry.get("@type") == "Hotel":
                    return entry

    return {}


def build_search_url(offset: int = 0) -> str:
    params = DEFAULT_SEARCH_QUERY.copy()
    if offset:
        params["offset"] = str(offset)
    return f"{BASE_SEARCH_URL}?{urlencode(params)}"


def build_city_search_url(city: str, offset: int = 0) -> str:
    """Build a Booking.com search URL for a specific city in UAE.

    Note: Avoid using country-level dest_id/dest_type so that the query resolves
    specifically to the provided city.
    """
    params: Dict[str, str] = {
        "aid": DEFAULT_SEARCH_QUERY["aid"],
        "label": DEFAULT_SEARCH_QUERY["label"],
        "lang": DEFAULT_SEARCH_QUERY["lang"],
        "sb": DEFAULT_SEARCH_QUERY["sb"],
        "src_elem": DEFAULT_SEARCH_QUERY["src_elem"],
        "ss": f"{city}, United Arab Emirates (UAE)",
        "ssne": f"{city}",
        "ssne_untouched": f"{city}",
        "efdco": DEFAULT_SEARCH_QUERY["efdco"],
        "checkin": DEFAULT_SEARCH_QUERY["checkin"],
        "checkout": DEFAULT_SEARCH_QUERY["checkout"],
        "group_adults": DEFAULT_SEARCH_QUERY["group_adults"],
        "group_children": DEFAULT_SEARCH_QUERY["group_children"],
        "no_rooms": DEFAULT_SEARCH_QUERY["no_rooms"],
        "sb_travel_purpose": DEFAULT_SEARCH_QUERY["sb_travel_purpose"],
        "sb_lp": DEFAULT_SEARCH_QUERY["sb_lp"],
        "rows": DEFAULT_SEARCH_QUERY["rows"],
        "selected_currency": DEFAULT_SEARCH_QUERY["selected_currency"],
    }
    if offset:
        params["offset"] = str(offset)
    return f"{BASE_SEARCH_URL}?{urlencode(params)}"


def collect_hotel_links(
    driver: webdriver.Chrome,
    max_results: int = MAX_HOTELS,
) -> List[Dict[str, object]]:
    """Scroll through the search results and collect up to max_results hotel entries including price snippets."""

    driver.get(build_search_url(0))
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, TITLE_LINK_SELECTOR))
        )
    except TimeoutException:
        time.sleep(5)

    entries: List[Dict[str, object]] = []
    seen: set[str] = set()
    idle_rounds = 0

    def collect_from_elements(elements) -> int:
        added = 0
        for anchor in elements:
            href = anchor.get_attribute("href")
            if not href:
                continue
            clean = href.split("?")[0]
            absolute = urljoin("https://www.booking.com", clean)
            if absolute not in seen:
                seen.add(absolute)
                card_html: Optional[str] = None
                try:
                    card_element = anchor.find_element(
                        By.XPATH,
                        "./ancestor::div[@data-testid='property-card']",
                    )
                    card_html = card_element.get_attribute("outerHTML")
                except Exception:
                    card_html = None

                search_pricing: Dict[str, object] = {}
                if card_html:
                    card_soup = BeautifulSoup(card_html, "html.parser")
                    search_pricing = extract_price_info(card_soup)

                entries.append({"url": absolute, "search_pricing": search_pricing})
                added += 1
                if len(entries) >= max_results:
                    break
        return added

    while len(entries) < max_results and idle_rounds < 3:
        elements = driver.find_elements(By.CSS_SELECTOR, TITLE_LINK_SELECTOR)
        previous_total = len(elements)
        collect_from_elements(elements)
        if len(entries) >= max_results:
            break

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        try:
            load_more = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//button[.//span[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'load more results')]]",
                    )
                )
            )
            driver.execute_script("arguments[0].click();", load_more)
        except TimeoutException:
            pass

        try:
            WebDriverWait(driver, 10).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, TITLE_LINK_SELECTOR)) > previous_total
            )
            idle_rounds = 0
        except TimeoutException:
            idle_rounds += 1

    return entries[:max_results]


def collect_hotel_links_for_city(
    driver: webdriver.Chrome,
    city: str,
    max_results: int = 10,
) -> List[Dict[str, object]]:
    """Collect up to max_results hotel entries for a specific city."""

    driver.get(build_city_search_url(city, 0))
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, TITLE_LINK_SELECTOR))
        )
    except TimeoutException:
        time.sleep(5)

    entries: List[Dict[str, object]] = []
    seen: set[str] = set()
    idle_rounds = 0

    def collect_from_elements(elements) -> int:
        added = 0
        for anchor in elements:
            href = anchor.get_attribute("href")
            if not href:
                continue
            clean = href.split("?")[0]
            absolute = urljoin("https://www.booking.com", clean)
            if absolute not in seen:
                seen.add(absolute)
                card_html: Optional[str] = None
                try:
                    card_element = anchor.find_element(
                        By.XPATH,
                        "./ancestor::div[@data-testid='property-card']",
                    )
                    card_html = card_element.get_attribute("outerHTML")
                except Exception:
                    card_html = None

                search_pricing: Dict[str, object] = {}
                if card_html:
                    card_soup = BeautifulSoup(card_html, "html.parser")
                    search_pricing = extract_price_info(card_soup)

                entries.append({"url": absolute, "search_pricing": search_pricing, "search_city": city})
                added += 1
                if len(entries) >= max_results:
                    break
        return added

    while len(entries) < max_results and idle_rounds < 3:
        elements = driver.find_elements(By.CSS_SELECTOR, TITLE_LINK_SELECTOR)
        previous_total = len(elements)
        collect_from_elements(elements)
        if len(entries) >= max_results:
            break

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        try:
            load_more = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//button[.//span[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'load more results')]]",
                    )
                )
            )
            driver.execute_script("arguments[0].click();", load_more)
        except TimeoutException:
            pass

        try:
            WebDriverWait(driver, 10).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, TITLE_LINK_SELECTOR)) > previous_total
            )
            idle_rounds = 0
        except TimeoutException:
            idle_rounds += 1

    return entries[:max_results]


def extract_hotel_details(driver: webdriver.Chrome, hotel_url: str, use_cache: bool = USE_CACHE) -> Dict[str, object]:
    """Visit a hotel detail page and extract relevant information.
    
    Args:
        driver: Chrome WebDriver instance
        hotel_url: URL of the hotel page
        use_cache: If True, use cached HTML if available; if False, always fetch fresh
    """
    page_source: Optional[str] = None
    used_cached_html = False
    
    # Try to load from cache first
    if use_cache:
        page_source = load_html_from_cache(hotel_url)
        if page_source:
            print(f"  📂 Using cached HTML")
            used_cached_html = True
    
    # If no cache or cache disabled, fetch from web
    if not page_source:
        driver.get(hotel_url)
        # Wait for page to load using key elements instead of fixed sleep
        try:
            # Wait for either the title or room table to be present (whichever loads first)
            WebDriverWait(driver, 10).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, "[data-testid='title'], tbody tr[data-block-id], div.hp-description")
            )
        except TimeoutException:
            # If key elements don't appear, wait a shorter time for page to stabilize
            time.sleep(1)
        
        page_source = driver.page_source
        
        # Save to cache for future use
        if use_cache:
            save_html_to_cache(hotel_url, page_source)
    
    soup = BeautifulSoup(page_source, "html.parser")
    structured_data = parse_structured_data(page_source)

    title: Optional[str] = None
    if structured_data:
        name = structured_data.get("name")
        if isinstance(name, str):
            title = name.strip()
    if not title:
        title = safe_select_text(soup, "[data-testid='title']")
    if not title:
        title = safe_select_text(soup, "h1") or safe_select_text(soup, "h2")

    description: Optional[str] = None
    if structured_data:
        desc_val = structured_data.get("description")
        if isinstance(desc_val, str):
            description = desc_val.strip()
    if not description:
        description = safe_select_text(soup, "div.hp-description p")

    gallery_images: List[str] = []
    if structured_data:
        images = structured_data.get("image")
        if isinstance(images, list):
            gallery_images.extend(str(url) for url in images if isinstance(url, str))

    for img in soup.select("div#photo_wrapper img"):
        img_url = img.get("src") or img.get("data-src") or img.get("data-lazy")
        if img_url:
            gallery_images.append(img_url)

    facilities: List[str] = []
    if structured_data:
        amenities = structured_data.get("amenityFeature")
        if isinstance(amenities, list):
            for amenity in amenities:
                if isinstance(amenity, dict):
                    name = amenity.get("name")
                    if isinstance(name, str) and name.strip():
                        facilities.append(name.strip())

    # Extract facilities from spans with class "f6b6d2a959" (e.g., "2 swimming pools (1 open)")
    for facility_span in soup.select("span.f6b6d2a959"):
        text = facility_span.get_text(strip=True)
        if text:
            facilities.append(text)

    # Also check for facility badges
    for badge in soup.select("[data-testid='facility-badge']"):
        text = badge.get_text(strip=True)
        if text:
            facilities.append(text)

    latitude: Optional[str] = None
    longitude: Optional[str] = None

    if structured_data:
        geo = structured_data.get("geo")
        if isinstance(geo, dict):
            lat_val = geo.get("latitude")
            lon_val = geo.get("longitude")
            if isinstance(lat_val, (float, int, str)):
                latitude = str(lat_val)
            if isinstance(lon_val, (float, int, str)):
                longitude = str(lon_val)

        has_map = structured_data.get("hasMap")
        if (not latitude or not longitude) and isinstance(has_map, str):
            parsed_url = urlparse(has_map)
            center = parse_qs(parsed_url.query).get("center")
            if center:
                parts = center[0].split(",")
                if len(parts) == 2:
                    latitude, longitude = parts[0], parts[1]

    if not latitude or not longitude:
        map_image = soup.select_one("div.a88a546fb2 img, img[data-testid='static-map']")
        if map_image:
            map_url = map_image.get("src") or map_image.get("data-src")
            if map_url:
                match = re.search(r"center=([\d.-]+),([\d.-]+)", map_url)
                if match:
                    latitude, longitude = match.group(1), match.group(2)

    gallery_images = list(dict.fromkeys(gallery_images))
    facilities = list(dict.fromkeys(facilities))

    # Extract city information
    city: Optional[str] = None
    
    # First priority: extract city from input[name="ss"] value attribute
    ss_input = soup.select_one('input[name="ss"]')
    if ss_input and ss_input.get("value"):
        city = ss_input.get("value").strip()
        if city:
            # Validate it's not empty or just the country name
            if city.lower() in ("uae", "united arab emirates", "united arab emirates (uae)"):
                city = None
    
    # Second priority: try structured data
    if not city and structured_data:
        address_data = structured_data.get("address")
        if isinstance(address_data, dict):
            address_locality = address_data.get("addressLocality")
            if isinstance(address_locality, str):
                city = address_locality.strip()
    
    # Fallback: try to extract city from page elements
    if not city:
        city_element = soup.select_one("[data-testid='address'], .hp_address_subtitle, .hp_address")
        if city_element:
            city_text = city_element.get_text(strip=True)
            # Handle format: "Old Boulevard , Batumi (Old Boulevard )" - city appears before parentheses
            if city_text:
                # Check if there are parentheses in the address
                if "(" in city_text:
                    # Extract text before the opening parenthesis
                    before_paren = city_text.split("(")[0].strip()
                    # Split by comma and get the last non-empty part (the city)
                    parts = [p.strip() for p in before_paren.split(",") if p.strip()]
                    if parts:
                        # The city is typically the last part before the parenthesis
                        city = parts[-1]
                        # Validate it's not the country name
                        if city.lower() in ("uae", "united arab emirates", "united arab emirates (uae)"):
                            city = None
                            # Try the part before that if available
                            if len(parts) > 1:
                                city = parts[-2]
                
                # If no city found from parentheses format, try standard comma-separated format
                if not city:
                    parts = [p.strip() for p in city_text.split(",") if p.strip()]
                    # Look for city (usually second to last part, before country)
                    if len(parts) >= 2:
                        # Skip if it's just "UAE" or country name
                        potential_city = parts[-2] if len(parts) > 2 else parts[0]
                        if potential_city.lower() not in ("uae", "united arab emirates", "united arab emirates (uae)"):
                            city = potential_city
                    elif len(parts) == 1 and parts[0].lower() not in ("uae", "united arab emirates", "united arab emirates (uae)"):
                        city = parts[0]
    
    # Additional fallback: try to find city in breadcrumbs or location info
    if not city:
        location_breadcrumb = soup.select_one(".hp_location_breadcrumb, [data-testid='property-location-breadcrumb']")
        if location_breadcrumb:
            breadcrumb_text = location_breadcrumb.get_text(" ", strip=True)
            # Look for city name in breadcrumb (usually before "UAE" or "United Arab Emirates")
            if "United Arab Emirates" in breadcrumb_text:
                parts = breadcrumb_text.split("United Arab Emirates")[0].strip().split()
                if parts:
                    city = parts[-1] if len(parts) > 1 else parts[0]
            elif "UAE" in breadcrumb_text:
                parts = breadcrumb_text.split("UAE")[0].strip().split()
                if parts:
                    city = parts[-1] if len(parts) > 1 else parts[0]

    # Extract location from div with classes "b99b6ef58f cb4b7a25d9 b06461926f"
    # Format: "Location Name, City, UAE"
    location: Optional[str] = None
    location_div = soup.select_one("div.b99b6ef58f.cb4b7a25d9.b06461926f")
    if location_div:
        # Get only direct text content (before nested divs)
        # The location text is the first text node before any nested div elements
        location_parts = []
        for child in location_div.children:
            if isinstance(child, str):
                # It's a text node - collect it
                text = child.strip()
                if text:
                    location_parts.append(text)
            elif isinstance(child, Tag):
                # It's an element node (Tag) - stop here as we've reached nested content
                break
        
        if location_parts:
            location = " ".join(location_parts).strip()
        else:
            # Fallback: get all text and extract first line or reasonable part
            full_text = location_div.get_text(" ", strip=True)
            if full_text:
                # Split by newline to get first line
                lines = full_text.split("\n")
                if lines:
                    location = lines[0].strip()
                else:
                    location = full_text.strip()
                
                # If location is too long (likely includes nested content), try to extract just the location part
                if location and len(location) > 200:
                    # Look for pattern ending with "UAE" or "United Arab Emirates" and extract that part
                    if "United Arab Emirates" in location:
                        parts = location.split("United Arab Emirates")
                        if parts:
                            location = (parts[0] + "United Arab Emirates").strip()
                    elif "UAE" in location:
                        parts = location.split("UAE")
                        if parts:
                            location = (parts[0] + "UAE").strip()

    # Extract reviews count
    reviews_count: Optional[int] = None
    # Try to find span with reviews text (e.g., "· 699 reviews")
    reviews_elements = soup.select("span.f63b14ab7a, span.fb14de7f14, span.eaa8455879")
    for element in reviews_elements:
        text = element.get_text(" ", strip=True)
        if "reviews" in text.lower():
            # Extract number from text using regex (e.g., "· 699 reviews" -> 699)
            match = re.search(r"(\d+(?:[,\s]\d+)*)\s*reviews?", text, re.IGNORECASE)
            if match:
                number_str = match.group(1).replace(",", "").replace(" ", "")
                try:
                    reviews_count = int(number_str)
                    break
                except ValueError:
                    pass
    
    # Fallback: search for any element containing "reviews" pattern
    if reviews_count is None:
        for element in soup.select("span, div, p"):
            text = element.get_text(" ", strip=True)
            if "reviews" in text.lower():
                match = re.search(r"(\d+(?:[,\s]\d+)*)\s*reviews?", text, re.IGNORECASE)
                if match:
                    number_str = match.group(1).replace(",", "").replace(" ", "")
                    try:
                        reviews_count = int(number_str)
                        break
                    except ValueError:
                        pass

    # Extract rating
    rating: Optional[float] = None
    # Look for div with classes "f63b14ab7a dff2e52086" containing rating (e.g., "9.0")
    # First try the specific combination that typically contains ratings
    rating_elements = soup.select("div.f63b14ab7a.dff2e52086")
    for element in rating_elements:
        rating_text = element.get_text(strip=True)
        if rating_text and "reviews" not in rating_text.lower():
            # Try to parse as float (e.g., "9.0" -> 9.0)
            try:
                rating_value = float(rating_text)
                # Validate it's a reasonable rating (typically 0-10 for booking.com)
                if 0 <= rating_value <= 10:
                    rating = rating_value
                    break
            except ValueError:
                pass
    
    # Fallback: try other div elements with class "f63b14ab7a" that might contain rating
    if rating is None:
        fallback_elements = soup.select("div.f63b14ab7a")
        for element in fallback_elements:
            rating_text = element.get_text(strip=True)
            # Skip if it contains "reviews" or other non-rating text
            if rating_text and "reviews" not in rating_text.lower() and len(rating_text) < 10:
                try:
                    rating_value = float(rating_text)
                    if 0 <= rating_value <= 10:
                        rating = rating_value
                        break
                except ValueError:
                    pass
    
    # Fallback: also check structured data for rating
    if rating is None and structured_data:
        aggregate_rating = structured_data.get("aggregateRating")
        if isinstance(aggregate_rating, dict):
            rating_value = aggregate_rating.get("ratingValue")
            if isinstance(rating_value, (int, float)):
                rating = float(rating_value)
            elif isinstance(rating_value, str):
                try:
                    rating = float(rating_value)
                except ValueError:
                    pass

    hotel_details = {
        "url": hotel_url,
        "title": title,
        "description": description,
        "gallery": gallery_images,
        "facilities": facilities,
        "latitude": latitude,
        "longitude": longitude,
        "city": city,
        "location": location,
        "reviews_count": reviews_count,
        "rating": rating,
    }

    pricing = extract_price_info(soup)
    if pricing:
        hotel_details["pricing"] = pricing

    # Only pass driver for room image extraction if we're not using cached HTML
    # (room image extraction requires interactive driver to click room links)
    # If we used cached HTML, driver is not on the page, so can't extract room images interactively
    driver_for_rooms = None if used_cached_html else driver
    rooms = extract_room_options(soup, driver=driver_for_rooms)
    if rooms:
        hotel_details["rooms"] = rooms

    return hotel_details


def _serialize_for_csv(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return json.dumps(value, ensure_ascii=False)


def compare_hotel_vs_room_images(hotel_data: List[Dict[str, object]]) -> None:
    """Print comparison of hotel gallery images vs room images for testing."""
    for hotel in hotel_data:
        hotel_title = hotel.get("title", "Unknown Hotel")
        hotel_gallery = hotel.get("gallery", [])
        rooms = hotel.get("rooms", [])
        
        print("\n" + "="*80)
        print(f"HOTEL: {hotel_title}")
        print("="*80)
        
        print(f"\nHotel Gallery Images ({len(hotel_gallery)} images):")
        for i, img in enumerate(hotel_gallery[:5], 1):  # Show first 5
            print(f"  {i}. {img}")
        if len(hotel_gallery) > 5:
            print(f"  ... and {len(hotel_gallery) - 5} more")
        
        print(f"\nRoom Galleries ({len(rooms)} rooms):")
        for room_idx, room in enumerate(rooms, 1):
            room_name = room.get("name", f"Room {room_idx}")
            room_gallery = room.get("gallery", [])
            print(f"\n  Room {room_idx}: {room_name}")
            if room_gallery:
                print(f"    Room Gallery ({len(room_gallery)} images):")
                for i, img in enumerate(room_gallery[:5], 1):  # Show first 5
                    print(f"      {i}. {img}")
                if len(room_gallery) > 5:
                    print(f"      ... and {len(room_gallery) - 5} more")
                
                # Check for overlap
                hotel_img_set = set(hotel_gallery)
                room_img_set = set(room_gallery)
                overlap = hotel_img_set & room_img_set
                if overlap:
                    print(f"    ⚠️  WARNING: {len(overlap)} images overlap with hotel gallery!")
                    for img in list(overlap)[:3]:
                        print(f"      - {img}")
                else:
                    print(f"    ✓ No overlap with hotel gallery (images are different)")
            else:
                print(f"    (No gallery images for this room)")


def write_hotels_to_csv(hotel_data: List[Dict[str, object]], append: bool = False) -> None:
    if not hotel_data:
        print("No hotel data to write.")
        return

    fieldnames = sorted({key for entry in hotel_data for key in entry.keys()})

    mode = "a" if append else "w"
    with OUTPUT_PATH.open(mode, newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        if not append:
            writer.writeheader()
        for entry in hotel_data:
            writer.writerow({field: _serialize_for_csv(entry.get(field)) for field in fieldnames})

    print(f"Saved {len(hotel_data)} hotels to {OUTPUT_PATH}")


def main(max_hotels: int = MAX_HOTELS) -> None:
    # Show cache statistics
    if USE_CACHE:
        cache_stats = get_cache_stats()
        print(f"{'='*60}")
        print(f"📂 HTML CACHE STATUS")
        print(f"{'='*60}")
        print(f"Cache enabled: {USE_CACHE}")
        print(f"Cached files: {cache_stats['cached_files']}")
        print(f"Cache size: {cache_stats['total_size_mb']} MB")
        if cache_stats['cached_files'] > 0:
            print(f"Cache directory: {cache_stats['cache_dir']}")
            print(f"ℹ️  Will use cached HTML where available (faster, no re-download)")
        else:
            print(f"ℹ️  No cached files yet - HTML will be downloaded and cached")
        print(f"{'='*60}\n")
    
    driver = build_driver(headless=True)
    try:
        # Set currency preference to USD before scraping
        print("Setting currency preference to USD...")
        set_currency_preference(driver, currency="USD")
        time.sleep(2)
        
        total_target = max_hotels
        num_cities = len(CITIES)
        
        # Collect more links than needed as buffer (since some hotels may not have rooms data)
        # Use 2x multiplier to ensure we have enough candidates
        buffer_multiplier = 2
        total_links_to_collect = total_target * buffer_multiplier
        
        # Calculate hotels per city: base is min_per_city, distribute remainder
        min_per_city = 10
        base_per_city = min_per_city
        remainder = total_links_to_collect - (base_per_city * num_cities)
        hotels_per_city = [base_per_city] * num_cities
        
        # Distribute remainder across cities (prefer earlier cities, wrap around if needed)
        for i in range(remainder):
            city_idx = i % num_cities
            hotels_per_city[city_idx] += 1
        
        print(f"Target: {total_target} hotels with complete data")
        print(f"Collecting {total_links_to_collect} hotel links as buffer (hotels without rooms will be skipped)")
        print(f"Distribution: {dict(zip(CITIES, hotels_per_city))}")
        
        all_hotel_entries: List[Dict[str, object]] = []
        
        for idx, city in enumerate(CITIES):
            target_count = hotels_per_city[idx]
            print(f"Collecting {target_count} hotel link(s) for {city}...")
            city_entries = collect_hotel_links_for_city(driver, city=city, max_results=target_count)
            if len(city_entries) < target_count:
                print(f"Warning: Only found {len(city_entries)} entries for {city} (requested {target_count}).")
            all_hotel_entries.extend(city_entries)

        if not all_hotel_entries:
            print("No hotels found for the specified cities.")
            return

        print(f"\nCollected {len(all_hotel_entries)} hotel links. Processing until we have {total_target} hotels with complete data...")
        
        # Define batch sizes for incremental saving (10 hotels per batch)
        batch_size = 10
        batch_thresholds = list(range(batch_size, total_target + batch_size, batch_size))
        
        hotel_data: List[Dict[str, object]] = []
        current_batch_data: List[Dict[str, object]] = []
        skipped_count = 0
        current_batch_num = 0
        next_batch_threshold = batch_thresholds[0] if batch_thresholds else total_target
        
        for index, entry in enumerate(all_hotel_entries, start=1):
            # Stop if we've already collected enough hotels with complete data
            if len(hotel_data) >= total_target:
                print(f"\n✓ Successfully collected {total_target} hotels with complete data!")
                break
                
            url = entry.get("url")
            if not isinstance(url, str) or not url:
                print(f"[{index}/{len(all_hotel_entries)}] Skipping entry with invalid URL: {entry}")
                skipped_count += 1
                continue

            print(f"[{index}/{len(all_hotel_entries)}] [Found: {len(hotel_data)}/{total_target}] Scraping {url}")
            details = extract_hotel_details(driver, url)
            
            # Check if hotel has rooms data
            rooms = details.get("rooms", [])
            if not rooms or len(rooms) == 0:
                print(f"  ⚠️  Skipping hotel (no rooms data available)")
                skipped_count += 1
                continue
            
            # Add search metadata
            search_pricing = entry.get("search_pricing")
            if isinstance(search_pricing, dict) and search_pricing:
                details["search_pricing"] = search_pricing
            search_city = entry.get("search_city")
            if isinstance(search_city, str) and search_city:
                details["search_city"] = search_city

            hotel_data.append(details)
            current_batch_data.append(details)
            print(f"  ✓ Added hotel with {len(rooms)} room(s)")
            
            # Check if we've reached a batch threshold
            if len(hotel_data) >= next_batch_threshold:
                current_batch_num += 1
                batch_size_actual = len(current_batch_data)
                print(f"\n{'='*60}")
                print(f"📦 BATCH {current_batch_num} COMPLETE ({batch_size_actual} hotels)")
                print(f"{'='*60}")
                
                # Save batch to CSV (append mode after first batch)
                is_first_batch = (current_batch_num == 1)
                write_hotels_to_csv(current_batch_data, append=not is_first_batch)
                
                # Save cumulative JSON backup
                json_path = OUTPUT_PATH.with_suffix('.json')
                with json_path.open("w", encoding="utf-8") as json_file:
                    json.dump(hotel_data, json_file, ensure_ascii=False, indent=2)
                print(f"💾 Saved batch to CSV and cumulative JSON ({len(hotel_data)} total hotels)")
                print(f"{'='*60}\n")
                
                # Clear current batch and update threshold
                current_batch_data = []
                if current_batch_num < len(batch_thresholds):
                    next_batch_threshold = batch_thresholds[current_batch_num]
            
            # Reduced sleep between hotels - page loads are handled by WebDriverWait
            time.sleep(0.3)
        
        # Save any remaining hotels in incomplete batch
        if current_batch_data:
            current_batch_num += 1
            print(f"\n{'='*60}")
            print(f"📦 FINAL BATCH ({len(current_batch_data)} hotels)")
            print(f"{'='*60}")
            is_first_batch = (current_batch_num == 1)
            write_hotels_to_csv(current_batch_data, append=not is_first_batch)
            json_path = OUTPUT_PATH.with_suffix('.json')
            with json_path.open("w", encoding="utf-8") as json_file:
                json.dump(hotel_data, json_file, ensure_ascii=False, indent=2)
            print(f"💾 Saved final batch to CSV and JSON")
            print(f"{'='*60}\n")
        
        # Check if we got enough hotels
        if len(hotel_data) < total_target:
            print(f"\n⚠️  Warning: Only collected {len(hotel_data)} hotels with complete data (target was {total_target})")
            print(f"   Skipped {skipped_count} hotels due to missing rooms data")
            print(f"   Consider increasing the buffer multiplier or expanding the search")
        else:
            print(f"\n✅ COMPLETE: Successfully collected {len(hotel_data)} hotels with complete data in {current_batch_num} batch(es)")
            print(f"   Skipped {skipped_count} hotels due to missing rooms data")
        
    finally:
        driver.quit()


if __name__ == "__main__":
    # QUICK CONFIGURATION:
    # 1. To scrape 100 hotels with caching: (default)
    #    main(max_hotels=MAX_HOTELS)
    #
    # 2. To scrape with fresh data (no cache):
    #    Set USE_CACHE = False at line ~112
    #
    # 3. To clear cache and start fresh:
    #    clear_cache()
    #
    # 4. To view cache statistics:
    #    print(get_cache_stats())
    
    main(max_hotels=MAX_HOTELS)

