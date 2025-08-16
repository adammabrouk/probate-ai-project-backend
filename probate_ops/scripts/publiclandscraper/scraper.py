#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import csv
import time
import random
import argparse
import logging
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

HOME_URL = "https://qpublic.schneidercorp.com/"
DEFAULT_TIMEOUT = 35

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
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


def build_driver(headless=True) -> webdriver.Chrome:
    chrome_opts = Options()
    if headless:
        chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--window-size=1400,1000")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    chrome_opts.add_argument("--disable-blink-features=AutomationControlled")
    chrome_opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_opts.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=chrome_opts)
    driver.set_page_load_timeout(60)
    return driver


def wait_any_of(wait: WebDriverWait, locators: List[tuple]) -> None:
    wait.until(EC.any_of(*[EC.presence_of_element_located(l) for l in locators]))


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
    state_btn = wait.until(EC.presence_of_element_located((By.ID, "stateMenuButton")))
    logger.info("Clicking State dropdown")
    js_click(driver, state_btn)
    time.sleep(0.2)

    # Find the state option by data-name (e.g., "Georgia")
    state_option = wait.until(
        EC.presence_of_element_located(
            (By.XPATH, f"//div[@id='stateMenuContent']//div[@role='option' and @data-name='{ctx.state}']")
        )
    )
    logger.info("Selecting State: %s", ctx.state)
    js_click(driver, state_option)

    # Open Area/County drop and pick
    area_btn = wait.until(EC.presence_of_element_located((By.ID, "areaMenuButton")))
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
                % repr(f"{ctx.county} County")
            )
        )
    )
    logger.info("Selecting Area/County: %s", ctx.county)
    js_click(driver, area_option)

    # Read selected option to capture AppID
    selected = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "#areaMenuContent .dropdown-option[aria-selected='true']")
        )
    )
    logger.info("Selected Area/County: %s", selected.text)
    ctx.appid = selected.get_attribute("data-appid")


def navigate_into_app(driver, ctx: RowCtx):
    """Get into the county application.
    Prefers Quickstart 'Search Records' tile; falls back to direct Application.aspx?AppID=..."""
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)

    # Wait for homepage bits which may render slowly
    try:
        logger.info("Waiting for homepage elements to load")
        wait_any_of(wait, [
            (By.ID, "quickstartList"),
            (By.CSS_SELECTOR, "iframe[src*='Application.aspx']"),
            (By.XPATH, "//a[contains(@href,'Application.aspx') and contains(@href,'AppID=')]"),
        ])
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
            "//div[@id='quickstartList']//a[.//h3[normalize-space()='Search Records']]"
        )
        href = link.get_attribute("href")
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
    agree_btn = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//a[normalize-space()='Agree']"))
    )
    driver.execute_script("arguments[0].click();", agree_btn)


def open_search_panel(driver):
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
            (By.XPATH, "//input[contains(@id,'Address') or contains(@placeholder,'Address')]")
        )
    )


def submit_address_and_capture_parcel(driver, raw_address: str) -> str:
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    # addr = normalize_address_for_qpublic(raw_address)
    addr = raw_address
    field = driver.find_element(
        By.XPATH, "//input[contains(@id,'Address') or contains(@placeholder,'Address')]"
    )
    field.clear()
    field.send_keys(addr)
    field.send_keys(Keys.ENTER)

    # Wait for one of: parcel links (grid), parcel detail, or a no-results message
    try:
        wait.until(EC.any_of(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='KeyValue=']")),
            EC.presence_of_element_located((By.CSS_SELECTOR, "a#lnkParcel, a[href*='Parcel.aspx']")),
            EC.presence_of_element_located((By.XPATH, "//*[contains(.,'No results') or contains(.,'No records')]")),
        ))
    except TimeoutException:
        # Some apps use loading overlays—if present, wait for them to vanish briefly, then re-check
        try:
            WebDriverWait(driver, 8).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".loading, .spinner, .k-loading-mask"))
            )
        except TimeoutException:
            pass

    # Case 1: grid with links
    links = driver.find_elements(By.CSS_SELECTOR, "a[href*='KeyValue=']")
    if links:
        href = links[0].get_attribute("href")
        # Open it in the top window to get a stable URL
        driver.execute_script("window.top.location = arguments[0];", href)
        # We switched window context; need to wait to load again
        WebDriverWait(driver, DEFAULT_TIMEOUT).until(EC.url_contains("KeyValue="))
        return driver.current_url

    # Case 2: already on a parcel detail
    if ("KeyValue=" in driver.current_url) or ("PageTypeID=4" in driver.current_url):
        return driver.current_url

    # Case 3: try a looser query (number + street name, no suffix)
    m = re.match(r"^\s*(\d+)\s+([A-Z0-9\s\.\-']+)$", addr)
    if m:
        pattern = r"\b(AVE|AV|ST|RD|DR|LN|CT|HWY|PKWY|CIR|TRL|TER|WAY|BLVD)\b"
        loose = f"{m.group(1)} {re.sub(pattern, '', m.group(2)).strip()}"
        field = driver.find_element(
            By.XPATH, "//input[contains(@id,'Address') or contains(@placeholder,'Address')]"
        )
        field.clear()
        field.send_keys(loose)
        field.send_keys(Keys.ENTER)

        try:
            wait.until(EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='KeyValue=']")),
                EC.presence_of_element_located((By.XPATH, "//*[contains(.,'No results') or contains(.,'No records')]")),
            ))
        except TimeoutException:
            pass

        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='KeyValue=']")
        if links:
            href = links[0].get_attribute("href")
            driver.execute_script("window.top.location = arguments[0];", href)
            WebDriverWait(driver, DEFAULT_TIMEOUT).until(EC.url_contains("KeyValue="))
            return driver.current_url

    raise RuntimeError("results: no parcel links; address not found")


def enrich_row(driver, row: Dict[str, Any]) -> Dict[str, Any]:
    """Main per-row routine with granular error logging."""
    # choose the best address input column available
    addr = row.get("Street Address") or row.get("pk_street_address") or row.get("owner_address_full") or ""
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
        row["scrape_error"] = f"after state/county select: {type(e).__name__}: {str(e)[:800]}"
        return row

    try:
        navigate_into_app(driver, ctx)
    except Exception as e:
        row["scrape_error"] = f"navigation into app: {type(e).__name__}: {str(e)[:800]}"
        return row

    try:
        # enter iframe (most Beacon apps)
        switch_into_app_frame(driver)
    except Exception as e:
        # Not fatal—some apps have no visible iframe (rare). Try to proceed.
        pass

    try:
        open_search_panel(driver)
    except Exception as e:
        row["scrape_error"] = f"inside app: could not open search panel: {type(e).__name__}: {str(e)[:800]}"
        return row

    try:
        url = submit_address_and_capture_parcel(driver, ctx.addr)
        row["qpublic_report_url"] = url
        row["scrape_error"] = ""
    except Exception as e:
        row["qpublic_report_url"] = ""
        row["scrape_error"] = f"{type(e).__name__}: {str(e)[:800]}"

    # add helpful debug breadcrumbs
    if ctx.appid:
        row["qpublic_appid"] = ctx.appid
    if ctx.visited_url:
        row["qpublic_visited_url"] = ctx.visited_url

    return row


def process_csv(in_path: str, out_path: str, headless=True, limit: Optional[int] = None):
    driver = build_driver(headless=headless)
    rows: List[Dict[str, Any]] = []

    try:
        with open(in_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            # make sure our output columns exist
            for col in ["qpublic_report_url", "scrape_error", "qpublic_appid", "qpublic_visited_url", "normalized_address_tried"]:
                if col not in fieldnames:
                    fieldnames.append(col)

            with open(out_path, "w", newline="", encoding="utf-8") as wf:
                writer = csv.DictWriter(wf, fieldnames=fieldnames)
                writer.writeheader()

                for i, row in enumerate(reader):
                    if limit and i >= limit:
                        break
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
                    # polite jitter between rows
                    time.sleep(random.uniform(0.4, 1.0))
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description="qPublic/Beacon parcel URL scraper (resilient).")
    ap.add_argument("--in", dest="in_path", required=True, help="Input CSV path")
    ap.add_argument("--out", dest="out_path", required=True, help="Output CSV path")
    ap.add_argument("--headed", action="store_true", help="Run with a visible browser")
    ap.add_argument("--limit", type=int, default=None, help="Optional: max rows to process")
    args = ap.parse_args()

    process_csv(args.in_path, args.out_path, headless=(not args.headed), limit=args.limit)


if __name__ == "__main__":
    main()
