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
REPORT_FILE = "web_test_report_playwright_conditional_tasks.txt" # Changed report file name
SCREENSHOT_DIR = "screenshots_playwright_conditional_tasks" # Directory to save screenshots

# Crawler Settings
MAX_PAGES_TO_VISIT = 20 # Increased max pages as many might not be the target type
TEST_FORMS_ON_EACH_PAGE = False # Simplified for this example, can be re-enabled
CLICK_BUTTONS = True
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
        # Added a small delay before AI calls to be mindful of API rate limits
        time.sleep(1)
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
    start_url = input("Enter the STARTING URL for the web test (e.g., https://example.com/books):\n> ").strip()
    if not start_url.startswith("http://") and not start_url.startswith("https://"):
        start_url = "https://" + start_url # Prepend https if not present

    parsed_start_url = urlparse(start_url)
    base_url = f"{parsed_start_url.scheme}://{parsed_start_url.netloc}"

    print("\n--- Step 1: Define Page Type Identification Prompt ---")
    print("This prompt helps the AI identify if a page is the specific type you're interested in (e.g., a 'book page').")
    print("The AI MUST respond with 'YES' or 'NO' ONLY, followed by a brief reason.")
    print("Example: 'Is this page a product detail page for a book? Respond with YES or NO only. If YES, explain why briefly. If NO, state why briefly.'")
    page_type_identification_prompt = input("\nEnter your Page Type Identification Prompt:\n> ")

    print("\n--- Step 2: Define Specific Task Prompt ---")
    print("This prompt tells the AI what detailed information to extract or verify, but ONLY if the page is identified as your target type.")
    print("Example (for a book page): 'Extract the book title, author, price, and stock status. If 'Out of Stock' or 'Unavailable' is present, report it as 'Stock Status: OUT OF STOCK'. Otherwise, report it as 'Stock Status: IN STOCK'.'")
    specific_task_prompt = input("\nEnter your Specific Task Prompt:\n> ")

    # Default prompt for non-target pages
    general_page_health_prompt = "Perform a general health check on this page. Report any broken links, missing content, layout issues, or obvious errors. Focus on overall functionality and visual integrity."

    print("--- Test Configuration Complete ---\n")

    # Playwright Context Manager
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) # Set to False for visible browser, True for headless
        page = browser.new_page()
        page.set_viewport_size({"width": 1280, "height": 800})

        report_content.append(f"--- Starting AI Web Test (Playwright) ---")
        report_content.append(f"Timestamp: {time.ctime()}")
        report_content.append(f"Starting URL: {start_url}")
        report_content.append(f"Base Domain for Crawling: {base_url}")
        report_content.append(f"Page Type Identification Prompt: '{page_type_identification_prompt}'")
        report_content.append(f"Specific Task Prompt: '{specific_task_prompt}'")
        report_content.append(f"Gemini Model Used: {GEMINI_MODEL}\n")

        urls_to_visit.append(start_url)
        page_count = 0

        while urls_to_visit and page_count < MAX_PAGES_TO_VISIT:
            current_url = urls_to_visit.popleft()

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
                page.goto(cleaned_current_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3) # Give some buffer for JS to render

                screenshot_filename = os.path.basename(urlparse(cleaned_current_url).path).replace('/', '_').replace('.', '_') or 'index'
                screenshot_path = os.path.join(SCREENSHOT_DIR, f"page_{page_count}_{screenshot_filename}.png")
                page.screenshot(path=screenshot_path)
                report_content.append(f"Screenshot saved: {screenshot_path}")

                page_source = page.content()

                # --- AI Page Type Identification ---
                report_content.append("\n--- AI Page Type Identification ---")
                ai_classification_response = analyze_content_with_ai(
                    page_source,
                    page_type_identification_prompt
                )
                report_content.append(f"AI Classification: {ai_classification_response}")

                is_target_page_type = "YES" in ai_classification_response.upper()

                # --- Conditional AI Content Analysis ---
                if is_target_page_type:
                    report_content.append("\n--- AI Specific Task Analysis (Target Page) ---")
                    ai_analysis_page = analyze_content_with_ai(
                        page_source,
                        specific_task_prompt # Apply specific task prompt
                    )
                else:
                    report_content.append("\n--- AI General Health Analysis (Non-Target Page) ---")
                    ai_analysis_page = analyze_content_with_ai(
                        page_source,
                        general_page_health_prompt # Apply general health prompt
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

                # --- Click Buttons ---
                if CLICK_BUTTONS:
                    buttons = page.locator("button, input[type='button'], input[type='submit']").all()
                    for btn_index, button_locator in enumerate(buttons):
                        try:
                            if button_locator.evaluate("el => el.closest('form')") and TEST_FORMS_ON_EACH_PAGE:
                                continue

                            if button_locator.is_visible() and button_locator.is_enabled():
                                btn_text = button_locator.text_content() or button_locator.get_attribute("value") or f"Button {btn_index}"
                                report_content.append(f"Attempting to click button: '{btn_text}' on {cleaned_current_url}")
                                print(f"Clicking button: '{btn_text}'")

                                url_before_click = page.url
                                button_locator.click()
                                time.sleep(3)

                                if page.url != url_before_click:
                                    report_content.append(f"NOTE: Button click led to new URL: {page.url}")
                                    new_url_after_click = urlparse(page.url)._replace(query='', fragment='').geturl()
                                    if new_url_after_click not in visited_urls and new_url_after_click not in urls_to_visit:
                                        urls_to_visit.append(new_url_after_click)
                                    page.goto(cleaned_current_url, wait_until="domcontentloaded")
                                    time.sleep(2)
                                else:
                                    report_content.append(f"NOTE: Button click did not change URL on {cleaned_current_url}.")

                        except PlaywrightTimeoutError as e:
                            report_content.append(f"FAIL: Button click failed (Timeout) for button {btn_index}: {e}")
                        except Exception as e:
                            report_content.append(f"ERROR: General error during button click for button {btn_index}: {e}")

                # --- Test Forms on the Page ---
                if TEST_FORMS_ON_EACH_PAGE:
                    forms = page.locator("form").all()
                    for form_index, form_locator in enumerate(forms):
                        report_content.append(f"\n--- Attempting basic form interaction for form {form_index} ---")
                        try:
                            text_inputs = form_locator.locator("input[type='text'], input[type='email'], input[type='password'], textarea")
                            for i in range(text_inputs.count()):
                                if text_inputs.nth(i).is_visible() and text_inputs.nth(i).is_editable():
                                    text_inputs.nth(i).fill("test_data")

                            checkboxes = form_locator.locator("input[type='checkbox']")
                            for i in range(checkboxes.count()):
                                if checkboxes.nth(i).is_visible() and checkboxes.nth(i).is_enabled():
                                    checkboxes.nth(i).click()

                            radios = form_locator.locator("input[type='radio']")
                            for i in range(radios.count()):
                                if radios.nth(i).is_visible() and radios.nth(i).is_enabled():
                                    radios.nth(i).click()

                            selects = form_locator.locator("select")
                            for i in range(selects.count()):
                                if selects.nth(i).is_visible() and selects.nth(i).is_enabled():
                                    options = selects.nth(i).locator("option").all_text_contents()
                                    if options:
                                        selects.nth(i).select_option(options[0])

                            submit_button = form_locator.locator("input[type='submit'], button[type='submit']").first
                            if submit_button.is_visible() and submit_button.is_enabled():
                                report_content.append(f"Submitting form {form_index}...")
                                url_before_submit = page.url
                                submit_button.click()
                                page.wait_for_load_state("domcontentloaded")
                                time.sleep(3)

                                report_content.append("\n--- AI Analysis: After Form Submission ---")
                                # Apply the general prompt or specific if the form submission leads to a target page
                                ai_analysis_form_submit = analyze_content_with_ai(
                                    page.content(),
                                    general_page_health_prompt # Default to general health for now
                                )
                                report_content.append(ai_analysis_form_submit)

                                if page.url != url_before_submit:
                                    new_url_after_submit = urlparse(page.url)._replace(query='', fragment='').geturl()
                                    if new_url_after_submit not in visited_urls and new_url_after_submit not in urls_to_visit:
                                        urls_to_visit.append(new_url_after_submit)
                                page.goto(cleaned_current_url, wait_until="domcontentloaded")
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
        report_content.append(f"Total forms attempted: {'N/A (Skipped)' if not TEST_FORMS_ON_EACH_PAGE else 'Yes, forms attempted'}")

        browser.close()

    # --- Generate Report ---
    print(f"\nWriting report to {REPORT_FILE}...")
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        for line in report_content:
            f.write(line + "\n")
    print(f"\nWeb test completed. Report saved to {REPORT_FILE}")
    print("Please review the report for AI insights and test outcomes and check the 'screenshots_playwright_conditional_tasks' directory.")

if __name__ == "__main__":
    run_web_test_playwright()