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
# IMPORTANT: REPLACE THESE WITH YOUR WEBSITE'S ACTUAL VALUES AND TEST STRATEGY 
BASE_URL = "https://the-internet.herokuapp.com" # Updated base URL
LOGIN_URL = f"{BASE_URL}/login" # The URL of your website's login page
# A part of the URL you expect after successful login (e.g., /home, /dashboard, /profile)
DASHBOARD_URL_PART = "/secure"
USERNAME = "tomsmith" # A valid test username for your website
PASSWORD = "SuperSecretPassword!" # The password for the test user

# Common element locators for login (adjust based on your website's HTML)
USERNAME_FIELD_LOCATOR = (By.NAME, "username") # Example: <input name="username">
PASSWORD_FIELD_LOCATOR = (By.NAME, "password") # Example: <input name="password">
LOGIN_BUTTON_LOCATOR = (By.CSS_SELECTOR, "button[type='submit']") # Example: <button type="submit">

# AI Model and Report
GEMINI_MODEL = "gemini-1.5-flash" # Or "gemini-1.5-pro" if you have access and need more capability
REPORT_FILE = "web_test_report_full.txt"
SCREENSHOT_DIR = "screenshots" # Directory to save screenshots

# Crawler Settings
MAX_PAGES_TO_VISIT = 10 # Limit the number of pages to prevent infinite crawling on large sites
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

    # --- Get AI Prompts from User Input ---
    print("\n--- Configure AI Prompts ---")
    login_fail_prompt = input("Enter prompt for AI analysis on a FAILED login page (e.g., 'Identify error messages, missing fields, or unexpected redirects'):\n> ")
    dashboard_prompt = input("Enter prompt for AI analysis on the DASHBOARD/POST-LOGIN page (e.g., 'Verify presence of user details, navigation links, and overall page health'):\n> ")
    page_traversal_prompt = input("Enter prompt for AI analysis on EACH CRAWLED page (e.g., 'Check for broken links, missing content, layout issues, and overall relevance'):\n> ")
    form_submit_prompt = input("Enter prompt for AI analysis AFTER FORM SUBMISSION (e.g., 'Look for success messages, validation errors, or unexpected redirects'):\n> ")
    print("--- AI Prompts Configured ---\n")


    try:
        driver = setup_driver()
        report_content.append(f"--- Starting AI Web Test ---")
        report_content.append(f"Timestamp: {time.ctime()}")
        report_content.append(f"Base URL: {BASE_URL}")
        report_content.append(f"Gemini Model Used: {GEMINI_MODEL}\n")

        # --- Test Case 1: User Login ---
        report_content.append("--- Test Case: User Login ---")
        report_content.append(f"Navigating to Login Page: {LOGIN_URL}...")
        driver.get(LOGIN_URL)
        driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "login_page_initial.png"))

        login_successful = False
        try:
            print("Waiting for login elements...")
            username_field = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(USERNAME_FIELD_LOCATOR)
            )
            password_field = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(PASSWORD_FIELD_LOCATOR)
            )
            login_button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(LOGIN_BUTTON_LOCATOR)
            )

            report_content.append(f"Found login elements. Entering credentials...")
            username_field.send_keys(USERNAME)
            password_field.send_keys(PASSWORD)

            login_button.click()
            report_content.append("Clicked Login button. Waiting for post-login page...")
            time.sleep(5) # Give some buffer for client-side processing/redirect

            # --- Post-Login Verification ---
            try:
                if DASHBOARD_URL_PART in driver.current_url:
                    report_content.append(f"SUCCESS: Login appears successful based on URL: {driver.current_url}")
                    login_successful = True
                else:
                    # Try to find a unique element on the dashboard if URL check is not enough
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.ID, "flash")) # For herokuapp, this is the success message
                    )
                    report_content.append(f"SUCCESS: Login appears successful based on dashboard element on {driver.current_url}")
                    login_successful = True

                # AI analysis of the dashboard page using user-provided prompt
                driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "dashboard_page.png"))
                dashboard_source = driver.page_source
                report_content.append("\n--- AI Analysis: Dashboard Page ---")
                ai_analysis_dashboard = analyze_content_with_ai(
                    dashboard_source,
                    dashboard_prompt # Using user-defined prompt
                )
                report_content.append(ai_analysis_dashboard)
                urls_to_visit.append(driver.current_url) # Start crawling from dashboard

            except TimeoutException:
                report_content.append(f"FAIL: Login did not lead to expected post-login page or element within timeout. Current URL: {driver.current_url}")
                driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "login_failed_post_click.png"))
                failed_login_source = driver.page_source
                report_content.append("\n--- AI Analysis: Failed Login Page ---")
                ai_analysis_failed_login = analyze_content_with_ai(
                    failed_login_source,
                    login_fail_prompt # Using user-defined prompt
                )
                report_content.append(ai_analysis_failed_login)

        except (TimeoutException, NoSuchElementException, Exception) as e:
            report_content.append(f"FAIL: Critical error during login interaction: {type(e).__name__} - {e}")
            report_content.append("This likely means login elements were not found or an unexpected error occurred before interaction.")
            driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "login_elements_not_found.png"))
            login_successful = False

        # --- Automated Page Traversal and Testing ---
        if login_successful:
            report_content.append("\n--- Starting Automated Page Traversal ---")
            page_count = 0

            while urls_to_visit and page_count < MAX_PAGES_TO_VISIT:
                current_url = urls_to_visit.popleft()

                if current_url in visited_urls:
                    continue # Skip already visited URLs

                # Check if the URL is within the base domain (unless external links are allowed)
                if not CLICK_EXTERNAL_LINKS and urlparse(current_url).netloc != urlparse(BASE_URL).netloc:
                    report_content.append(f"Skipping external URL: {current_url}")
                    continue

                visited_urls.add(current_url)
                page_count += 1
                report_content.append(f"\n--- Testing Page {page_count}: {current_url} ---")
                print(f"Testing Page {page_count}: {current_url}")

                try:
                    driver.get(current_url)
                    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body"))) # Wait for body to load
                    time.sleep(2) # Give some buffer for JS to render

                    screenshot_path = os.path.join(SCREENSHOT_DIR, f"page_{page_count}_{os.path.basename(urlparse(current_url).path).replace('/', '_') or 'index'}.png")
                    driver.save_screenshot(screenshot_path)
                    report_content.append(f"Screenshot saved: {screenshot_path}")

                    page_source = driver.page_source
                    report_content.append("\n--- AI Content Analysis ---")
                    ai_analysis_page = analyze_content_with_ai(
                        page_source,
                        page_traversal_prompt # Using user-defined prompt
                    )
                    report_content.append(ai_analysis_page)

                    # --- Find and Queue New Links ---
                    links = driver.find_elements(By.TAG_NAME, "a")
                    for link in links:
                        try:
                            href = link.get_attribute("href")
                            if href: # Ensure href is not None
                                # Resolve relative URLs
                                full_url = urljoin(current_url, href)
                                # Basic check to ensure it's a valid HTTP/HTTPS URL
                                if full_url.startswith("http://") or full_url.startswith("https://"):
                                    # Ensure it's within the base domain or external links are allowed
                                    if (CLICK_EXTERNAL_LINKS or urlparse(full_url).netloc == urlparse(BASE_URL).netloc) and \
                                       full_url not in visited_urls and full_url not in urls_to_visit:
                                        urls_to_visit.append(full_url)
                        except StaleElementReferenceException:
                            # Element no longer attached to the DOM, skip it
                            continue
                        except Exception as link_e:
                            report_content.append(f"WARN: Error processing link on {current_url}: {link_e}")


                    # --- Test Forms on the Page (Optional but recommended) ---
                    if TEST_FORMS_ON_EACH_PAGE:
                        forms = driver.find_elements(By.TAG_NAME, "form")
                        for form_index, form in enumerate(forms):
                            # Create a unique identifier for the form
                            form_identifier = (current_url, form.get_attribute("action"), form.get_attribute("id") or form_index)
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
                                                # Click the first non-disabled option, or the first one
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
                                        form_submit_prompt # Using user-defined prompt
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
                                # For comprehensive crawling, it's often safer to go back to the current_url
                                # unless the submission explicitly leads to a new, crawlable page.
                                if driver.current_url != current_url: # If form submission changed URL, add new URL to queue
                                    if driver.current_url not in visited_urls and driver.current_url not in urls_to_visit:
                                        urls_to_visit.append(driver.current_url)
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
            report_content.append("\n--- Automated Page Traversal Complete ---")
            report_content.append(f"Total pages visited: {len(visited_urls)}")
            report_content.append(f"Total forms tested: {len(forms_tested)}")

        else:
            report_content.append("\n--- Skipping automated page traversal as login failed. ---")

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
        print("Please review the report for AI insights and test outcomes and check the 'screenshots' directory.")

if __name__ == "__main__":
    run_web_test()