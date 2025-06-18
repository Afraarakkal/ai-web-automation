import os
import time
from collections import deque
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Page, Locator

import google.generativeai as genai

# --- Configuration ---
# AI Model and Report
GEMINI_MODEL = "gemini-1.5-flash"
REPORT_FILE = "web_test_report_playwright_with_testcases.txt" # Report file name
SCREENSHOT_DIR = "screenshots_playwright_testcases" # Directory to save screenshots

# Crawler Settings
MAX_PAGES_TO_VISIT = 20 # Limit the number of pages to prevent infinite crawling on large sites
CLICK_EXTERNAL_LINKS = False # Set to True if you want to test external links (use with caution!)

# --- Action Control Flags (YOU SET THESE DIRECTLY IN THE CODE) ---
PERFORM_BUTTON_CLICKS = True
PERFORM_FORM_TESTING = True

# --- TEST CASES (YOU MUST EDIT AND DEFINE THESE SPECIFIC URLs) ---
# Add full URLs (including https://) that you want the crawler to specifically visit.
# These URLs will be visited first, before general link discovery on the site.
# IMPORTANT: Replace these with the actual URLs from your target website for your scenario!
# I'm using a common test site (books.toscrape.com) as an example.
TEST_CASES_URLS = [
    "https://books.toscrape.com/",                                 # 1. Homepage
    "https://books.toscrape.com/catalogue/category/books_1/index.html", # 2. Books Category Page (Assuming 'Books' link leads here)
    "https://books.toscrape.com/catalogue/sharp-objects_997/index.html" # 3. Specific Product Page for 'Sharp Objects'
]

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
    MAX_CONTENT_LENGTH = 15000 # Max tokens for the model
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH] + "\n... [Content Truncated] ..."

    full_prompt = f"Analyze the following web page content. {prompt_suffix}\n\nContent:\n{content}"
    try:
        time.sleep(1) # Small delay before AI calls to be mindful of API rate limits
        print(f"Sending content for AI analysis (prompt len: {len(full_prompt)})...")
        response = gemini_model.generate_content(full_prompt)
        if response.parts and response.parts[0].text:
            return response.parts[0].text
        else:
            return "AI analysis completed, but no text response was generated."
    except Exception as e:
        return f"AI analysis failed: {e}. This might be due to API issues, rate limits, or content too large."

# --- Playwright Web Testing Logic ---

def run_web_test_playwright():
    report_content = []
    visited_urls = set()
    urls_to_visit = deque() # URLs to visit, prioritizing test cases

    # A set to keep track of URLs that are already in the queue to avoid duplicates
    urls_in_queue = set()

    def add_url_to_queue(url):
        normalized_url = urlparse(url)._replace(query='', fragment='').geturl()
        if normalized_url not in visited_urls and normalized_url not in urls_in_queue:
            urls_to_visit.append(normalized_url)
            urls_in_queue.add(normalized_url)
            print(f"DEBUG: Added to queue: {normalized_url}") # Debugging line

    # --- Get User Input for Testing ---
    print("\n--- Configure Web Test (Playwright) ---")
    start_url = input("Enter the STARTING URL for the web test (e.g., https://example.com):\n> ").strip()
    if not start_url.startswith("http://") and not start_url.startswith("https://"):
        start_url = "https://" + start_url

    parsed_start_url = urlparse(start_url)
    base_url = f"{parsed_start_url.scheme}://{parsed_start_url.netloc}"

    print("\n--- Define Your AI Task Prompt (Strict Adherence) ---")
    print("The AI will perform ONLY what is specified in this prompt for EVERY page visited.")
    print("Be precise, as the AI will not infer tasks beyond your direct instruction.")
    print("\nFor your 'Sharp Objects' scenario, use a prompt like this:")
    print("   \"Analyze this page. If this is a product detail page for 'Sharp Objects', find and extract its price and any available stock information. If it's a category page, identify the 'Sharp Objects' book. If it's the homepage, summarize its main sections. For any page, also identify potential issues with navigation or missing elements.\"")
    main_ai_prompt = input("\nEnter your PRIMARY AI analysis prompt:\n> ")
    print("--- Test Configuration Complete ---\n")

    # Playwright Context Manager
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) # Set to False for visible browser, True for headless
        page = browser.new_page()
        page.set_viewport_size({"width": 1280, "height": 800})

        report_content.append(f"--- Starting AI Web Test (Playwright) ---")
        report_content.append(f"Timestamp: {time.ctime()}")
        report_content.append(f"Starting URL: {start_url}")
        report_content.append(f"Base Domain for Internal Crawling: {base_url}")
        report_content.append(f"AI Analysis Prompt: '{main_ai_prompt}'")
        report_content.append(f"Gemini Model Used: {GEMINI_MODEL}\n")
        report_content.append(f"Button Clicks Enabled: {PERFORM_BUTTON_CLICKS}")
        report_content.append(f"Form Testing Enabled: {PERFORM_FORM_TESTING}")
        report_content.append(f"Number of Pre-defined Test Cases: {len(TEST_CASES_URLS)}\n")

        # --- Populate URLs to visit queue with test cases first ---
        for tc_url in TEST_CASES_URLS:
            add_url_to_queue(tc_url)

        # Add the initial start_url to the queue if it's not already covered by test cases
        add_url_to_queue(start_url)

        page_count = 0

        while urls_to_visit and page_count < MAX_PAGES_TO_VISIT:
            current_url_to_process = urls_to_visit.popleft()
            urls_in_queue.discard(current_url_to_process) # This URL is now being processed

            # Normalize the URL for comparison and adding to visited_urls
            normalized_current_url_to_process = urlparse(current_url_to_process)._replace(query='', fragment='').geturl()

            if normalized_current_url_to_process in visited_urls:
                print(f"DEBUG: Skipping already visited URL: {normalized_current_url_to_process}")
                continue

            if not CLICK_EXTERNAL_LINKS and urlparse(normalized_current_url_to_process).netloc != urlparse(base_url).netloc:
                report_content.append(f"Skipping external URL (outside base domain): {normalized_current_url_to_process}")
                continue

            visited_urls.add(normalized_current_url_to_process) # Mark as visited *before* attempting goto
            page_count += 1
            report_content.append(f"\n--- Testing Page {page_count}: {normalized_current_url_to_process} ---")
            print(f"Testing Page {page_count}: {normalized_current_url_to_process}")

            try:
                # --- Attempt Navigation ---
                print(f"DEBUG: Navigating to: {normalized_current_url_to_process}")
                page.goto(normalized_current_url_to_process, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3) # Give more buffer

                # Verify actual URL after navigation
                actual_url_after_goto = urlparse(page.url)._replace(query='', fragment='').geturl()
                if actual_url_after_goto != normalized_current_url_to_process:
                    report_content.append(f"WARN: Navigated to {normalized_current_url_to_process} but landed on {page.url} (might be redirect).")
                    print(f"WARN: Navigated to {normalized_current_url_to_process} but landed on {page.url} (might be redirect). Adding new URL to queue if not visited.")
                    add_url_to_queue(page.url) # Add the redirected URL to be processed later if unique
                    continue # Skip current page analysis and actions if it's not the intended URL

                # --- Take screenshot (with added error handling for timeouts) ---
                screenshot_filename = os.path.basename(urlparse(page.url).path).replace('/', '_').replace('.', '_') or 'index'
                screenshot_path = os.path.join(SCREENSHOT_DIR, f"page_{page_count}_{screenshot_filename}.png")
                try: # <--- New try block for screenshot
                    page.screenshot(path=screenshot_path, timeout=45000) # Increased timeout to 45 seconds
                    report_content.append(f"Screenshot saved: {screenshot_path}")
                except PlaywrightTimeoutError:
                    report_content.append(f"FAIL: Screenshot timed out for {page.url}. Page might be slow to render or unresponsive.")
                    print(f"FAIL: Screenshot timed out for {page.url}.")
                except Exception as screenshot_e:
                    report_content.append(f"ERROR: Failed to take screenshot for {page.url}: {screenshot_e}")
                    print(f"ERROR: Failed to take screenshot for {page.url}: {screenshot_e}")

                # Get page source for AI analysis
                page_source = page.content()

                # --- AI Content Analysis using the single user-defined prompt ---
                report_content.append("\n--- AI Analysis (Direct Task) ---")
                ai_analysis_page = analyze_content_with_ai(
                    page_source,
                    main_ai_prompt
                )
                report_content.append(ai_analysis_page)

                # --- Find and Queue New Links for further crawling ---
                links = page.locator("a").all()
                for link_locator in links:
                    try:
                        href = link_locator.get_attribute("href")
                        if href:
                            full_url = urljoin(page.url, href) # Use page.url for context
                            if (full_url.startswith("http://") or full_url.startswith("https://")) and \
                               urlparse(full_url).fragment == '' and \
                               (CLICK_EXTERNAL_LINKS or urlparse(full_url).netloc == urlparse(base_url).netloc):
                                add_url_to_queue(full_url)

                    except PlaywrightTimeoutError:
                        continue
                    except Exception as link_e:
                        report_content.append(f"WARN: Error processing link on {page.url}: {link_e}")


                # --- Click Buttons (Conditional Action) ---
                if PERFORM_BUTTON_CLICKS:
                    buttons = page.locator("button, input[type='button'], input[type='submit']").all()
                    for btn_index, button_locator in enumerate(buttons):
                        try:
                            # Skip submit buttons if form testing is enabled and we are handling forms separately
                            if button_locator.evaluate("el => el.closest('form')") and PERFORM_FORM_TESTING:
                                continue

                            if button_locator.is_visible() and button_locator.is_enabled():
                                btn_text = button_locator.text_content() or button_locator.get_attribute("value") or f"Button {btn_index}"
                                report_content.append(f"Attempting to click button: '{btn_text}' on {page.url}")
                                print(f"Clicking button: '{btn_text}'")

                                url_before_click = page.url
                                button_locator.click()
                                page.wait_for_load_state("domcontentloaded")
                                time.sleep(3)

                                if page.url != url_before_click:
                                    report_content.append(f"NOTE: Button click led to new URL: {page.url}. This URL will be processed in a future iteration.")
                                    add_url_to_queue(page.url)
                                    # If a navigation occurred, we want the main loop to pick up the new URL.
                                    # We don't continue processing elements on this page.
                                    break # Exit button loop, effectively ending current page processing

                                else:
                                    report_content.append(f"NOTE: Button click did not change URL on {page.url}.")

                        except PlaywrightTimeoutError as e:
                            report_content.append(f"FAIL: Button click failed (Timeout) for button {btn_index} on {page.url}: {e}")
                        except Exception as e:
                            report_content.append(f"ERROR: General error during button click for button {btn_index} on {page.url}: {e}")

                # --- Test Forms on the Page (Conditional Action) ---
                if PERFORM_FORM_TESTING:
                    forms = page.locator("form").all()
                    for form_index, form_locator in enumerate(forms):
                        report_content.append(f"\n--- Attempting basic form interaction for form {form_index} on {page.url} ---")
                        try:
                            # Fill text inputs and textareas
                            text_inputs = form_locator.locator("input[type='text'], input[type='email'], input[type='password'], textarea")
                            for i in range(text_inputs.count()):
                                if text_inputs.nth(i).is_visible() and text_inputs.nth(i).is_editable():
                                    text_inputs.nth(i).fill("test_data")

                            # Click checkboxes
                            checkboxes = form_locator.locator("input[type='checkbox']")
                            for i in range(checkboxes.count()):
                                if checkboxes.nth(i).is_visible() and checkboxes.nth(i).is_enabled():
                                    checkboxes.nth(i).click()

                            # Click radio buttons (selects the first visible/enabled one in a group)
                            radios = form_locator.locator("input[type='radio']")
                            for i in range(radios.count()):
                                if radios.nth(i).is_visible() and radios.nth(i).is_enabled():
                                    radios.nth(i).click()
                                    break

                            # Select options in dropdowns
                            selects = form_locator.locator("select")
                            for i in range(selects.count()):
                                if selects.nth(i).is_visible() and selects.nth(i).is_enabled():
                                    options = selects.nth(i).locator("option").all_text_contents()
                                    if options:
                                        selects.nth(i).select_option(options[0])

                            # Attempt to submit the form
                            submit_button = form_locator.locator("input[type='submit'], button[type='submit']").first
                            if submit_button.is_visible() and submit_button.is_enabled():
                                report_content.append(f"Submitting form {form_index} on {page.url}...")
                                url_before_submit = page.url
                                submit_button.click()
                                page.wait_for_load_state("domcontentloaded")
                                time.sleep(3)

                                report_content.append("\n--- AI Analysis: After Form Submission ---")
                                ai_analysis_form_submit = analyze_content_with_ai(
                                    page.content(),
                                    main_ai_prompt
                                )
                                report_content.append(ai_analysis_form_submit)

                                if page.url != url_before_submit:
                                    report_content.append(f"NOTE: Form submission led to new URL: {page.url}. This URL will be processed in a future iteration.")
                                    add_url_to_queue(page.url)
                                    # If a navigation occurred, we want the main loop to pick up the new URL.
                                    # We don't continue processing elements on this page.
                                    break # Exit form loop, effectively ending current page processing
                                else:
                                    report_content.append(f"NOTE: Form submission did not change URL on {page.url}.")
                            else:
                                report_content.append(f"WARN: No clickable submit button found for form {form_index} on {page.url}.")

                        except PlaywrightTimeoutError as e:
                            report_content.append(f"FAIL: Form interaction failed (Timeout) for form {form_index} on {page.url}: {e}")
                        except Exception as e:
                            report_content.append(f"ERROR: General error during form interaction for form {form_index} on {page.url}: {e}")

            except PlaywrightTimeoutError:
                report_content.append(f"FAIL: Page {normalized_current_url_to_process} did not load within timeout (30 seconds).")
                # When a page load times out, we still try to take a screenshot if possible
                screenshot_filename = os.path.basename(urlparse(normalized_current_url_to_process).path).replace('/', '_').replace('.', '_') or 'index_timeout'
                screenshot_path = os.path.join(SCREENSHOT_DIR, f"page_load_timeout_{page_count}_{screenshot_filename}.png")
                try:
                    page.screenshot(path=screenshot_path, timeout=5000) # Give a short timeout for screenshot
                    report_content.append(f"Screenshot saved for timeout page: {screenshot_path}")
                except Exception as screenshot_e:
                    report_content.append(f"ERROR: Failed to take screenshot for timed-out page {normalized_current_url_to_process}: {screenshot_e}")

            except Exception as e:
                report_content.append(f"ERROR: An unexpected error occurred while testing {normalized_current_url_to_process}: {e}")
                # Try to take a screenshot even on general errors
                screenshot_filename = os.path.basename(urlparse(normalized_current_url_to_process).path).replace('/', '_').replace('.', '_') or 'index_error'
                screenshot_path = os.path.join(SCREENSHOT_DIR, f"page_error_{page_count}_{screenshot_filename}.png")
                try:
                    page.screenshot(path=screenshot_path, timeout=5000) # Give a short timeout for screenshot
                    report_content.append(f"Screenshot saved for error page: {screenshot_path}")
                except Exception as screenshot_e:
                    report_content.append(f"ERROR: Failed to take screenshot for error page {normalized_current_url_to_process}: {screenshot_e}")


        if page_count >= MAX_PAGES_TO_VISIT:
            report_content.append(f"\n--- Maximum pages to visit ({MAX_PAGES_TO_VISIT}) reached. Stopping traversal. ---")
        report_content.append("\n--- Automated Web Test Complete ---")
        report_content.append(f"Total unique pages visited: {len(visited_urls)}")
        report_content.append(f"Button Clicks Performed: {PERFORM_BUTTON_CLICKS}")
        report_content.append(f"Form Testing Performed: {PERFORM_FORM_TESTING}")

        browser.close()

    # --- Generate Report ---
    print(f"\nWriting report to {REPORT_FILE}...")
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        for line in report_content:
            f.write(line + "\n")
    print(f"\nWeb test completed. Report saved to {REPORT_FILE}")
    print(f"Please review the report ({REPORT_FILE}) for AI insights and test outcomes.")
    print(f"Check the '{SCREENSHOT_DIR}' directory for screenshots.")

if __name__ == "__main__":
    run_web_test_playwright()