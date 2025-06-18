import os
import time
from collections import deque
from urllib.parse import urljoin, urlparse
# Playwright specific imports
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Page, Locator

import google.generativeai as genai

# --- Configuration ---
# AI Model and Report
GEMINI_MODEL = "gemini-1.5-flash"
REPORT_FILE = "web_test_report_playwright_buttons.txt" # Changed report file name
SCREENSHOT_DIR = "screenshots_playwright_buttons" # Directory to save screenshots

# Crawler Settings
MAX_PAGES_TO_VISIT = 10
TEST_FORMS_ON_EACH_PAGE = False # Simplified for this example, can be re-enabled
CLICK_BUTTONS = True # <-- NEW: Set to True to enable button clicking
CLICK_EXTERNAL_LINKS = False

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

# --- AI Analysis Function ---
def analyze_content_with_ai(content: str, prompt_suffix: str) -> str:
    """Sends content to Gemini for analysis."""
    MAX_CONTENT_LENGTH = 15000
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
def run_web_test_playwright():
    report_content = []
    visited_urls = set()
    urls_to_visit = deque()

    # --- Get User Input for Testing ---
    print("\n--- Configure Web Test (Playwright) ---")
    start_url = input("Enter the STARTING URL for the web test (e.g., https://example.com):\n> ").strip()
    if not start_url.startswith("http://") and not start_url.startswith("https://"):
        start_url = "https://" + start_url # Prepend https if not present

    parsed_start_url = urlparse(start_url)
    base_url = f"{parsed_start_url.scheme}://{parsed_start_url.netloc}"

    main_ai_prompt = input("Enter the PRIMARY AI prompt for analysis on ALL visited pages (e.g., 'Check for broken links, missing content, layout issues, and overall relevance. Identify any functional anomalies or errors.'). This will guide all AI analysis:\n> ")
    print("--- Test Configuration Complete ---\n")

    # Playwright Context Manager
    with sync_playwright() as p:
        # You can choose 'chromium', 'firefox', or 'webkit'
        # For visible browser, set headless=False
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_viewport_size({"width": 1280, "height": 800}) # Set a consistent viewport

        report_content.append(f"--- Starting AI Web Test (Playwright) ---")
        report_content.append(f"Timestamp: {time.ctime()}")
        report_content.append(f"Starting URL: {start_url}")
        report_content.append(f"Base Domain for Crawling: {base_url}")
        report_content.append(f"AI Analysis Prompt: '{main_ai_prompt}'")
        report_content.append(f"Gemini Model Used: {GEMINI_MODEL}\n")

        urls_to_visit.append(start_url)
        page_count = 0

        while urls_to_visit and page_count < MAX_PAGES_TO_VISIT:
            current_url = urls_to_visit.popleft()

            # Clean URL for tracking (remove fragments and query params for basic crawl)
            cleaned_current_url = urlparse(current_url)._replace(query='', fragment='').geturl()
            if cleaned_current_url in visited_urls:
                continue

            if not CLICK_EXTERNAL_LINKS and urlparse(cleaned_current_url).netloc != urlparse(base_url).netloc:
                report_content.append(f"Skipping external URL: {cleaned_current_url}")
                continue

            visited_urls.add(cleaned_current_url)
            page_count += 1
            report_content.append(f"\n--- Testing Page {page_count}: {cleaned_current_url} ---")
            print(f"Testing Page {page_count}: {cleaned_current_url}")

            try:
                page.goto(cleaned_current_url, wait_until="domcontentloaded", timeout=30000) # 30 sec timeout
                time.sleep(2) # Give some buffer for JS to render

                screenshot_filename = os.path.basename(urlparse(cleaned_current_url).path).replace('/', '_').replace('.', '_') or 'index'
                screenshot_path = os.path.join(SCREENSHOT_DIR, f"page_{page_count}_{screenshot_filename}.png")
                page.screenshot(path=screenshot_path)
                report_content.append(f"Screenshot saved: {screenshot_path}")

                page_source = page.content() # Get page source
                report_content.append("\n--- AI Content Analysis ---")
                ai_analysis_page = analyze_content_with_ai(
                    page_source,
                    main_ai_prompt
                )
                report_content.append(ai_analysis_page)

                # --- Find and Queue New Links ---
                links = page.locator("a").all()
                for link_locator in links:
                    try:
                        href = link_locator.get_attribute("href")
                        if href:
                            full_url = urljoin(cleaned_current_url, href)
                            if (full_url.startswith("http://") or full_url.startswith("https://")) and \
                               urlparse(full_url).fragment == '' and \
                               (CLICK_EXTERNAL_LINKS or urlparse(full_url).netloc == urlparse(base_url).netloc):
                                cleaned_full_url = urlparse(full_url)._replace(query='').geturl()
                                if cleaned_full_url not in visited_urls and cleaned_full_url not in urls_to_visit:
                                    urls_to_visit.append(cleaned_full_url)
                    except PlaywrightTimeoutError:
                        continue
                    except Exception as link_e:
                        report_content.append(f"WARN: Error processing link on {cleaned_current_url}: {link_e}")

                # --- Click Buttons (New Feature) ---
                if CLICK_BUTTONS:
                    # Find general buttons and input type="button"
                    buttons = page.locator("button, input[type='button'], input[type='submit']").all() # Added submit types here too
                    for btn_index, button_locator in enumerate(buttons):
                        try:
                            # Avoid clicking already-processed form submit buttons if TEST_FORMS_ON_EACH_PAGE is also True
                            # This is a heuristic; might need refinement depending on actual page structure
                            if button_locator.evaluate("el => el.closest('form')") and TEST_FORMS_ON_EACH_PAGE:
                                continue # Skip if it's inside a form and forms are handled separately

                            if button_locator.is_visible() and button_locator.is_enabled():
                                btn_text = button_locator.text_content() or button_locator.get_attribute("value") or f"Button {btn_index}"
                                report_content.append(f"Attempting to click button: '{btn_text}' on {cleaned_current_url}")
                                print(f"Clicking button: '{btn_text}'")

                                # Capture URL before click to detect navigation
                                url_before_click = page.url

                                # Use page.click() which handles auto-waiting
                                button_locator.click()
                                time.sleep(3) # Give time for potential new content/redirect

                                # Check if clicking the button led to a new page
                                if page.url != url_before_click:
                                    report_content.append(f"NOTE: Button click led to new URL: {page.url}")
                                    new_url_after_click = urlparse(page.url)._replace(query='', fragment='').geturl()
                                    if new_url_after_click not in visited_urls and new_url_after_click not in urls_to_visit:
                                        urls_to_visit.append(new_url_after_click)
                                    # Navigate back to original URL to continue crawling other elements on it
                                    page.goto(cleaned_current_url, wait_until="domcontentloaded")
                                    time.sleep(2) # Wait for original page to reload
                                else:
                                    report_content.append(f"NOTE: Button click did not change URL on {cleaned_current_url}.")
                                    # If it's an AJAX call, the page content might have changed.
                                    # AI analysis will capture these changes in the next page.content() call.

                        except PlaywrightTimeoutError as e:
                            report_content.append(f"FAIL: Button click failed (Timeout) for button {btn_index}: {e}")
                        except Exception as e:
                            report_content.append(f"ERROR: General error during button click for button {btn_index}: {e}")

                # --- Test Forms on the Page (Simplified for Playwright example) ---
                if TEST_FORMS_ON_EACH_PAGE:
                    forms = page.locator("form").all()
                    for form_index, form_locator in enumerate(forms):
                        # Playwright locators are powerful; interact directly with form elements
                        # This is a very basic example; full form testing would involve more logic
                        # to identify input types, fill intelligently, and handle specific validations.
                        report_content.append(f"\n--- Attempting basic form interaction for form {form_index} ---")
                        try:
                            # Fill text/email inputs
                            text_inputs = form_locator.locator("input[type='text'], input[type='email'], input[type='password'], textarea")
                            for i in range(text_inputs.count()):
                                if text_inputs.nth(i).is_visible() and text_inputs.nth(i).is_editable():
                                    text_inputs.nth(i).fill("test_data")

                            # Click checkboxes/radios
                            checkboxes = form_locator.locator("input[type='checkbox']")
                            for i in range(checkboxes.count()):
                                if checkboxes.nth(i).is_visible() and checkboxes.nth(i).is_enabled():
                                    checkboxes.nth(i).click()

                            radios = form_locator.locator("input[type='radio']")
                            for i in range(radios.count()):
                                if radios.nth(i).is_visible() and radios.nth(i).is_enabled():
                                    radios.nth(i).click()

                            # Select first option in select dropdowns
                            selects = form_locator.locator("select")
                            for i in range(selects.count()):
                                if selects.nth(i).is_visible() and selects.nth(i).is_enabled():
                                    options = selects.nth(i).locator("option").all_text_contents()
                                    if options:
                                        selects.nth(i).select_option(options[0]) # Selects by value, label, or index

                            # Attempt to submit - use Playwright's form.submit() if available, or click the submit button
                            # Using submit_button locator which handles input type="submit" and button type="submit"
                            submit_button = form_locator.locator("input[type='submit'], button[type='submit']").first
                            if submit_button.is_visible() and submit_button.is_enabled():
                                report_content.append(f"Submitting form {form_index}...")
                                url_before_submit = page.url # Capture URL before submission
                                submit_button.click()
                                page.wait_for_load_state("domcontentloaded") # Wait for page to be ready after potential submit
                                time.sleep(3) # Give time for server response

                                report_content.append("\n--- AI Analysis: After Form Submission ---")
                                ai_analysis_form_submit = analyze_content_with_ai(
                                    page.content(),
                                    main_ai_prompt
                                )
                                report_content.append(ai_analysis_form_submit)

                                # After form submission, navigate back to original URL to continue crawling
                                if page.url != url_before_submit: # If form submission changed URL, add new URL to queue
                                    new_url_after_submit = urlparse(page.url)._replace(query='', fragment='').geturl()
                                    if new_url_after_submit not in visited_urls and new_url_after_submit not in urls_to_visit:
                                        urls_to_visit.append(new_url_after_submit)
                                page.goto(cleaned_current_url, wait_until="domcontentloaded") # Return to the page being tested
                                time.sleep(2)
                            else:
                                report_content.append(f"WARN: No clickable submit button found for form {form_index}.")

                        except PlaywrightTimeoutError as e:
                            report_content.append(f"FAIL: Form interaction failed (Timeout) for form {form_index}: {e}")
                        except Exception as e:
                            report_content.append(f"ERROR: General error during form interaction for form {form_index}: {e}")


            except PlaywrightTimeoutError:
                report_content.append(f"FAIL: Page {cleaned_current_url} did not load within timeout.")
                page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"page_load_timeout_{page_count}.png"))
            except Exception as e:
                report_content.append(f"ERROR: An unexpected error occurred while testing {cleaned_current_url}: {e}")
                page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"page_error_{page_count}.png"))

        if page_count >= MAX_PAGES_TO_VISIT:
            report_content.append(f"\n--- Maximum pages to visit ({MAX_PAGES_TO_VISIT}) reached. Stopping traversal. ---")
        report_content.append("\n--- Automated Web Test Complete ---")
        report_content.append(f"Total unique pages visited: {len(visited_urls)}")
        report_content.append(f"Total forms attempted: {'N/A (Simplified)' if not TEST_FORMS_ON_EACH_PAGE else 'Yes, forms attempted'}")

        browser.close()

    # --- Generate Report ---
    print(f"\nWriting report to {REPORT_FILE}...")
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        for line in report_content:
            f.write(line + "\n")
    print(f"\nWeb test completed. Report saved to {REPORT_FILE}")
    print("Please review the report for AI insights and test outcomes and check the 'screenshots_playwright_buttons' directory.")

if __name__ == "__main__":
    run_web_test_playwright()