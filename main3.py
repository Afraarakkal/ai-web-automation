import os
import time
from collections import deque
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

import google.generativeai as genai

# --- Configuration ---
# NO LONGER HARDCODED LOGIN DETAILS - These will be user input
# BASE_URL will now be derived from the START_URL
# USERNAME, PASSWORD, LOGIN_URL, DASHBOARD_URL_PART and their locators are removed.

# AI Model and Report
GEMINI_MODEL = "gemini-1.5-flash" # Or "gemini-1.5-pro" if you have access and need more capability
REPORT_FILE = "web_test_report_general.txt" # Changed report file name
SCREENSHOT_DIR = "screenshots_general_test" # Directory to save screenshots

# Crawler Settings
MAX_PAGES_TO_VISIT = 100 # Limit the number of pages to prevent infinite crawling on large sites
TEST_FORMS_ON_EACH_PAGE = True # Set to False if you want to skip form testing
CLICK_EXTERNAL_LINKS = False # Set to True if you want to test external links (use with caution!)

# --- Ensure Screenshot Directory Exists ---
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# --- Configure Google Gemini API ---
try:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
except KeyError:
    print("Error: GEMINI_API_KEY environment variable not set. Please set it.")
    exit()

# --- Initialize Gemini Model ---
try:
    gemini_model = genai.GenerativeModel(GEMINI_MODEL)
except Exception as e:
    print(f"Error initializing Gemini model '{GEMINI_MODEL}': {e}")
    print("Please check if the model is available and your API key is correct.")
    exit()

# --- WebDriver Setup ---
def setup_driver():
    """Sets up and returns a Selenium WebDriver instance."""
    try:
        print("Setting up Chrome WebDriver...")
        service = ChromeService(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        # options.add_argument("--headless") # Uncomment to run in headless mode (no visible browser)
        options.add_argument("--start-maximized")
        driver = webdriver.Chrome(service=service, options=options)
        print("WebDriver setup complete.")
        return driver
    except Exception as e:
        print(f"Error setting up WebDriver: {e}")
        print("Ensure you have Chrome installed and webdriver-manager is configured correctly.")
        exit()

# --- AI Analysis Function ---
def analyze_content_with_ai(content: str, prompt_suffix: str) -> str:
    """Sends content to Gemini for analysis."""
    MAX_CONTENT_LENGTH = 15000 # Adjust based on model's context window and your needs (approx 15k chars for flash, more for pro)
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH] + "\n... [Content Truncated] ..."

    full_prompt = f"Analyze the following web page content. {prompt_suffix}\n\nContent:\n{content}"
    try:
        print(f"Sending content for AI analysis (prompt len: {len(full_prompt)})...")
        response = gemini_model.generate_content(full_prompt)
        if response.parts and response.parts[0].text:
            return response.parts[0].text
        else:
            return "AI analysis completed, but no text response was generated."
    except Exception as e:
        return f"AI analysis failed: {e}. This might be due to API issues, rate limits, or content too large."

# --- Web Testing Logic ---
def run_web_test():
    driver = None
    report_content = []
    visited_urls = set()
    urls_to_visit = deque()
    forms_tested = set() # To track forms by their unique properties (e.g., action attribute)

    # --- Get User Input for Testing ---
    print("\n--- Configure Web Test ---")
    start_url = input("Enter the STARTING URL for the web test (e.g., https://example.com):\n> ").strip()
    if not start_url.startswith("http://") and not start_url.startswith("https://"):
        start_url = "https://" + start_url # Prepend https if not present

    # Derive BASE_URL from start_url for internal link checking
    parsed_start_url = urlparse(start_url)
    base_url = f"{parsed_start_url.scheme}://{parsed_start_url.netloc}"

    main_ai_prompt = input("Enter the PRIMARY AI prompt for analysis on ALL visited pages (e.g., 'Check for broken links, missing content, layout issues, and overall relevance. Identify any functional anomalies or errors.'). This will guide all AI analysis:\n> ")
    print("--- Test Configuration Complete ---\n")

    try:
        driver = setup_driver()
        report_content.append(f"--- Starting AI Web Test ---")
        report_content.append(f"Timestamp: {time.ctime()}")
        report_content.append(f"Starting URL: {start_url}")
        report_content.append(f"Base Domain for Crawling: {base_url}")
        report_content.append(f"AI Analysis Prompt: '{main_ai_prompt}'")
        report_content.append(f"Gemini Model Used: {GEMINI_MODEL}\n")

        # Start crawling from the user-provided URL
        urls_to_visit.append(start_url)
        page_count = 0

        while urls_to_visit and page_count < MAX_PAGES_TO_VISIT:
            current_url = urls_to_visit.popleft()

            if current_url in visited_urls:
                continue # Skip already visited URLs

            # Check if the URL is within the base domain (unless external links are allowed)
            if not CLICK_EXTERNAL_LINKS and urlparse(current_url).netloc != urlparse(base_url).netloc:
                report_content.append(f"Skipping external URL: {current_url}")
                continue

            visited_urls.add(current_url)
            page_count += 1
            report_content.append(f"\n--- Testing Page {page_count}: {current_url} ---")
            print(f"Testing Page {page_count}: {current_url}")

            try:
                driver.get(current_url)
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body"))) # Wait for body to load
                time.sleep(3) # Give some buffer for JS to render

                screenshot_path = os.path.join(SCREENSHOT_DIR, f"page_{page_count}_{os.path.basename(urlparse(current_url).path).replace('/', '_').replace('.', '_') or 'index'}.png")
                driver.save_screenshot(screenshot_path)
                report_content.append(f"Screenshot saved: {screenshot_path}")

                page_source = driver.page_source
                report_content.append("\n--- AI Content Analysis ---")
                ai_analysis_page = analyze_content_with_ai(
                    page_source,
                    main_ai_prompt # Using the single user-defined prompt
                )
                report_content.append(ai_analysis_page)

                # --- Find and Queue New Links ---
                links = driver.find_elements(By.TAG_NAME, "a")
                for link in links:
                    try:
                        href = link.get_attribute("href")
                        if href: # Ensure href is not None
                            full_url = urljoin(current_url, href)
                            # Basic check to ensure it's a valid HTTP/HTTPS URL and not a fragment
                            if (full_url.startswith("http://") or full_url.startswith("https://")) and \
                               urlparse(full_url).fragment == '' and \
                               (CLICK_EXTERNAL_LINKS or urlparse(full_url).netloc == urlparse(base_url).netloc):
                                # Remove query parameters for simpler URL tracking, to avoid re-visiting same page with different params
                                url_without_params = urlparse(full_url)._replace(query='').geturl()
                                if url_without_params not in visited_urls and url_without_params not in urls_to_visit:
                                    urls_to_visit.append(url_without_params)
                    except StaleElementReferenceException:
                        continue # Element no longer attached to the DOM, skip it
                    except Exception as link_e:
                        report_content.append(f"WARN: Error processing link on {current_url}: {link_e}")


                # --- Test Forms on the Page (Optional but recommended) ---
                if TEST_FORMS_ON_EACH_PAGE:
                    forms = driver.find_elements(By.TAG_NAME, "form")
                    for form_index, form in enumerate(forms):
                        # Create a unique identifier for the form
                        form_identifier = (current_url, form.get_attribute("action"), form.get_attribute("id") or f"form_{form_index}")
                        if form_identifier in forms_tested:
                            continue # Skip already tested forms
                        forms_tested.add(form_identifier)

                        report_content.append(f"\n--- Testing Form: {form_identifier[2]} on {current_url} ---")
                        try:
                            # Find form elements only within the current form to avoid confusion
                            inputs = form.find_elements(By.TAG_NAME, "input")
                            textareas = form.find_elements(By.TAG_NAME, "textarea")
                            selects = form.find_elements(By.TAG_NAME, "select")

                            for input_field in inputs:
                                if input_field.is_displayed() and input_field.is_enabled():
                                    input_type = input_field.get_attribute("type")
                                    if input_type in ["text", "search", "email", "url", "tel", "password"]:
                                        input_field.send_keys("test_data")
                                    elif input_type == "checkbox":
                                        if not input_field.is_selected():
                                            input_field.click()
                                    elif input_type == "radio":
                                        input_field.click() # Clicks if not selected

                            for textarea in textareas:
                                if textarea.is_displayed() and textarea.is_enabled():
                                    textarea.send_keys("This is a test comment.")

                            for select in selects:
                                if select.is_displayed() and select.is_enabled():
                                    try:
                                        # Try to select the first visible option
                                        options = select.find_elements(By.TAG_NAME, "option")
                                        if options:
                                            selected = False
                                            for opt in options:
                                                if opt.is_enabled() and opt.is_displayed():
                                                    opt.click()
                                                    selected = True
                                                    break
                                            if not selected:
                                                report_content.append(f"WARN: No clickable options found for select element in form {form_identifier[2]}.")
                                        else:
                                            report_content.append(f"WARN: No options found for select element in form {form_identifier[2]}.")
                                    except Exception as select_e:
                                        report_content.append(f"ERROR: Could not interact with select in form {form_identifier[2]}: {select_e}")

                            # Attempt to submit the form
                            submit_button = None
                            try:
                                # Prioritize type='submit' buttons
                                submit_button = form.find_element(By.CSS_SELECTOR, "input[type='submit'], button[type='submit']")
                            except NoSuchElementException:
                                try: # Fallback: Find any button within the form
                                    submit_button = form.find_element(By.TAG_NAME, "button")
                                except NoSuchElementException:
                                    report_content.append(f"WARN: No explicit submit button found for form {form_identifier[2]}. Skipping submission.")

                            if submit_button and submit_button.is_displayed() and submit_button.is_enabled():
                                report_content.append(f"Attempting to submit form: {form_identifier[2]}")
                                current_url_before_submit = driver.current_url
                                submit_button.click()
                                time.sleep(5) # Wait for form submission to process

                                # AI analysis of page after form submission
                                report_content.append("\n--- AI Analysis: After Form Submission ---")
                                ai_analysis_form_submit = analyze_content_with_ai(
                                    driver.page_source,
                                    main_ai_prompt # Using the general prompt for form submission analysis
                                )
                                report_content.append(ai_analysis_form_submit)

                                if driver.current_url == current_url_before_submit:
                                    report_content.append(f"NOTE: Page did not redirect after submitting form {form_identifier[2]}. Check for AJAX validation or same-page updates.")
                            else:
                                report_content.append(f"WARN: Could not find clickable submit button for form {form_identifier[2]}.")

                        except Exception as form_e:
                            report_content.append(f"ERROR: Failed to test form {form_identifier[2]} due to: {form_e}")
                        finally:
                            # After testing a form, navigate back to the original page to continue crawling
                            # if the URL changed due to submission, or stay if it's an AJAX form.
                            if driver.current_url != current_url: # If form submission changed URL, add new URL to queue
                                # Remove query parameters for simpler URL tracking
                                new_url_without_params = urlparse(driver.current_url)._replace(query='').geturl()
                                if new_url_without_params not in visited_urls and new_url_without_params not in urls_to_visit:
                                    urls_to_visit.append(new_url_without_params)
                            driver.get(current_url) # Return to the page being tested to find other links/forms
                            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                            time.sleep(2)


            except TimeoutException:
                report_content.append(f"FAIL: Page {current_url} did not load within timeout.")
                driver.save_screenshot(os.path.join(SCREENSHOT_DIR, f"page_load_timeout_{page_count}.png"))
            except Exception as e:
                report_content.append(f"ERROR: An unexpected error occurred while testing {current_url}: {e}")
                driver.save_screenshot(os.path.join(SCREENSHOT_DIR, f"page_error_{page_count}.png"))

        if page_count >= MAX_PAGES_TO_VISIT:
            report_content.append(f"\n--- Maximum pages to visit ({MAX_PAGES_TO_VISIT}) reached. Stopping traversal. ---")
        report_content.append("\n--- Automated Web Test Complete ---")
        report_content.append(f"Total unique pages visited: {len(visited_urls)}")
        report_content.append(f"Total forms attempted: {len(forms_tested)}")


    except Exception as e:
        report_content.append(f"\n--- FATAL ERROR DURING ENTIRE TEST RUN: {e} ---")
    finally:
        if driver:
            print("Closing WebDriver...")
            driver.quit()
        # --- Generate Report ---
        print(f"\nWriting report to {REPORT_FILE}...")
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            for line in report_content:
                f.write(line + "\n")
        print(f"\nWeb test completed. Report saved to {REPORT_FILE}")
        print("Please review the report for AI insights and test outcomes and check the 'screenshots_general_test' directory.")

if __name__ == "__main__":
    run_web_test()