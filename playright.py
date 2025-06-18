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
REPORT_FILE = "web_test_report_playwright.txt" # Changed report file name
SCREENSHOT_DIR = "screenshots_playwright_test" # Directory to save screenshots

# Crawler Settings
MAX_PAGES_TO_VISIT = 10
TEST_FORMS_ON_EACH_PAGE = False # Simplified for this example, can be re-enabled
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
                # Playwright often auto-waits, but a small sleep can help for dynamic JS rendering
                time.sleep(2)

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
                # Playwright's page.locator allows for robust element selection
                links = page.locator("a").all() # Get all <a> locators
                for link_locator in links:
                    try:
                        href = link_locator.get_attribute("href")
                        if href:
                            full_url = urljoin(cleaned_current_url, href)
                            # Basic validation and domain check
                            if (full_url.startswith("http://") or full_url.startswith("https://")) and \
                               urlparse(full_url).fragment == '' and \
                               (CLICK_EXTERNAL_LINKS or urlparse(full_url).netloc == urlparse(base_url).netloc):
                                cleaned_full_url = urlparse(full_url)._replace(query='').geturl()
                                if cleaned_full_url not in visited_urls and cleaned_full_url not in urls_to_visit:
                                    urls_to_visit.append(cleaned_full_url)
                    except PlaywrightTimeoutError: # Or other Playwright errors on locator
                        continue # Skip elements that cause issues
                    except Exception as link_e:
                        report_content.append(f"WARN: Error processing link on {cleaned_current_url}: {link_e}")

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

                            # Attempt to submit
                            submit_button = form_locator.locator("input[type='submit'], button[type='submit'], button:has-text('Submit'), button:has-text('Send')").first
                            if submit_button.is_visible() and submit_button.is_enabled():
                                report_content.append(f"Submitting form {form_index}...")
                                page.wait_for_load_state("domcontentloaded") # Wait for page to be ready after potential submit
                                submit_button.click()
                                time.sleep(3) # Give time for server response

                                report_content.append("\n--- AI Analysis: After Form Submission ---")
                                ai_analysis_form_submit = analyze_content_with_ai(
                                    page.content(),
                                    main_ai_prompt # Use general prompt
                                )
                                report_content.append(ai_analysis_form_submit)
                                # After form submission, navigate back to original URL to continue crawling
                                page.goto(cleaned_current_url, wait_until="domcontentloaded")
                                time.sleep(2)
                            else:
                                report_content.append(f"WARN: No clickable submit button found for form {form_index}.")

                        except PlaywrightTimeoutError as e:
                            report_content.append(f"FAIL: Form interaction failed (Timeout) for form {form_index}: {e}")
                        except Exception as e:
                            report_content.append(f"ERROR: General error during form interaction for form {form_index}: {e}")
                        finally:
                            pass # No explicit navigation back needed if submit failed or form was AJAX

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
        report_content.append(f"Total forms attempted: {'N/A (Simplified)' if not TEST_FORMS_ON_EACH_PAGE else 'Yes, forms attempted'}") # Update if form testing is detailed

        browser.close() # Close the browser when done

    # --- Generate Report ---
    print(f"\nWriting report to {REPORT_FILE}...")
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        for line in report_content:
            f.write(line + "\n")
    print(f"\nWeb test completed. Report saved to {REPORT_FILE}")
    print("Please review the report for AI insights and test outcomes and check the 'screenshots_playwright_test' directory.")

if __name__ == "__main__":
    run_web_test_playwright()