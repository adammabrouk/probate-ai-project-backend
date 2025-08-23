#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import csv
import time
import random
import argparse
import logging
import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)


NO_RESULTS_XPATH = (
    "//h2[@aria-live='assertive' and contains("
    "translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
    "'no results match your search criteria.')]"
)

RESULT_LINK_XPATH = "//a[contains(@href,'KeyValue')]"
HOME_URL = "https://qpublic.schneidercorp.com/"
DEFAULT_TIMEOUT = 35

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


@dataclass
class RowCtx:
    row: Dict[str, Any]
    addr: str
    county: str
    state: str = "Georgia"
    appid: Optional[str] = None
    visited_url: Optional[str] = None


def page_has_no_results_text(driver) -> bool:
    """Return True iff the 'No results match your search criteria.' message is present."""
    return bool(driver.find_elements(By.XPATH, NO_RESULTS_XPATH))


def page_has_result_links(driver) -> bool:
    """Return True iff at least one parcel/result link is present."""
    return bool(driver.find_elements(By.XPATH, RESULT_LINK_XPATH))


def build_driver(headless=True) -> webdriver.Chrome:
    chrome_opts = Options()
    if headless:
        chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--window-size=1400,1000")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    chrome_opts.add_argument("--disable-blink-features=AutomationControlled")
    chrome_opts.add_experimental_option(
        "excludeSwitches", ["enable-automation"]
    )
    chrome_opts.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=chrome_opts)
    driver.set_page_load_timeout(60)
    return driver


def wait_any_of(wait: WebDriverWait, locators: List[tuple]) -> None:
    wait.until(
        EC.any_of(*[EC.presence_of_element_located(l) for l in locators])
    )


def js_click(driver, el):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    try:
        el.click()
    except Exception:
        try:
            el.send_keys(Keys.SPACE)
            el.send_keys(Keys.ENTER)
        except Exception:
            pass
        driver.execute_script("arguments[0].click();", el)


def select_state_and_county(driver, ctx: RowCtx):
    """Use the Local tab's advanced dropdowns to select State + County.
    Then extract the county AppID for resilient navigation."""
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)

    # ensure we're on home
    if "schneidercorp.com" not in driver.current_url:
        driver.get(HOME_URL)

    logger.info("Selecting state and county: %s, %s", ctx.state, ctx.county)
    # Make sure Local tab is active (btnLocal exists)
    try:
        btn_local = wait.until(EC.element_to_be_clickable((By.ID, "btnLocal")))
        logger.info("Clicking Local tab")
        js_click(driver, btn_local)
    except TimeoutException:
        pass  # often Local is already active

    # Open State drop and pick
    state_btn = wait.until(
        EC.presence_of_element_located((By.ID, "stateMenuButton"))
    )
    logger.info("Clicking State dropdown")
    js_click(driver, state_btn)
    time.sleep(0.2)

    # Find the state option by data-name (e.g., "Georgia")
    state_option = wait.until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                f"//div[@id='stateMenuContent']//div[@role='option' and @data-name='{ctx.state}']",
            )
        )
    )
    logger.info("Selecting State: %s", ctx.state)
    js_click(driver, state_option)

    # Open Area/County drop and pick
    area_btn = wait.until(
        EC.presence_of_element_located((By.ID, "areaMenuButton"))
    )
    logger.info("Clicking Area/County dropdown")
    js_click(driver, area_btn)
    time.sleep(0.2)

    # Exact visible label match like "Atkinson County, GA"
    # But some labels include two spaces in “County,  GA”, so match loosely
    area_option = wait.until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                "//div[@id='areaMenuContent']//div[@role='option' and contains(normalize-space(.), 'County') and contains(., ',') and contains(normalize-space(.), %s)]"
                % repr(f"{ctx.county} County"),
            )
        )
    )
    logger.info("Selecting Area/County: %s", ctx.county)
    js_click(driver, area_option)

    # Read selected option to capture AppID
    selected = wait.until(
        EC.presence_of_element_located(
            (
                By.CSS_SELECTOR,
                "#areaMenuContent .dropdown-option[aria-selected='true']",
            )
        )
    )
    logger.info("Selected Area/County: %s", selected.text)
    ctx.appid = selected.get_attribute("data-appid")


def navigate_into_app(driver, ctx: RowCtx):
    """Get into the county application.
    Prefers Quickstart 'Search Records' tile; falls back to direct Application.aspx?AppID=...
    """
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)

    # Wait for homepage bits which may render slowly
    try:
        logger.info("Waiting for homepage elements to load")
        wait_any_of(
            wait,
            [
                (By.ID, "quickstartList"),
                (By.CSS_SELECTOR, "iframe[src*='Application.aspx']"),
                (
                    By.XPATH,
                    "//a[contains(@href,'Application.aspx') and contains(@href,'AppID=')]",
                ),
            ],
        )
        logger.info("Homepage elements loaded")
    except TimeoutException:
        # try direct if we have appid
        logger.error("Timed out waiting for homepage elements")
        if ctx.appid:
            driver.get(f"{HOME_URL}Application.aspx?AppID={ctx.appid}")
            ctx.visited_url = driver.current_url
            return
        raise

    # 1) Try Quickstart "Search Records"
    try:
        logger.info("Trying to find Quickstart 'Search Records' link")
        link = driver.find_element(
            By.XPATH,
            "//div[@id='quickstartList']//a[.//h3[normalize-space()='Search Records']]",
        )
        href = link.get_attribute("href")
        logger.info("Found Quickstart 'Search Records' link: %s", href)
        if href:
            driver.get(href)
            ctx.visited_url = href
            return
    except NoSuchElementException:
        logger.error("Quickstart 'Search Records' link not found")
        pass

    # 2) If already inside app
    if "Application.aspx" in driver.current_url:
        logger.info("Already inside an application page")
        ctx.visited_url = driver.current_url
        return

    # 3) Fallback: first Application link on page
    try:
        logger.info("Trying to find first Application link on page")
        fallback = driver.find_element(
            By.XPATH,
            "//a[contains(@href,'Application.aspx') and contains(@href,'AppID=')]"
        )
        driver.get(fallback.get_attribute("href"))
        ctx.visited_url = driver.current_url
        return
    except NoSuchElementException:
        logger.error("No Application link found on page")
        pass

    # 4) Absolute fallback: construct from AppID
    if ctx.appid:
        driver.get(f"{HOME_URL}Application.aspx?AppID={ctx.appid}")
        ctx.visited_url = driver.current_url
        return

    raise RuntimeError("after county select: quickstart or app not found")


def switch_into_app_frame(driver):
    # wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    # wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "iframe")))
    # frames = driver.find_elements(By.CSS_SELECTOR, "iframe")
    # # Prefer the first visible one
    # for fr in frames:
    #     if fr.is_displayed():
    #         driver.switch_to.frame(fr)
    #         return
    # # else pick the first
    # driver.switch_to.frame(frames[0])

    # Wait for any <a> tag containing "Agree"
    logger.info("Waiting for 'Agree' button in iframe")
    agree_btn = WebDriverWait(driver, 2).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//a[normalize-space()='Agree']")
        )
    )
    driver.execute_script("arguments[0].click();", agree_btn)


def open_search_panel(driver):
    logger.info("Opening search panel")
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)

    # Some apps show a splash—give it a breath
    time.sleep(random.uniform(0.4, 1.0))

    # Try clicking a Search tab/button
    for by, sel in [
        (By.XPATH, "//a[normalize-space()='Search']"),
        (By.XPATH, "//button[normalize-space()='Search']"),
        (By.CSS_SELECTOR, "[data-tab='search'], .tab-search"),
    ]:
        els = driver.find_elements(by, sel)
        if els:
            js_click(driver, els[0])
            break
    logger.info("Search panel opened")
    # Expand Address/Location if collapsible
    for xp in [
        "//h2[contains(.,'Address') or contains(.,'Location')]",
        "//button[contains(.,'Address') or contains(.,'Location')]",
    ]:
        hdrs = driver.find_elements(By.XPATH, xp)
        if hdrs:
            # If it looks collapsed, click it
            klass = hdrs[0].get_attribute("class") or ""
            aria = hdrs[0].get_attribute("aria-expanded") or ""
            if "collapsed" in klass or aria == "false":
                js_click(driver, hdrs[0])
            break

    # Wait for an address input to appear
    wait.until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                "//input[contains(@id,'Address') or contains(@placeholder,'Address')]",
            )
        )
    )


def submit_address(driver, raw_address: str) -> str:

    field = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'address')]",
            )
        )
    )
    field.clear()
    field.send_keys(raw_address)
    field.send_keys(Keys.ENTER)

    # Wait for results to load
    wait = WebDriverWait(driver, 2)

    try:
        # Wait until at least one parcel/result link shows up
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//a[contains(@href,'KeyValue')]")
            )
        )
        # Return the current page URL (search results URL)
        return driver.current_url
    except Exception:
        logger.error(
            "No parcel links found after submitting address: %s", raw_address
        )
        raise RuntimeError(
            f"results: no parcel links; address not found for '{raw_address}'"
        )


# def submit_address(driver, raw_address: str) -> str:

#     field = WebDriverWait(driver, 15).until(
#         EC.presence_of_element_located((
#             By.XPATH,
#             "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'address')]"
#         ))
#     )
#     field.clear()
#     field.send_keys(raw_address)
#     field.send_keys(Keys.ENTER)

#     # Wait for results to load
#     wait = WebDriverWait(driver, DEFAULT_TIMEOUT)

#     try:
#         # Wait until at least one parcel/result link shows up
#         wait.until(EC.any_of(
#             EC.presence_of_element_located((By.XPATH, RESULT_LINK_XPATH)),
#             EC.presence_of_element_located((By.XPATH, NO_RESULTS_XPATH))
#         ))
#         # Return the current page URL (search results URL)

#         if page_has_no_results_text(driver):
#             raise RuntimeError(f"results: no parcel links; address not found for '{raw_address}'")
#         return driver.current_url

#     except TimeoutException:
#         raise RuntimeError(f"results: no parcel links; address not found for '{raw_address}'")


def extract_property_image(driver) -> Optional[str]:
    try:
        elems = driver.find_elements(By.CSS_SELECTOR, "img.rsImg")
        if elems:
            return elems[0].get_attribute("src")
        return None
    except Exception:
        return None


def extract_property_summary(driver, timeout: int = 2) -> dict:
    """
    Locate the first table matching:
      <table class="tabular-data-two-column" role="presentation">...</table>
    and extract header/value pairs from its rows.

    Returns:
        OrderedDict[str, str]
    """

    # Wait for the table to be present
    def clean(text: str) -> str:
        if text is None:
            return ""
        return text.strip()

    try:
        table = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "table.tabular-data-two-column[role='presentation']",
                )
            )
        )
    except TimeoutException:
        logger.error("Property summary table not found within timeout")
        return {}

    data = OrderedDict()

    rows = table.find_elements(By.CSS_SELECTOR, "tbody > tr, tr")
    for r in rows:
        ths = r.find_elements(By.TAG_NAME, "th")
        tds = r.find_elements(By.TAG_NAME, "td")
        if not ths or not tds:
            continue

        key = clean(ths[0].text)
        if not key or key.lower() == "view map":
            continue

        # Preserve original spacing
        val_text = tds[0].text.strip()

        # Fallback if .text is empty
        if not val_text:
            val_text = (tds[0].get_attribute("textContent") or "").strip()

        data[key] = val_text

    return data


# Valuation extraction functions
def _find_section_by_exact_title(driver, title_text):
    # search all sections and match the header .title text exactly (case-insensitive)
    sections = driver.find_elements(
        By.CSS_SELECTOR, "section[id^='ctlBodyPane_ctl'][id$='_mSection']"
    )
    for sec in sections:
        titles = sec.find_elements(By.CSS_SELECTOR, "header .title")
        if (
            titles
            and titles[0].text.strip().lower() == title_text.strip().lower()
        ):
            return sec
    return None


def _clean_money(s):
    # remove '$' but keep thousands separators, as in your desired output
    return s.replace("$", "").strip()


def extract_evaluation_appraised(driver):
    """Extract ALL years and total appraised values from Valuation (Appraised 100%)."""
    sec = _find_section_by_exact_title(driver, "Valuation (Appraised 100%)")
    if not sec:
        return {}

    data = {}

    # Collect both current + historical tables
    tables = []
    # tables += sec.find_elements(By.CSS_SELECTOR, "table[id*='_gvValuationHistoricalAppr']")
    tables += sec.find_elements(
        By.CSS_SELECTOR, "table[id*='gvValuationAppr']"
    )
    logger.info("Found %d valuation tables", len(tables))
    for table in tables:
        rows = table.find_elements(By.CSS_SELECTOR, "tbody tr[valign='top']")
        for r in rows:
            # year is the text inside the th.a
            year_cell = r.find_elements(By.CSS_SELECTOR, "th[scope='row']")
            if not year_cell:
                continue

            year_text = year_cell[0].text.strip()
            year = "".join(ch for ch in year_text if ch.isdigit())
            if not year:
                continue

            tds = r.find_elements(By.CSS_SELECTOR, "td")
            if not tds:
                continue
            total_value = tds[-1].text.strip()
            if total_value:
                data[year] = _clean_money(total_value)

    return data


def extract_valuation_std(driver):
    # ----- Case A: Valuation (assessed “Current Value”) -----
    sec = _find_section_by_exact_title(driver, "Valuation")
    if sec:
        tables = sec.find_elements(
            By.CSS_SELECTOR, "table[id*='grdValuation']"
        )
        if not tables:
            return {}
        table = tables[0]

        # years from last header row
        header_rows = table.find_elements(By.CSS_SELECTOR, "thead tr")
        if not header_rows:
            return {}
        header_cells = header_rows[-1].find_elements(By.CSS_SELECTOR, "th, td")
        years = [
            c.text.strip() for c in header_cells if c.text.strip().isdigit()
        ]

        # "Current Value" row
        cur = table.find_elements(
            By.XPATH, ".//tbody/tr[th[contains(normalize-space(.),'Current')]]"
        )
        if not cur:
            return {}
        vals = [
            td.text.strip()
            for td in cur[0].find_elements(By.CSS_SELECTOR, "td.value-column")
        ]

        # align from right in case some columns are hidden
        if len(vals) < len(years):
            years = years[-len(vals) :]

        return {y: _clean_money(v) for y, v in zip(years, vals)}

    return {}  # nothing found


def extract_valuation_any(driver):

    return {
        **extract_evaluation_appraised(driver),
        **extract_valuation_std(driver),
    }


def enrich_row(driver, row: Dict[str, Any]) -> Dict[str, Any]:
    """Main per-row routine with granular error logging."""
    # choose the best address input column available
    addr = (
        row.get("Street Address")
        or row.get("pk_street_address")
        or row.get("owner_address_full")
        or ""
    )
    county = (row.get("County") or "").strip()
    if not county:
        row["scrape_error"] = "missing County"
        return row
    if not addr:
        row["scrape_error"] = "missing address"
        return row

    ctx = RowCtx(row=row, addr=addr, county=county)

    try:
        driver.get(HOME_URL)
        select_state_and_county(driver, ctx)
    except Exception as e:
        row["scrape_error"] = (
            f"after state/county select: {type(e).__name__}: {str(e)[:800]}"
        )
        return row

    try:
        navigate_into_app(driver, ctx)
    except Exception as e:
        row["scrape_error"] = (
            f"navigation into app: {type(e).__name__}: {str(e)[:800]}"
        )
        return row

    try:
        # enter iframe (most Beacon apps)
        switch_into_app_frame(driver)
    except Exception as e:
        # Not fatal—some apps have no visible iframe (rare). Try to proceed.
        pass

    try:
        url = submit_address(driver, ctx.addr)
        row["qpublic_report_url"] = url
        row["scrape_error"] = ""
    except Exception as e:
        row["qpublic_report_url"] = ""
        row["scrape_error"] = f"No Data for Given Address"
        return row

    try:
        # Extract property summary table
        summary = extract_property_summary(driver)
        if summary:
            row["parcel_number"] = summary.get("Parcel Number", "")
            row["property_class"] = summary.get("Class", "")
            row["property_tax_district"] = summary.get("Tax District", "")
            row["property_acres"] = summary.get("Acres", "")

    except Exception as e:

        row[
            "scrape_error"
        ] += f" | summary extraction: {type(e).__name__}: {str(e)[:800]}"

    # Extract valuation data

    try:
        valuation_dict = extract_valuation_any(driver)

        for year in range(2025, 2019, -1):
            key = f"property_value_{year}"
            if str(year) in valuation_dict:
                row[key] = valuation_dict[str(year)]
            else:
                row[key] = ""
    except Exception as e:
        row[
            "scrape_error"
        ] += f" | valuation extraction: {type(e).__name__}: {str(e)[:800]}"

    try:
        img = extract_property_image(driver)
        if img:
            row["property_image"] = img
        else:
            row["property_image"] = ""
    except Exception as e:
        pass

    return row


# Decorator for keeping checkpoint of processed rows
def checkpoint_cache(func):
    def wrapper(*args, **kwargs):
        in_path, out_path = kwargs["in_path"], kwargs["out_path"]
        checkpoint_file = f"{in_path}_{out_path}.checkpoint"
        try:
            with open(checkpoint_file, "r") as f:
                start_from = int(f.read().strip())
        except FileNotFoundError:
            start_from = 0

        kwargs["start_from"] = start_from
        return func(*args, **kwargs)

    return wrapper


@checkpoint_cache
def process_csv(
    in_path: str,
    out_path: str,
    headless=True,
    limit: Optional[int] = None,
    start_from: Optional[int] = 0,
):
    driver = build_driver(headless=headless)
    rows: List[Dict[str, Any]] = []
    logger.info("Starting From", start_from)

    try:
        with open(in_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            # make sure our output columns exist
            for col in [
                "qpublic_report_url",
                "parcel_number",
                "property_class",
                "property_tax_district",
                "property_value_2025",
                "property_value_2024",
                "property_value_2023",
                "property_value_2022",
                "property_value_2021",
                "property_value_2020",
                "property_acres",
                "property_image",
                "scrape_error",
            ]:
                if col not in fieldnames:
                    fieldnames.append(col)

            # open checkpint file as well
            checkpoint_file = f"{in_path}_{out_path}.checkpoint"
            with open(out_path, "a", newline="", encoding="utf-8") as wf:
                writer = csv.DictWriter(wf, fieldnames=fieldnames)
                if start_from == 0:
                    writer.writeheader()

                for i, row in enumerate(reader):
                    if limit and i >= limit:
                        break
                    if i < start_from:
                        continue
                    try:
                        logger.debug("Processing row %d: %s", i + 1, row)
                        enriched = enrich_row(driver, dict(row))
                    except WebDriverException as e:
                        # Hard browser failure—retry once with a fresh driver
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        driver = build_driver(headless=headless)
                        enriched = enrich_row(driver, dict(row))

                    writer.writerow(enriched)
                    with open(
                        checkpoint_file, "w", encoding="utf-8"
                    ) as cp_file:
                        cp_file.write(str(i + 1) + "\n")
                    # polite jitter between rows
                    time.sleep(random.uniform(0.4, 1.0))
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(
        description="qPublic/Beacon parcel URL scraper (resilient)."
    )
    ap.add_argument(
        "--in", dest="in_path", required=True, help="Input CSV path"
    )
    ap.add_argument(
        "--out", dest="out_path", required=True, help="Output CSV path"
    )
    ap.add_argument(
        "--headed", action="store_true", help="Run with a visible browser"
    )
    ap.add_argument(
        "--limit", type=int, default=None, help="Optional: max rows to process"
    )
    args = ap.parse_args()

    process_csv(
        in_path=args.in_path,
        out_path=args.out_path,
        headless=(not args.headed),
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
