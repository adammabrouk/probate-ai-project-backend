# qpublic_basic.py
# pip install selenium webdriver-manager

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options


def start_driver(headless=False):
    opts = Options()
    if headless:
        # Headless can sometimes be blocked; run headful if you hit Cloudflare.
        opts.add_argument("--headless=new")
    # A few tweaks to look more like a real browser session
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--start-maximized")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=opts)


def wait_click(driver, by, value, timeout=20):
    el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
    el.click()
    return el


def select_from_advanced_dropdown(driver, input_id, content_id, query_text, option_locator=None):
    """
    For Schneider's custom dropdowns:
    - Click input
    - Type query_text
    - Click the first visible, not 'no-match' option (or a specific option if option_locator passed)
    """
    # Focus the input and type
    inp = wait_click(driver, By.ID, input_id)
    inp.send_keys(Keys.CONTROL, "a")
    inp.send_keys(query_text)

    # If a specific option is requested (e.g., state 'Georgia'), use it
    if option_locator:
        opt = WebDriverWait(driver, 20).until(EC.element_to_be_clickable(option_locator))
        opt.click()
        return

    # Otherwise pick the first visible match
    content = WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.ID, content_id)))
    # Schneider marks filtered-out options with 'no-match'. We pick the first that is not 'no-match' and not the blank 'all-option'.
    candidates = WebDriverWait(driver, 20).until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, f"#{content_id} .dropdown-option:not(.no-match):not(.all-option)")
        )
    )
    # Click the first clickable candidate
    for el in candidates:
        try:
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable(el)).click()
            break
        except Exception:
            continue


def go_qpublic(county_query="Douglas"):
    driver = start_driver(headless=False)
    wait = WebDriverWait(driver, 25)

    try:
        driver.get("https://qpublic.schneidercorp.com/")

        # Ensure the "Local" tab is active (it usually is)
        try:
            wait_click(driver, By.ID, "btnLocal")
        except Exception:
            pass  # Already active

        # --- State = Georgia ---
        # Open state dropdown, type 'Georgia', click the Georgia option
        select_from_advanced_dropdown(
            driver,
            input_id="stateMenuButton",
            content_id="stateMenuContent",
            query_text="Georgia",
            option_locator=(By.CSS_SELECTOR, "#stateMenuContent #state-option-Georgia")
        )

        # --- County: type and choose the FIRST visible match ---
        # Example: "Douglas" -> selects the first result (e.g., "Douglas County, GA")
        select_from_advanced_dropdown(
            driver,
            input_id="areaMenuButton",
            content_id="areaMenuContent",
            query_text=county_query
        )

        # Click "Property Search"
        prop_link = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//h3[normalize-space()='Property Search']/ancestor::a")
            )
        )
        prop_link.click()

        # Optional: confirm navigation
        wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "div.modal.in[aria-label='Terms and Conditions'], div.modal.in"))
        )

        # Find the "Agree" link (Bootstrap uses <a data-dismiss="modal">)
        agree = driver.find_element(
            By.XPATH, "//div[contains(@class,'modal') and contains(@class,'in')]//a[@data-dismiss='modal' and normalize-space()='Agree']"
        )

        # Click via JS to avoid any backdrop/overlay issues
        driver.execute_script("arguments[0].click();", agree)

        # Wait until the modal is gone and page is unblocked
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.modal.in")))
        wait.until(lambda d: "modal-open" not in d.find_element(By.TAG_NAME, "body").get_attribute("class"))
        print("Terms popup accepted.")

        # Keep the window a bit if you’re watching it
        time.sleep(20)

    finally:
        # Close only if you want to end the session automatically.
        # Comment this out while you’re developing to inspect the page.
        driver.quit()


if __name__ == "__main__":
    # Change the county query as needed; the script will pick the first visible match.
    go_qpublic(county_query="Douglas")    