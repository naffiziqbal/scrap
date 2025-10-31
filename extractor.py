from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup, SoupStrainer, Tag
import json
import re
import time
from urllib.parse import urljoin, urlparse, parse_qs


SEARCH_URL = (
    "https://www.booking.com/searchresults.html?aid=304142&label=gen173nr-10CAQoggJCDnNlYXJjaF9nZW9yZ2lhSDNYBGgUiAEBmAEzuAEHyAEM2AED6AEB-"
    "AEBiAIBqAIBuAKzg4nIBsACAdICJGNjYmE2MGNiLTBkMjAtNDI3ZS05ODkzLWFhZWZlMzQ2ZWNhZtgCAeACAQ&sid=35788a66b0bc8369c8d88feab7d284bc&checkin=2025-11-01&checkout=2025-11-02&dest_id=900049585&dest_type=city&srpvid=6aa4479224d8095b&"
)
OUTPUT_PATH = Path("georgia_hotels.json")


def build_driver(headless: bool = True) -> webdriver.Chrome:
    """Create a Chrome WebDriver instance."""

    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


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


def collect_hotel_links(driver: webdriver.Chrome, search_url: str) -> List[str]:
    """Navigate to the search page and collect unique hotel detail URLs."""

    driver.get(search_url)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-testid='titleLink']"))
        )
    except TimeoutException:
        time.sleep(5)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    links: List[str] = []
    seen: set[str] = set()

    for anchor in soup.select("a[data-testid='titleLink']"):
        href = anchor.get("href")
        if not href:
            continue
        clean = href.split("?")[0]
        absolute = urljoin("https://www.booking.com", clean)
        if absolute not in seen:
            seen.add(absolute)
            links.append(absolute)

    return links


def extract_hotel_details(driver: webdriver.Chrome, hotel_url: str) -> Dict[str, object]:
    """Visit a hotel detail page and extract relevant information."""

    driver.get(hotel_url)
    time.sleep(5)

    page_source = driver.page_source
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

    if not gallery_images:
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

    if not facilities:
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

        if not latitude or not longitude:
            has_map = structured_data.get("hasMap")
            if isinstance(has_map, str):
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

    return {
        "url": hotel_url,
        "title": title,
        "description": description,
        "gallery": gallery_images,
        "facilities": facilities,
        "latitude": latitude,
        "longitude": longitude,
    }


def main() -> None:
    driver = build_driver(headless=True)
    try:
        hotel_links = collect_hotel_links(driver, SEARCH_URL)
        if not hotel_links:
            print("No hotels found on the search results page.")
            return

        hotel_data: List[Dict[str, object]] = []
        for index, link in enumerate(hotel_links, start=1):
            print(f"[{index}/{len(hotel_links)}] Scraping {link}")
            details = extract_hotel_details(driver, link)
            hotel_data.append(details)
            time.sleep(1)

        OUTPUT_PATH.write_text(
            json.dumps(hotel_data, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Saved {len(hotel_data)} hotels to {OUTPUT_PATH}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
