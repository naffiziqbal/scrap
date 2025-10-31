from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
from urllib.parse import urljoin, urlparse, parse_qs, urlencode


OUTPUT_PATH = Path("georgia_hotels.json")
MAX_HOTELS = 10
SEARCH_RESULTS_PAGE_SIZE = 25

BASE_SEARCH_URL = "https://www.booking.com/searchresults.html"
DEFAULT_SEARCH_QUERY = {
    "aid": "304142",
    "label": "gen173nr-10CAQoggJCDnNlYXJjaF9nZW9yZ2lhSDNYBGgUiAEBmAEzuAEHyAEM2AED6AEB-AEBiAIBqAIBuAKzg4nIBsACAdICJGNjYmE2MGNiLTBkMjAtNDI3ZS05ODkzLWFhZWZlMzQ2ZWNhZtgCAeACAQ",
    "sid": "35788a66b0bc8369c8d88feab7d284bc",
    "lang": "en-us",
    "selected_currency":"USD",
    "sb": "1",
    "src": "searchresults",
    "src_elem": "sb",
    "ss": "Batumi",
    "ssne": "Batumi",
    "ssne_untouched": "Batumi",
    "checkin": "2025-11-01",
    "checkout": "2025-11-02",
    "group_adults": "2",
    "group_children": "0",
    "no_rooms": "1",
    "rows": str(SEARCH_RESULTS_PAGE_SIZE),
    "sb_travel_purpose": "leisure",
}

TITLE_LINK_SELECTOR = "a[data-testid='titleLink'],a[data-testid='title-link']"


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


def extract_price_info(
    soup: BeautifulSoup,
    structured_data: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
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

    if structured_data:
        offers = structured_data.get("offers")
        offer_candidates: List[Dict[str, object]] = []
        if isinstance(offers, list):
            offer_candidates = [offer for offer in offers if isinstance(offer, dict)]
        elif isinstance(offers, dict):
            offer_candidates = [offers]

        for offer in offer_candidates:
            price_value = offer.get("price")
            price_currency = offer.get("priceCurrency")

            if price_currency and "current_price_currency" not in price_info:
                price_info["current_price_currency"] = str(price_currency)

            if price_value and "current_price_amount" not in price_info:
                try:
                    numeric_price = float(price_value)
                except (TypeError, ValueError):
                    numeric_price = None

                if numeric_price is not None:
                    price_info["current_price_amount"] = numeric_price
                    price_info.setdefault("current_price_amount_text", str(price_value))
                else:
                    price_info.setdefault("current_price_amount_text", str(price_value))

            if "current_price_currency" in price_info and "current_price_amount" in price_info:
                break

    return {key: value for key, value in price_info.items() if value is not None}


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

    hotel_details = {
        "url": hotel_url,
        "title": title,
        "description": description,
        "gallery": gallery_images,
        "facilities": facilities,
        "latitude": latitude,
        "longitude": longitude,
    }

    pricing = extract_price_info(soup, structured_data)
    if pricing:
        hotel_details["pricing"] = pricing

    return hotel_details


def main(max_hotels: int = MAX_HOTELS) -> None:
    driver = build_driver(headless=True)
    try:
        hotel_entries = collect_hotel_links(driver, max_results=max_hotels)
        if not hotel_entries:
            print("No hotels found on the search results page.")
            return

        hotel_data: List[Dict[str, object]] = []
        for index, entry in enumerate(hotel_entries, start=1):
            url = entry.get("url")
            if not isinstance(url, str) or not url:
                print(f"[{index}/{len(hotel_entries)}] Skipping entry with invalid URL: {entry}")
                continue

            print(f"[{index}/{len(hotel_entries)}] Scraping {url}")
            details = extract_hotel_details(driver, url)
            search_pricing = entry.get("search_pricing")
            if isinstance(search_pricing, dict) and search_pricing:
                details["search_pricing"] = search_pricing

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
