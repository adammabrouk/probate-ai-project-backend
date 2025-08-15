from time import sleep
from parsel import Selector
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pprint import pprint
import os
import pandas as pd

print("Scraper Started...")


# Helper function for extracting values from a Selector object using XPath
def parse(
    html_selector, xpath, get_method="get", comma_join=False, space_join=True
):
    """
    Extracts values from a Selector object using an XPath expression.

    Args:
        html_selector (Selector): The parsel Selector object to extract from.
        xpath (str): The XPath expression to use for extraction.
        get_method (str, optional): Extraction method, either "get" (single value) or "getall" (list). Defaults to "get".
        comma_join (bool, optional): If True and get_method is "getall", join results with commas. Defaults to False.
        space_join (bool, optional): If True and get_method is "getall", join results with spaces. Defaults to True.

    Returns:
        str: The extracted value(s) as a string, or an empty string if not found.
    """
    value = ""
    if get_method == "get":
        value = html_selector.xpath(xpath).get()
        value = (value or "").strip()
    elif get_method == "getall":
        value = html_selector.xpath(xpath).getall()
        if value:
            if comma_join:
                value = " ".join(
                    ", ".join([str(x).strip() for x in value]).split()
                ).strip()
                value = (value or "").strip()
            elif space_join:
                value = " ".join(
                    " ".join([str(x).strip() for x in value]).split()
                ).strip()
                value = (value or "").strip()
        else:
            value = ""
    return value


def bot_setup(headless=False):
    """
    Sets up and returns a Selenium Chrome WebDriver instance with custom options.

    Args:
        headless (bool, optional): Whether to run Chrome in headless mode. Defaults to False.

    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance.
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    if headless:
        options.add_argument("--headless=new")
    driver = webdriver.Chrome(
        service=Service(),
        options=options,
    )
    driver.implicitly_wait(3)
    driver.maximize_window()
    return driver


def send_keys(driver, xpath, keys, wait_time=5):
    """
    Sends keystrokes to a web element located by XPath.

    Args:
        driver (webdriver.Chrome): The Selenium WebDriver instance.
        xpath (str): XPath of the element to send keys to.
        keys (str or Keys): The keys to send.
        wait_time (int, optional): Maximum wait time for the element. Defaults to 5 seconds.
    """
    element = WebDriverWait(driver, wait_time).until(
        EC.presence_of_element_located((By.XPATH, xpath))
    )
    element.send_keys(keys)


def wait_for_element(driver, xpath, wait_time=5):
    """
    Waits until an element specified by XPath is present in the DOM.

    Args:
        driver (webdriver.Chrome): The Selenium WebDriver instance.
        xpath (str): XPath of the element to wait for.
        wait_time (int, optional): Maximum wait time for the element. Defaults to 5 seconds.
    """
    WebDriverWait(driver, wait_time).until(
        EC.presence_of_element_located((By.XPATH, xpath))
    )


def select_county_and_input_dates(driver, county, start_date, end_date):
    """
    Selects a county from the dropdown and inputs the date range in the search form.

    Args:
        driver (webdriver.Chrome): The Selenium WebDriver instance.
        county (str): The county name to select.
        start_date (str): The start date in MM/DD/YYYY format.
        end_date (str): The end date in MM/DD/YYYY format.
    """
    county_dropdown = driver.find_element(
        By.XPATH, '//div[@id="ctl00_cpMain_ddlCounty"]'
    )
    county_dropdown.click()
    sleep(1)
    send_keys(driver, xpath='//div[@id="ctl00_cpMain_ddlCounty"]', keys=county)
    sleep(1)
    send_keys(
        driver, xpath='//div[@id="ctl00_cpMain_ddlCounty"]', keys=Keys.ENTER
    )
    sleep(1)
    send_keys(
        driver,
        xpath='//input[@id="ctl00_cpMain_txtDeceasedStartDate_dateInput"]',
        keys=start_date,
    )
    sleep(1)
    send_keys(
        driver,
        xpath='//input[@id="ctl00_cpMain_txtDeceasedEndDate_dateInput"]',
        keys=end_date,
    )
    sleep(1)
    search_btn = driver.find_element(
        By.XPATH, '//input[@id="ctl00_cpMain_btnSearch_input"]'
    )
    search_btn.click()
    sleep(2)
    return


def wait_for_loading_spinner(driver):
    """
    Waits for the loading spinner to disappear from the page.

    Args:
        driver (webdriver.Chrome): The Selenium WebDriver instance.
    """
    while True:
        temp_html_selector = Selector(text=driver.page_source)
        is_loading_spinner = parse(
            temp_html_selector,
            xpath='//div[@id="cpMain_raLoadingPanel" and not(contains(@style, "display: none;"))]',
        )
        if not is_loading_spinner:
            break
        else:
            sleep(1)
    return


# Get date range input from user
start_date = input("Enter the start date (MM/DD/YYYY): ")
end_date = input("Enter the end date (MM/DD/YYYY): ")

sleep(1)
# Initialize Selenium WebDriver
driver = bot_setup()

# Prepare output directories and file paths
cwd = os.getcwd()
date_output_folder = os.path.join(
    cwd,
    "{}_to_{}_output".format(start_date.replace("/", "-"), end_date).replace(
        "/", "-"
    ),
)
os.makedirs(date_output_folder, exist_ok=True)
records_ouput_folder = os.path.join(date_output_folder, "records")
os.makedirs(records_ouput_folder, exist_ok=True)
results_output_folder = os.path.join(date_output_folder, "results")
os.makedirs(results_output_folder, exist_ok=True)

# Prepare records file
records_filename = "records.csv"
records_filepath = os.path.join(records_ouput_folder, records_filename)
if os.path.exists(records_filepath):
    df = pd.read_csv(records_filepath, dtype=str).fillna("")
    records = df.to_dict(orient="records")
    counties_done = df["County"].unique().tolist()
else:
    records = []
    counties_done = []

# Prepare results file
results_filename = "results.csv"
results_filepath = os.path.join(results_output_folder, results_filename)
if os.path.exists(results_filepath):
    df = pd.read_csv(results_filepath, dtype=str).fillna("")
    results = df.to_dict(orient="records")
    source_urls_done = df["Source URL"].unique().tolist()
else:
    results = []
    source_urls_done = []

# Prepare Excel output path
results_excel_filename = "results.xlsx"
results_excel_filepath = os.path.join(
    results_output_folder, results_excel_filename
)

# Open the search page
driver.get("https://georgiaprobaterecords.com/Estates/SearchEstates.aspx")
wait_for_element(driver, xpath='//div[@id="ctl00_cpMain_ddlCounty"]')
sleep(2)

# Get list of counties from the dropdown
html_selector = Selector(text=driver.page_source)
counties = parse(
    html_selector,
    xpath='//div[@id="ctl00_cpMain_ddlCounty_DropDown"]/div/ul/li[position()>1]/text()',
    get_method="getall",
    space_join=False,
)
counties = [county.strip() for county in counties if county.strip()]

# Loop through each county to collect records
for county_idx, county in enumerate(counties):
    for _ in range(3):  # Retry up to 3 times per county
        try:
            print("=" * 30)
            print(
                "County IDX -> {}/{} | County -> {} | Collecting Records.".format(
                    county_idx + 1, len(counties), county
                )
            )
            if county in counties_done:
                print(
                    "County IDX -> {}/{} | County -> {} | Records Already Collected.".format(
                        county_idx + 1, len(counties), county
                    )
                )
                print("=" * 30)
                continue

            # Reload the search page and input county and dates
            driver.get(
                "https://georgiaprobaterecords.com/Estates/SearchEstates.aspx"
            )
            wait_for_element(
                driver, xpath='//div[@id="ctl00_cpMain_ddlCounty"]'
            )
            sleep(1)
            select_county_and_input_dates(driver, county, start_date, end_date)
            county_records = []
            page_no = 1
            while True:
                wait_for_element(
                    driver, xpath='//table[@class="rgMasterTable"]'
                )
                sleep(1)
                html_selector = Selector(text=driver.page_source)
                rows = html_selector.xpath(
                    '//table[@class="rgMasterTable"]/tbody/tr'
                )
                for row in rows:
                    items = {}
                    items["County"] = county
                    items["Source URL"] = (
                        "https://georgiaprobaterecords.com/Estates/"
                        + parse(row, "./td[1]/a/@href")
                    )
                    items["Case No"] = parse(row, xpath="./td[1]/a/text()")
                    items["Decedent"] = parse(row, xpath="./td[2]/text()")
                    items["Street Address"] = ""
                    items["City"] = parse(row, xpath="./td[3]/text()")
                    items["State"] = parse(row, xpath="./td[4]/text()")
                    items["Zip Code"] = ""
                    items["Death Date"] = parse(row, xpath="./td[5]/text()")
                    county_records.append(items)
                print("-" * 30)
                print(
                    "County IDX -> {}/{} | County -> {} | Page -> {} | Records Collected.".format(
                        county_idx + 1, len(counties), county, page_no
                    )
                )

                # Check if there is a next page
                is_next_page = parse(
                    html_selector,
                    xpath='//td[@class="rgPagerCell NextPrevAndNumeric"]/div[@class="rgWrap rgNumPart"]/a[@class="rgCurrentPage"]/following-sibling::a[1]',
                )
                if is_next_page:
                    next_page_btn = driver.find_element(
                        By.XPATH,
                        '//td[@class="rgPagerCell NextPrevAndNumeric"]/div[@class="rgWrap rgNumPart"]/a[@class="rgCurrentPage"]/following-sibling::a[1]',
                    )
                    next_page_btn.click()
                    wait_for_loading_spinner(driver)
                    sleep(1)
                    page_no += 1
                else:
                    break

            # Save county records to CSV
            records.extend(county_records)
            df = pd.DataFrame(records, dtype=str).fillna("")
            df.to_csv(records_filepath, index=False, encoding="utf-8")
            print("-" * 30)
            print(
                "County IDX -> {}/{} | County -> {} | Records Collected.".format(
                    county_idx + 1, len(counties), county
                )
            )
            print("=" * 30)
            break
        except:
            continue

# Reload all records from file
df = pd.read_csv(records_filepath, dtype=str).fillna("")
records = df.to_dict(orient="records")

# Reload results if exists
results = (
    pd.read_csv(results_filepath, dtype=str)
    .fillna("")
    .to_dict(orient="records")
    if os.path.exists(results_filepath)
    else []
)
done_records = [x["Source URL"] for x in results] if results else []

# Loop through each record to collect detailed info
for rec_idx, rec in enumerate(records):
    source_url = rec["Source URL"]
    if source_url in done_records:
        print("Already Done {}/{}".format(rec_idx + 1, len(records)))
        continue

    for _ in range(3):  # Retry up to 3 times per record
        try:
            driver.get(source_url)
            wait_for_element(driver, xpath='//div[@class="EstateHeader"]')
            sleep(1)
            response = Selector(text=driver.page_source)
            items = rec.copy()
            items["Street Address"] = parse(
                response, xpath='//span[@id="cpMain_lblStreetAddress"]/text()'
            )
            items["Zip Code"] = parse(
                response, xpath='//span[@id="cpMain_lblCityStateZip"]/text()'
            )
            if items["Zip Code"]:
                try:
                    items["Zip Code"] = (
                        items["Zip Code"]
                        .split(",")[-1]
                        .strip()
                        .split()[-1]
                        .strip()
                    )
                except:
                    items["Zip Code"] = ""

            items["Party"] = parse(
                response,
                xpath='//span[@id="cpMain_repParty_lblParty_0"]/text()',
            )
            items["Party Street Address"] = parse(
                response,
                xpath='//span[@id="cpMain_repParty_lblAddress_0"]/text()',
            )
            party_city_state_zip = parse(
                response,
                xpath='//span[@id="cpMain_repParty_lblCityStateZip_0"]/text()',
            )
            if party_city_state_zip:
                try:
                    items["Party City"] = party_city_state_zip.split(",")[
                        0
                    ].strip()
                    items["Party State"] = (
                        party_city_state_zip.split(",")[-1]
                        .strip()
                        .split()[0]
                        .strip()
                    )
                    items["Party Zip Code"] = (
                        party_city_state_zip.split(",")[-1]
                        .strip()
                        .split()[-1]
                        .strip()
                    )
                except:
                    items["Party City"] = ""
                    items["Party State"] = ""
                    items["Party Zip Code"] = ""
            items["Responsibility"] = parse(
                response,
                xpath='//span[@id="cpMain_repParty_lblPartyType_0"]/text()',
            )
            items["Petition Type"] = parse(
                response,
                xpath='//span[@id="cpMain_repFilings_lblFilingTypeDesc_0"]/text()',
            )
            items["Petition Date"] = parse(
                response,
                xpath='//span[@id="cpMain_repFilings_lblFiledDate_0"]/text()',
            )

            # Save results to CSV and Excel
            results.append(items)
            df = pd.DataFrame(results, dtype=str).fillna("")
            df.to_csv(results_filepath, index=False, encoding="utf-8-sig")
            df.to_excel(results_excel_filepath, index=False)
            print("=" * 30)
            pprint(items, sort_dicts=False)
            print("-" * 30)
            print("Done {}/{}".format(rec_idx + 1, len(records)))
            print("=" * 30)
            break
        except:
            continue

# Close the browser and finish
driver.close()
driver.quit()
print("Scraper Finished...")
input("Press enter to exit...")
