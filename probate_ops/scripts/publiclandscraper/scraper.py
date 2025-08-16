# qpublic_batch_scraper.py
# Usage:
#   python qpublic_batch_scraper.py --in input.csv --out enriched.csv --headful
#
# CSV must have at least: County, Street Address, City, State, Zip Code
#
# Anti-bot hygiene: randomized UA, human-like typing, jittered waits, retries,
# reusing a single browser per county (reduces repetitive navigation).

import argparse
import random
import time
import re
import sys
from typing import Dict, List, Tuple, Optional

import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    StaleElementReferenceException,
)
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options

QPUBLIC_ROOT = "https://qpublic.schneidercorp.com/"

# ---------------------------
# Small utility helpers
# ---------------------------

def jitter(a: float, b: float) -> float:
    """Random jitter sleep seconds."""
    return random.uniform(a, b)

def sleepy(a: float, b: float) -> None:
    time.sleep(jitter(a, b))

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

def build_driver(headless: bool) -> webdriver.Chrome:
    opts = Options()
    opts.add_argument(f"--user-agent={random.choice(UA_POOL)}")

    if not headless:
        opts.add_argument("--start-maximized")
    else:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1600,1000")

    # Make it look less like automation
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--no-sandbox")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=opts)
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": """Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"""}
        )
    except Exception:
        pass
    return driver

def soup_from_html(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")

def wait_clickable(driver, locator, timeout=25):
    return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(locator))

def type_like_human(el, text: str):
    el.clear()
    sleepy(0.2, 0.5)
    for chunk in re.findall(r".{1,6}", text):
        el.send_keys(chunk)
        sleepy(0.06, 0.2)

def safe_text(el) -> str:
    try:
        return el.get_text(strip=True)
    except Exception:
        return ""

def text_or_empty(soup, selector) -> str:
    node = soup.select_one(selector)
    return node.get_text(strip=True) if node else ""

def first_or_empty(lst: List[str]) -> str:
    return lst[0] if lst else ""

# ---------------------------
# Robust navigation helpers
# ---------------------------

def _click_property_search_or_go(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """
    Click the 'Property Search' tile. If clicking fails, navigate using its href.
    Ensures we land on Real Property Search (PageTypeID=2) or see Terms modal.
    """
    def find_tile():
        return driver.find_element(By.XPATH, "//h3[normalize-space()='Property Search']/ancestor::a")

    # Re-find after county selection (DOM refresh)
    prop_link = wait.until(EC.presence_of_element_located(
        (By.XPATH, "//h3[normalize-space()='Property Search']/ancestor::a")
    ))
    sleepy(0.2, 0.5)

    # Try JS click first (overlays can block native)
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", prop_link)
        sleepy(0.2, 0.5)
        driver.execute_script("arguments[0].click();", prop_link)
    except StaleElementReferenceException:
        prop_link = find_tile()
        driver.execute_script("arguments[0].click();", prop_link)
    except Exception:
        # Native click fallback
        try:
            prop_link.click()
        except Exception:
            pass

    # Verify navigation or do hard href get
    def on_rp_or_terms(d):
        return (
            "PageTypeID=2" in d.current_url
            or d.find_elements(By.CSS_SELECTOR, "div.modal.in, div.modal[aria-label='Terms and Conditions']")
            or d.find_elements(By.ID, "ctlBodyPane_ctl01_ctl01_txtAddress")
        )

    try:
        WebDriverWait(driver, 6).until(on_rp_or_terms)
    except TimeoutException:
        # Pull href and go directly
        try:
            prop_link = find_tile()
        except Exception:
            # Re-locate via alternative anchor text (rare theme variant)
            prop_link = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//a[.//h3[contains(., 'Property')]]")
            ))
        href = prop_link.get_attribute("href")
        if not href:
            # Last-resort: extract via 'Links' in page if present
            alt = driver.find_elements(By.XPATH, "//a[contains(@href,'PageTypeID=2') and contains(.,'Property Search')]")
            href = alt[0].get_attribute("href") if alt else None
        if not href:
            raise RuntimeError("Could not resolve Property Search link href.")
        driver.get(href)
        WebDriverWait(driver, 12).until(on_rp_or_terms)

    # Terms modal → click Agree
    try:
        WebDriverWait(driver, 8).until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "div.modal.in, div.modal[aria-label='Terms and Conditions']")
            )
        )
        sleepy(0.4, 0.9)
        agree = driver.find_element(
            By.XPATH, "//div[contains(@class,'modal')]//a[@data-dismiss='modal' and normalize-space()='Agree']"
        )
        driver.execute_script("arguments[0].click();", agree)
        WebDriverWait(driver, 10).until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.modal.in")))
        WebDriverWait(driver, 6).until(
            lambda d: "modal-open" not in d.find_element(By.TAG_NAME, "body").get_attribute("class")
        )
        sleepy(0.2, 0.5)
    except TimeoutException:
        # No modal shown (often after first accept)
        pass

def choose_ga_and_county(driver, county_query: str) -> None:
    """From qPublic homepage: Local tab -> State=Georgia -> County match -> Property Search."""
    driver.get(QPUBLIC_ROOT)
    wait = WebDriverWait(driver, 25)
    sleepy(1.0, 2.0)

    # Ensure Local tab
    try:
        local = wait.until(EC.presence_of_element_located((By.ID, "btnLocal")))
        if "active" not in (local.get_attribute("class") or ""):
            try:
                local.click()
            except Exception:
                driver.execute_script("arguments[0].click();", local)
        sleepy(0.2, 0.6)
    except Exception:
        pass

    # Select Georgia
    state_input = wait_clickable(driver, (By.ID, "stateMenuButton"), timeout=20)
    state_input.click()
    sleepy(0.2, 0.5)
    state_input.send_keys(Keys.CONTROL, "a")
    state_input.send_keys("Georgia")
    sleepy(0.5, 1.0)
    ga_opt = wait_clickable(driver, (By.CSS_SELECTOR, "#stateMenuContent #state-option-Georgia"), timeout=15)
    ga_opt.click()
    sleepy(0.3, 0.8)

    # County dropdown
    county_input = wait_clickable(driver, (By.ID, "areaMenuButton"), timeout=15)
    county_input.click()
    sleepy(0.2, 0.5)
    county_input.send_keys(Keys.CONTROL, "a")
    county_input.send_keys(county_query)
    sleepy(0.7, 1.4)

    # Click first real option
    area_menu = wait.until(EC.visibility_of_element_located((By.ID, "areaMenuContent")))
    options = area_menu.find_elements(By.CSS_SELECTOR, ".dropdown-option:not(.no-match):not(.all-option)")
    if not options:
        raise RuntimeError(f"No county options matched '{county_query}'.")
    try:
        options[0].click()
    except Exception:
        driver.execute_script("arguments[0].click();", options[0])
    sleepy(0.3, 0.8)

    # NOW: robustly open Real Property Search
    _click_property_search_or_go(driver, wait)

# ---------------------------
# Search & scrape per record
# ---------------------------

def search_address_and_open_first(driver, address: str) -> None:
    """
    On Real Property Search page:
      - type address in 'Search by Location Address'
      - click Search
      - if results page (PageTypeID=3), click first result
      - otherwise, if directly on report (PageTypeID=4), continue
    """
    # Focus address input (most GA counties use this ID)
    addr_input = wait_clickable(driver, (By.ID, "ctlBodyPane_ctl01_ctl01_txtAddress"), timeout=20)
    type_like_human(addr_input, address)

    # Click address Search
    wait_clickable(driver, (By.ID, "ctlBodyPane_ctl01_ctl01_btnSearch"), timeout=12).click()
    sleepy(0.8, 1.6)

    def on_page_type(ptype: str) -> bool:
        return f"PageTypeID={ptype}" in driver.current_url

    try:
        WebDriverWait(driver, 18).until(lambda d: on_page_type("3") or on_page_type("4"))
    except TimeoutException:
        raise RuntimeError("Search didn't navigate to Results/Report page.")

    if on_page_type("3"):
        # Click first parcel link
        try:
            first_link = WebDriverWait(driver, 12).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(@href,'PageTypeID=4') and contains(@href,'KeyValue=')]")
                )
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", first_link)
            sleepy(0.2, 0.6)
            try:
                first_link.click()
            except Exception:
                driver.execute_script("arguments[0].click();", first_link)
            WebDriverWait(driver, 15).until(lambda d: on_page_type("4"))
        except TimeoutException:
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='PageTypeID=4'][href*='KeyValue=']")
            if not links:
                raise RuntimeError("No parcel links found on Results page.")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", links[0])
            sleepy(0.2, 0.6)
            try:
                links[0].click()
            except Exception:
                driver.execute_script("arguments[0].click();", links[0])
            WebDriverWait(driver, 15).until(lambda d: on_page_type("4"))

# ---------------------------
# HTML parsing (report page)
# ---------------------------

def scrape_two_col_table(tbl: BeautifulSoup) -> Dict[str, str]:
    out = {}
    for row in tbl.select("tr"):
        th = row.find("th")
        td = row.find("td")
        if not th or not td:
            continue
        label = safe_text(th).strip(": ").replace("\xa0", " ")
        value = safe_text(td)
        out[label] = value
    return out

def money_to_int(s: str) -> Optional[int]:
    s = s.replace(",", "").replace("$", "").strip()
    return int(s) if s.isdigit() else None

def parse_report_html(html: str) -> Dict[str, str]:
    soup = soup_from_html(html)

    record: Dict[str, str] = {}

    # ---------------- Summary ----------------
    summary_tbl = soup.select_one("#ctlBodyPane_ctl01_ctl01_dynamicSummaryData_divSummary table.tabular-data-two-column")
    if summary_tbl:
        summary = scrape_two_col_table(summary_tbl)
        record["parcel_number"] = summary.get("Parcel Number", "")
        record["location_address"] = summary.get("Location Address", "")
        record["legal_description"] = summary.get("Legal Description", "")
        record["class"] = summary.get("Class", "")
        record["zoning"] = summary.get("Zoning", "")
        record["tax_district"] = summary.get("Tax District", "")
        record["millage_rate"] = summary.get("Millage Rate", "")
        record["acres"] = summary.get("Acres", "")
        record["neighborhood"] = summary.get("Neighborhood", "")
        record["homestead_code"] = summary.get("Homestead Code", "")
        record["topography"] = summary.get("Topography", "")

    # ---------------- Owner ----------------
    owner_block = soup.select_one("#ctlBodyPane_ctl02_mSection .module-content")
    if owner_block:
        owner_name = text_or_empty(owner_block, "#ctlBodyPane_ctl02_ctl01_rptOwner_ctl00_sprOwnerName1_lnkUpmSearchLinkSuppressed_lblSearch")
        record["owner_primary_name"] = owner_name
        owner_addr = text_or_empty(owner_block, "#ctlBodyPane_ctl02_ctl01_rptOwner_ctl00_lblOwnerAddress")
        lines = [ln.strip() for ln in owner_addr.splitlines() if ln.strip()]
        record["owner_address_full"] = " ".join(lines)
        if len(lines) >= 2:
            record["owner_mailing_line1"] = lines[0]
            city_state_zip = lines[1]
            m = re.search(r"^(.*?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$", city_state_zip)
            if m:
                record["owner_city"] = m.group(1)
                record["owner_state"] = m.group(2)
                record["owner_zip"] = m.group(3)

    # ---------------- Land (first row) ----------------
    land_row = soup.select_one("#ctlBodyPane_ctl04_ctl01_grdLand_grdFlat tbody tr")
    if land_row:
        tds = [td.get_text(strip=True) for td in land_row.select("td")]
        desc = text_or_empty(land_row, "th")
        record["land_description"] = desc
        if len(tds) >= 1: record["land_calc_method"] = tds[0]
        if len(tds) >= 2: record["land_sqft"] = tds[1]
        if len(tds) >= 3: record["land_frontage"] = tds[2]
        if len(tds) >= 4: record["land_depth"] = tds[3]
        if len(tds) >= 5: record["land_acres_row"] = tds[4]
        if len(tds) >= 6: record["land_lots"] = tds[5]

    # ---------------- Residential Improvement (left column) ----------------
    res_left_tbl = soup.select_one("#ctlBodyPane_ctl05_ctl01_lstBuildings_ctl00_dynamicBuildingDataLeftColumn_divSummary table.tabular-data-two-column")
    if res_left_tbl:
        res = scrape_two_col_table(res_left_tbl)
        keys_map = {
            "Card": "res_card",
            "Style": "res_style",
            "Heated Square Feet": "res_heated_sqft",
            "Exterior Wall": "res_exterior_wall",
            "Attic Square Feet": "res_attic_sqft",
            "Finished Bsmt Sqft": "res_finished_bsmt_sqft",
            "Total Bsmt Sqft": "res_total_bsmt_sqft",
            "Year Built": "res_year_built",
            "Roof Type": "res_roof_type",
            "Flooring Type": "res_flooring_type",
            "Heating Type": "res_heating_type",
            "Number of Rooms": "res_rooms",
            "Number of Bedrooms": "res_bedrooms",
            "Condition": "res_condition",
            "Fireplaces\\Appliances": "res_fireplaces_appliances",
            "Number Of Plumbing Extras": "res_plumbing_extras",
            "Half Bath (2 Fixture)": "res_half_bath_2_fix",
            "Full Bath (3 Fixture)": "res_full_bath_3_fix",
            "Bath (4 Fixture)": "res_bath_4_fix",
            "Bath (5 Fixture)": "res_bath_5_fix",
            "Bath (6 Fixture)": "res_bath_6_fix",
            "Bath (7 Fixture)": "res_bath_7_fix",
        }
        for k_src, k_dst in keys_map.items():
            record[k_dst] = res.get(k_src, "")

    # ---------------- Accessory Information (all rows, flattened) ----------------
    acc_rows = soup.select("#ctlBodyPane_ctl09_ctl01_lstOBYMaster_ctl00_gvwOBY tbody tr")
    acc_pieces: List[str] = []
    for r in acc_rows:
        cols = [c.get_text(strip=True) for c in r.select("th,td")]
        if len(cols) >= 5:
            piece = f"{cols[0]}|{cols[1]}|{cols[2]}|{cols[3]}|{cols[4]}"
        else:
            piece = "|".join(cols)
        acc_pieces.append(piece)
    record["accessories_concat"] = " || ".join(acc_pieces)

    # ---------------- Valuation - Current Appraised (100%) ----------------
    appr_row = soup.select_one("#ctlBodyPane_ctl13_ctl01_gvValuationAppr tbody tr")
    if appr_row:
        tds = [c.get_text(strip=True) for c in appr_row.select("th,td")]
        if len(tds) >= 6:
            record["appr_year"] = tds[0]
            record["appr_prop_class"] = tds[1]
            record["appr_luc"] = tds[2]
            record["appr_land"] = tds[3]
            record["appr_building"] = tds[4]
            record["appr_total"] = tds[5]

    # ---------------- Valuation - Current Assessed (40%) ----------------
    asmt_row = soup.select_one("#ctlBodyPane_ctl14_ctl01_gvValuationAsmt tbody tr")
    if asmt_row:
        tds = [c.get_text(strip=True) for c in asmt_row.select("th,td")]
        if len(tds) >= 4:
            record["asmt_year"] = tds[0]
            record["asmt_land"] = tds[1]
            record["asmt_building"] = tds[2]
            record["asmt_total"] = tds[3]

    # ---------------- Sketch image (if any) ----------------
    sketch_img = soup.select_one("#sketchgrid img.rsImg")
    if sketch_img and sketch_img.has_attr("src"):
        record["sketch_image_url"] = sketch_img["src"]

    # ---------------- Assessment Notices (buttons) ----------------
    notice_buttons = soup.select("#ctlBodyPane_ctl16_ctl01_pnlButtonMain input.btn.btn-primary")
    notice_links = []
    for btn in notice_buttons:
        oc = btn.get("onclick", "")
        m = re.search(r"window\.open\('([^']+)'", oc)
        if m:
            notice_links.append(m.group(1))
    record["assessment_notice_urls"] = " | ".join(notice_links)

    return record

# ---------------------------
# Orchestration for many rows
# ---------------------------

def process_one(driver, county: str, address: str) -> Tuple[Dict[str, str], Optional[str]]:
    """
    Returns (scraped_record_dict, error_message_if_any)
    Keeps driver on the Report page at the end.
    """
    try:
        # If we're not on Real Property Search for a county, go select it.
        if "PageTypeID=2" not in driver.current_url:
            choose_ga_and_county(driver, county)

        search_address_and_open_first(driver, address)
        sleepy(0.5, 1.2)
        # Human-ish scroll
        driver.execute_script("window.scrollTo(0, 400);")
        sleepy(0.2, 0.6)
        driver.execute_script("window.scrollTo(0, 0);")
        html = driver.page_source
        data = parse_report_html(html)
        return data, None
    except Exception as e:
        return {}, f"{type(e).__name__}: {e}"

def run_batch(input_csv: str, output_csv: str, headless: bool) -> None:
    df = pd.read_csv(input_csv, dtype=str).fillna("")
    required_cols = ["County", "Street Address"]
    for col in required_cols:
        if col not in df.columns:
            raise SystemExit(f"Input CSV missing required column: {col}")

    out_rows: List[Dict[str, str]] = []
    driver = build_driver(headless=headless)
    current_county = None

    try:
        for idx, row in df.iterrows():
            county = row["County"].strip()
            street = row["Street Address"].strip()
            street_query = street  # county scoping usually makes street enough

            # Small randomized pause per record
            sleepy(0.8, 2.2)

            # If county changed, reopen search for that county
            if current_county != county:
                try:
                    choose_ga_and_county(driver, county)
                    current_county = county
                except Exception as e:
                    enriched = {}
                    enriched["scrape_error"] = f"Navigation error for county '{county}': {e}"
                    combined = {**row.to_dict(), **enriched}
                    out_rows.append(combined)
                    continue

            data, err = process_one(driver, county, street_query)

            enriched = data.copy()
            enriched["qpublic_report_url"] = driver.current_url if data else ""
            enriched["scrape_error"] = err or ""

            # Attach your primary key columns
            enriched["pk_county"] = county
            enriched["pk_street_address"] = street

            combined = {**row.to_dict(), **enriched}
            out_rows.append(combined)

            # Random dwell / motion
            sleepy(0.6, 1.8)
            if random.random() < 0.25:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * Math.random());")
                sleepy(0.2, 0.5)

        # Normalize and write CSV
        out_df = pd.DataFrame(out_rows)
        orig_cols = list(df.columns)
        new_cols = [c for c in out_df.columns if c not in orig_cols]
        ordered_cols = orig_cols + sorted(new_cols)
        out_df = out_df.reindex(columns=ordered_cols)
        out_df.to_csv(output_csv, index=False)

    finally:
        try:
            driver.quit()
        except Exception:
            pass

def main():
    parser = argparse.ArgumentParser(description="qPublic batch scraper → one-row-per-input CSV.")
    parser.add_argument("--in", dest="in_csv", required=True, help="Input CSV path")
    parser.add_argument("--out", dest="out_csv", required=True, help="Output CSV path")
    parser.add_argument("--headful", action="store_true", help="Run with visible Chrome (default headless)")
    args = parser.parse_args()

    run_batch(args.in_csv, args.out_csv, headless=not args.headful)

if __name__ == "__main__":
    main()
