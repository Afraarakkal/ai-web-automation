import asyncio
import json
import re
import os
from playwright.async_api import async_playwright

# Import the Google Generative AI library
import google.generativeai as genai

# --- AI Model Configuration ---
GEMINI_MODEL = "gemini-1.5-flash"

# Configure the API key using the GEMINI_API_KEY environment variable
try:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
except KeyError:
    print("Error: GEMINI_API_KEY environment variable not set. Please set it.")
    exit()

# Initialize Gemini Model
try:
    gemini_model = genai.GenerativeModel(GEMINI_MODEL)
except Exception as e:
    print(f"Error initializing Gemini model '{GEMINI_MODEL}': {e}")
    print("Please check if the model is available and your API key is correct.")
    exit()

# Global dictionary to store extracted data
extracted_data = {}

# --- Helper function to infer generalized selectors (WEBSITE INDEPENDENT VERSION) ---

def infer_generic_selectors(description: str) -> list[str]:
    """
    Infers a list of potential Playwright selectors based on a natural language description,
    designed to be as website-independent as possible by focusing on common HTML attributes
    and text content rather than site-specific IDs or classes.
    """
    description_lower = description.lower()
    selectors = []

    # --- Button and Link Related ---
    # Prioritize buttons or links with exact or partial text matches
    button_link_keywords = ['button', 'link', 'click', 'submit', 'go', 'next', 'continue', 'sign in', 'log in', 'login', 'checkout', 'add to cart', 'cart', 'buy']
    for keyword in button_link_keywords:
        if keyword in description_lower:
            # Exact text match for buttons/links
            text_match = re.search(r"'(.*?)'", description_lower) or re.search(r'"(.*?)"', description_lower)
            if text_match:
                text_content = text_match.group(1).strip()
                selectors.append(f"button:has-text('{text_content}')")
                selectors.append(f"a:has-text('{text_content}')")
                # Try case-insensitive (Playwright :has-text is case-sensitive by default unless regex flag is used)
                selectors.append(f"button:has-text(/{re.escape(text_content)}/i)")
                selectors.append(f"a:has-text(/{re.escape(text_content)}/i)")
                # Add button with attribute for text (e.g., value for submit inputs)
                selectors.append(f"input[type='submit'][value*='{text_content}']")
                selectors.append(f"input[type='button'][value*='{text_content}']")
                # Aria-label or data-testid
                selectors.append(f"*[aria-label*='{text_content}']")
                selectors.append(f"*[data-testid*='{text_content.replace(' ', '-')}']")
            else:
                # General button/link if no specific text is extracted but keywords are present
                selectors.append("button")
                selectors.append("a")
                selectors.append("input[type='submit']")
                selectors.append("input[type='button']")
                selectors.append("[role='button']")
                selectors.append("[role='link']")

    # --- Input Field Related ---
    # Search bar/input field
    if 'search' in description_lower or 'input' in description_lower or 'fill in' in description_lower or 'type' in description_lower:
        input_label_match = re.search(r'(?:text input|input field|fill in|type into)(?: labeled| with text| named| for)?\s*\'?\"?([^\']+)\'?\"?', description_lower)
        input_label = input_label_match.group(1).strip() if input_label_match else None

        if input_label:
            # Look for inputs with matching placeholder, aria-label, name, or ID
            selectors.append(f"input[placeholder*='{input_label}']")
            selectors.append(f"input[aria-label*='{input_label}']")
            selectors.append(f"input[name*='{input_label}']")
            selectors.append(f"input[id*='{input_label}']")
            selectors.append(f"textarea[placeholder*='{input_label}']")
            selectors.append(f"textarea[aria-label*='{input_label}']")
            selectors.append(f"textarea[name*='{input_label}']")
            selectors.append(f"textarea[id*='{input_label}']")
            # Look for inputs preceded by a label with matching text
            selectors.append(f"label:has-text('{input_label}') + input")
            selectors.append(f"label:has-text('{input_label}') + textarea")
        
        # General input fields
        selectors.append("input[type='text']")
        selectors.append("input[type='email']")
        selectors.append("input[type='password']")
        selectors.append("input[type='search']")
        selectors.append("textarea")
        selectors.append("[role='textbox']")


    # --- Dropdown/Select Related ---
    if 'dropdown' in description_lower or 'select' in description_lower or 'sort by' in description_lower or 'filter by' in description_lower:
        option_text_match = re.search(r"'(.*?)'", description_lower) or re.search(r'"(.*?)"', description_lower)
        option_text = option_text_match.group(1).strip() if option_text_match else None

        # Select element
        selectors.append("select")
        selectors.append("[role='combobox']") # For custom dropdowns
        
        # Options within a select or custom dropdown
        if option_text:
            selectors.append(f"option:has-text('{option_text}')")
            selectors.append(f"option[value*='{option_text.lower().replace(' ', '_')}']") # e.g., price_high_to_low
            selectors.append(f"option[value*='{option_text.lower().replace(' ', '')}']") # e.g., pricehightolow
            selectors.append(f"div[role='option']:has-text('{option_text}')") # For custom dropdowns
            selectors.append(f"li:has-text('{option_text}')") # Common for dropdown lists

        # Try to find the dropdown element itself by label or aria-label
        dropdown_label_match = re.search(r'(?:sort by|filter by|select from) ?\'?\"?([^\']+)\'?\"?', description_lower)
        if dropdown_label_match:
            dropdown_label = dropdown_label_match.group(1).strip()
            selectors.append(f"select[aria-label*='{dropdown_label}']")
            selectors.append(f"select[name*='{dropdown_label}']")
            selectors.append(f"select[id*='{dropdown_label}']")
            selectors.append(f"label:has-text('{dropdown_label}') + select")
            selectors.append(f"button:has-text('{dropdown_label}')") # For dropdowns triggered by a button


    # --- Checkbox/Radio Related ---
    if 'checkbox' in description_lower or 'radio' in description_lower or 'toggle' in description_lower:
        label_match = re.search(r'(?:checkbox|radio|toggle)(?: labeled| with text)?\s*\'?\"?([^\']+)\'?\"?', description_lower)
        label_text = label_match.group(1).strip() if label_match else None

        if label_text:
            selectors.append(f"input[type='checkbox'][aria-label*='{label_text}']")
            selectors.append(f"input[type='radio'][aria-label*='{label_text}']")
            selectors.append(f"label:has-text('{label_text}') input[type='checkbox']")
            selectors.append(f"label:has-text('{label_text}') input[type='radio']")
            selectors.append(f"*[role='checkbox']:has-text('{label_text}')")
            selectors.append(f"*[role='radio']:has-text('{label_text}')")
        
        # General checkboxes/radios
        selectors.append("input[type='checkbox']")
        selectors.append("input[type='radio']")
        selectors.append("[role='checkbox']")
        selectors.append("[role='radio']")


    # --- Content Extraction Related (product details, reviews, etc.) ---
    if 'product title' in description_lower:
        selectors += [
            "h1[itemprop*='name']", "h2[itemprop*='name']", ".product-title", ".item-name",
            "[data-qa='product-title']", "[data-test='product-title']",
            "h1:has-text(/product/i)", "h2:has-text(/title/i)",
            "a[href*='/product/'][class*='title']", # Link to product with title class
            "div[class*='product-info'] h1", "div[class*='product-info'] h2",
        ]
    elif 'product price' in description_lower or 'item price' in description_lower:
        selectors += [
            "span[itemprop='price']", ".product-price", ".item-price", ".price",
            "[data-qa='product-price']", "[data-test='product-price']",
            "span:has-text(/price/i)", "div:has-text(/currency/i)",
            ".price-value", ".current-price",
        ]
    elif 'product description' in description_lower:
        selectors += [
            "div[itemprop='description']", ".product-description", ".item-description",
            "#description", "#product-details", ".description-content",
            "section:has-text(/description/i)",
        ]
    elif 'image' in description_lower:
        selectors += [
            "img[alt*='product']", "img[alt*='item']", ".product-image", ".item-image",
            "img[role='img']", "img[srcset]",
            "picture img", # Modern image tags
        ]
    elif 'review' in description_lower:
        selectors += [
            ".review-text", ".customer-review", ".review-body",
            "[data-hook='review']", "[itemprop='review']",
            "div:has-text(/review/i)", "span:has-text(/rating/i)",
        ]
    elif 'all' in description_lower and ('products' in description_lower or 'items' in description_lower or 'results' in description_lower):
        selectors += [
            "[data-product-id]", "[data-item-id]", ".product-card", ".item-tile",
            ".search-result", ".product-listing-item",
            "div[class*='product-grid'] > div", "div[class*='item-list'] > div",
            "article[role='listitem']", "li[role='listitem']", # Common for item lists
        ]

    # --- General Elements based on roles or common IDs/classes (last resort before text) ---
    selectors.append("[role='main']") # Main content area
    selectors.append("main")
    selectors.append("header")
    selectors.append("footer")
    selectors.append("nav")
    selectors.append("[role='navigation']")

    # --- Fallback to Text-Based Selectors (most general, but can be less precise) ---
    # Add generic text selectors only if no more specific selectors were found so far
    # These should be lower priority as they can match too broadly.
    if not selectors or not any(s for s in selectors if not s.startswith("text=") and not s.startswith(":has-text=")):
        # Prefer exact text match if present in the description
        exact_text_match = re.search(r"'(.*?)'", description) or re.search(r'"(.*?)"', description)
        if exact_text_match:
            text_content = exact_text_match.group(1).strip()
            selectors.append(f"text='{text_content}'")
            selectors.append(f":has-text('{text_content}')")
            # Case-insensitive text match
            selectors.append(f"text=/{re.escape(text_content)}/i")
            selectors.append(f":has-text(/{re.escape(text_content)}/i)")
        else:
            # Otherwise, use the whole description as a general text match
            selectors.append(f"text='{description}'")
            selectors.append(f":has-text('{description}')")
            selectors.append(f"text=/{re.escape(description)}/i")
            selectors.append(f":has-text(/{re.escape(description)}/i)")


    # Remove duplicates while preserving order
    seen = set()
    result = []
    for sel in selectors:
        if sel not in seen:
            seen.add(sel)
            result.append(sel)

    return result


# --- AI function using Gemini (No changes needed, as it generates generic descriptions) ---

async def get_instructions_from_ai(prompt: str) -> dict:
    """
    Sends the user's natural language instruction to the Gemini model
    and expects a JSON array of actions for web automation.
    """
    try:
        system_instruction = (
            "You are an AI assistant that converts user instructions into a JSON array of actions for web automation. "
            "Each action in the array should be a JSON object with an 'action' key and relevant parameters. "
            "Only generate actions explicitly requested or implied by the user's prompt. "
            "Do not add additional actions not specified by the user.\n\n"
            "- For **'navigate'** action: `{\"action\": \"navigate\", \"url\": \"<URL_TO_NAVIGATE_TO>\"}`\n"
            "- For **'click'**, **'wait'**, and **'assert'** actions: `{\"action\": \"<action_type>\", \"selector_description\": \"<NATURAL_LANGUAGE_DESCRIPTION_OF_ELEMENT>\"}`\n"
            "- For **'type'** action (filling text into an input): `{\"action\": \"type\", \"selector_description\": \"<NATURAL_LANGUAGE_DESCRIPTION_OF_INPUT_FIELD>\", \"value\": \"<TEXT_TO_TYPE>\"}`\n"
            "- For **'select'** action (selecting an option from a dropdown): `{\"action\": \"select\", \"selector_description\": \"<NATURAL_LANGUAGE_DESCRIPTION_OF_DROPDOWN>\", \"value\": \"<OPTION_TEXT_TO_SELECT>\"}`\n"
            "- For **'scroll'** action (scrolling the page): `{\"action\": \"scroll\", \"to\": \"<'bottom' OR 'top'>\"}`. If a specific element should be scrolled, add `\"selector_description\": \"<NATURAL_LANGUAGE_DESCRIPTION_OF_SCROLLABLE_ELEMENT>\"`\n"
            "- For **'extract'** action (getting text content from an element): `{\"action\": \"extract\", \"selector_description\": \"<NATURAL_LANGUAGE_DESCRIPTION_OF_ELEMENT_TO_EXTRACT>\", \"name\": \"<VARIABLE_NAME_FOR_EXTRACTED_DATA>\"}`. "
            "If extracting multiple items (e.g., all product titles), indicate this in `selector_description` (e.g., 'all product titles') and the `name` should be plural (e.g., 'product_titles').\n"
            "- For **'screenshot'** action: `{\"action\": \"screenshot\", \"name\": \"<FILENAME.png>\"}`\n\n"
            "If the user provides a starting URL, ensure the first action is 'navigate' to that URL. "
            "If the user only gives actions without an explicit URL, assume the actions start from the current page and do not generate a 'navigate' action unless specifically instructed.\n\n"
            "Example JSON output: "
            '`{"actions": [{"action": "navigate", "url": "https://example.com"}, {"action": "type", "selector_description": "username input field", "value": "myuser"}, {"action": "select", "selector_description": "sort by dropdown", "value": "Price: High to Low"}, {"action": "scroll", "to": "bottom"}, {"action": "extract", "selector_description": "all product titles", "name": "extracted_titles"}, {"action": "click", "selector_description": "Sign In button"}, {"action": "screenshot", "name": "final_page.png"}]}`'
        )

        print("Sending instruction to Gemini for action planning...")
        response = await genai.GenerativeModel(GEMINI_MODEL).generate_content_async(
            f"{system_instruction}\n\nUser instruction: {prompt}"
        )
        
        text = response.text.strip()
        # Clean up potential markdown code blocks from Gemini's response
        if text.startswith("```json") and text.endswith("```"):
            text = text[7:-3].strip()
            
        return json.loads(text)

    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from AI response: {e}")
        print(f"AI response was: \n{text}")
        return {"actions": []}
    except Exception as e:
        print(f"An error occurred while calling the AI model: {e}")
        return {"actions": []}


# --- Utility: try selectors one by one until success ---

async def try_selectors(page, selectors, action_type, selector_description_for_debug: str = "element", value=None, timeout=15000):
    """Attempts to perform a Playwright action using a list of selectors in order,
    stopping at the first successful attempt."""
    last_error = None
    
    for sel in selectors:
        try:
            # First ensure the element exists
            element = await page.wait_for_selector(sel, state='attached', timeout=timeout)
            
            # For interactive actions, ensure it's visible and enabled
            if action_type in ['click', 'type', 'select']:
                await element.wait_for_element_state('visible', timeout=timeout)
                is_disabled = await element.get_attribute('disabled')
                if is_disabled is not None: # Check if attribute exists and is not 'false' (though Playwright handles this)
                    raise Exception(f"Element '{sel}' is disabled.")
                
                # Scroll into view if needed
                await element.scroll_into_view_if_needed()
                
                # Additional check for clickable
                if action_type == 'click':
                    box = await element.bounding_box()
                    if not box:
                        raise Exception(f"Element '{sel}' not clickable (no bounding box).")
            
            # --- Perform the actual action based on action_type ---
            if action_type == 'click':
                await element.click()
                print(f"Successfully clicked using selector: {sel} (Description: '{selector_description_for_debug}')")
                print(f"Page URL after click attempt: {page.url()}")
                # Sanitize selector_description_for_debug for filename
                safe_desc_filename = re.sub(r'[^\w\s-]', '', selector_description_for_debug.lower())
                safe_desc_filename = re.sub(r'[-\s]+', '_', safe_desc_filename).strip('_')
                if not safe_desc_filename: safe_desc_filename = "element" # fallback
                await page.screenshot(path=f"debug_after_click_on_{safe_desc_filename}.png")

            elif action_type == 'type':
                await element.fill(value)
                print(f"Successfully typed '{value}' into '{selector_description_for_debug}' using selector: {sel}")
            elif action_type == 'select':
                # For select, we need to try selecting by value, label, or index
                try:
                    await element.select_option(value)
                    print(f"Successfully selected '{value}' in '{selector_description_for_debug}' using selector: {sel}")
                except Exception:
                    # If direct value fails, try selecting by label (text)
                    await element.select_option(label=value)
                    print(f"Successfully selected '{value}' (by label) in '{selector_description_for_debug}' using selector: {sel}")
            elif action_type == 'extract':
                # The 'value' parameter for extract action is the 'name' for extracted_data
                data_name = value 
                if "all" in selector_description_for_debug.lower() and \
                    ("products" in selector_description_for_debug.lower() or \
                     "items" in selector_description_for_debug.lower() or \
                     "titles" in selector_description_for_debug.lower() or \
                     "prices" in selector_description_for_debug.lower() or \
                     "reviews" in selector_description_for_debug.lower()):
                    # Extract multiple elements
                    elements = await page.query_selector_all(sel)
                    extracted_texts = []
                    for el_idx, el in enumerate(elements):
                        text_content = await el.text_content()
                        if text_content:
                            extracted_texts.append(text_content.strip())
                        if el_idx < 5: # Print first few for confirmation
                             print(f"Extracted item {el_idx+1} for '{data_name}': '{text_content.strip()[:50]}...'")

                    extracted_data[data_name] = extracted_texts
                    print(f"Successfully extracted {len(extracted_texts)} items for '{data_name}' using selector: {sel}")
                else:
                    # Extract single element
                    text_content = await element.text_content()
                    if text_content:
                        extracted_data[data_name] = text_content.strip()
                        print(f"Successfully extracted '{text_content.strip()}' for '{data_name}' using selector: {sel}")
                    else:
                        raise Exception("No text content found for extraction.")
            elif action_type == 'wait':
                # The wait_for_selector already handles the waiting, no further action needed
                print(f"Successfully waited for element '{selector_description_for_debug}' using selector: {sel}")
            elif action_type == 'assert':
                # For assert, we check if the element exists and is visible
                # The wait_for_selector and checks above already cover this
                print(f"Assertion successful: element '{selector_description_for_debug}' found and visible using selector: {sel}")

            return True
            
        except Exception as e:
            last_error = f"Selector '{sel}' for '{selector_description_for_debug}' failed: {str(e)}"
            continue
    
    print(f"All selectors failed for action '{action_type}' on '{selector_description_for_debug}'. Last error: {last_error}")
    return False


# --- Main automation runner ---

async def run_automation(natural_language_instruction: str):
    """
    Executes a series of web automation steps based on a natural language instruction
    processed by the AI.
    """
    # 1. Get AI instructions
    ai_response = await get_instructions_from_ai(natural_language_instruction)
    actions = ai_response.get("actions", [])

    if not actions:
        print("AI did not return any executable actions or an error occurred. Please refine your instruction.")
        return

    print(f"\nAI generated actions: {json.dumps(actions, indent=2)}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Keep headless=False for human interaction
        page = await browser.new_page()

        for step_idx, step in enumerate(actions):
            action = step.get("action")
            selector_description = step.get("selector_description", "N/A")
            print(f"\n--- Step {step_idx + 1}: Action '{action}' on '{selector_description}' ---")

            if action == "navigate":
                url = step.get("url")
                if url:
                    os.environ["CURRENT_URL"] = url  
                    print(f"Navigating to {url}")
                    try:
                        await page.goto(url, wait_until='domcontentloaded')  
                        print(f"Successfully navigated to {url}")
                    except Exception as e:
                        print(f"Failed to navigate to {url}: {e}")
                        screenshot_name = f"failure_navigate_to_{url.replace('https://','').replace('http://','').replace('/', '_')}.png"
                        await page.screenshot(path=screenshot_name)
                        print(f"Screenshot saved to {screenshot_name}")
                        break  
                else:
                    print("Navigation action missing URL, skipping.")

            elif action in ("click", "type", "select", "wait", "assert", "extract"):
                desc = step.get("selector_description")
                value = step.get("value") if action in ("type", "select", "extract") else None
                if not desc:
                    print(f"Missing selector_description for action {action}, skipping.")
                    continue

                selectors = infer_generic_selectors(desc)
                print(f"Attempting to '{action}' on: '{desc}' using selectors: {selectors}")

                success = await try_selectors(page, selectors, action, selector_description_for_debug=desc, value=value)
                
                if not success:
                    print(f"\nCRITICAL: Failed to {action} on '{desc}'.")
                    
                    # Sanitize desc for filename
                    safe_desc_filename = re.sub(r'[^\w\s-]', '', desc.lower())
                    safe_desc_filename = re.sub(r'[-\s]+', '_', safe_desc_filename).strip('_')
                    if not safe_desc_filename: safe_desc_filename = "failed_action"

                    failure_screenshot_path = f"failure_{safe_desc_filename}_step_{step_idx + 1}.png"
                    await page.screenshot(path=failure_screenshot_path)
                    print(f"Screenshot of failure saved to {failure_screenshot_path}")

                    # --- Human-in-the-Loop Intervention ---
                    while True:
                        print("\n--- Human Intervention Required ---")
                        print(f"The automation failed at Step {step_idx + 1}: Action '{action}' on '{desc}'.")
                        print(f"A screenshot of the current page is saved at: {failure_screenshot_path}")
                        print("Options:")
                        print(" 1. Provide a new Playwright selector (e.g., '#myButton', 'input[name=\"username\"]')")
                        print(" 2. Provide a new natural language description for the element")
                        print(" 3. Skip this step")
                        print(" 4. Exit automation")
                        
                        user_choice = input("Enter your choice (1/2/3/4): ").strip()

                        if user_choice == '1':
                            new_selector = input("Enter the new Playwright selector: ").strip()
                            if new_selector:
                                print(f"Attempting to retry with new selector: '{new_selector}'")
                                retry_success = await try_selectors(page, [new_selector], action, selector_description_for_debug=desc, value=value)
                                if retry_success:
                                    print("Retry successful! Continuing automation.")
                                    break # Exit human intervention loop
                                else:
                                    print("Retry with provided selector failed. Please try again.")
                            else:
                                print("No selector provided. Please enter a valid selector.")
                        elif user_choice == '2':
                            new_description = input("Enter a new natural language description for the element: ").strip()
                            if new_description:
                                new_selectors = infer_generic_selectors(new_description)
                                if not new_selectors:
                                    print("Could not infer selectors from the new description. Please try a different description or a direct selector.")
                                    continue # Go back to choice menu
                                print(f"Attempting to retry with new description '{new_description}' (inferred selectors: {new_selectors})")
                                retry_success = await try_selectors(page, new_selectors, action, selector_description_for_debug=new_description, value=value)
                                if retry_success:
                                    print("Retry successful! Continuing automation.")
                                    break # Exit human intervention loop
                                else:
                                    print("Retry with new description failed. Please try again.")
                            else:
                                print("No description provided. Please enter a valid description.")
                        elif user_choice == '3':
                            print("Skipping this step and continuing with the next action.")
                            break # Exit human intervention loop
                        elif user_choice == '4':
                            print("Exiting automation as requested by human.")
                            await browser.close()
                            return # Exit the function
                        else:
                            print("Invalid choice. Please enter 1, 2, 3, or 4.")
                    # End of while loop for human intervention
            
            elif action == "scroll":
                to = step.get("to")
                scroll_desc = step.get("selector_description") # Optional for element-specific scroll
                if to == "bottom":
                    if scroll_desc:
                        selectors = infer_generic_selectors(scroll_desc)
                        if selectors:
                            try:
                                # Prioritize scrolling the specific element if found
                                element = await page.wait_for_selector(selectors[0], state='attached', timeout=5000)
                                await element.evaluate("el => el.scrollTop = el.scrollHeight")
                                print(f"Scrolled element '{scroll_desc}' to bottom.")
                            except Exception as e:
                                print(f"Could not find or scroll element '{scroll_desc}': {e}. Attempting full page scroll.")
                                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                print("Scrolled page to bottom.")
                        else:
                            print(f"Could not infer selectors for scroll target '{scroll_desc}'. Scrolling full page to bottom.")
                            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            print("Scrolled page to bottom.")
                    else:
                        # Default to scrolling the entire page if no specific element is described
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        print("Scrolled page to bottom.")
                elif to == "top":
                    if scroll_desc:
                        selectors = infer_generic_selectors(scroll_desc)
                        if selectors:
                            try:
                                # Prioritize scrolling the specific element if found
                                element = await page.wait_for_selector(selectors[0], state='attached', timeout=5000)
                                await element.evaluate("el => el.scrollTop = 0")
                                print(f"Scrolled element '{scroll_desc}' to top.")
                            except Exception as e:
                                print(f"Could not find or scroll element '{scroll_desc}': {e}. Attempting full page scroll.")
                                await page.evaluate("window.scrollTo(0, 0)")
                                print("Scrolled page to top.")
                        else:
                            print(f"Could not infer selectors for scroll target '{scroll_desc}'. Scrolling full page to top.")
                            await page.evaluate("window.scrollTo(0, 0)")
                            print("Scrolled page to top.")
                    else:
                        # Default to scrolling the entire page if no specific element is described
                        await page.evaluate("window.scrollTo(0, 0)")
                        print("Scrolled page to top.")
                else:
                    print(f"Invalid scroll direction: '{to}'. Skipping scroll action.")

            elif action == "screenshot":
                name = step.get("name", f"screenshot_{step_idx + 1}.png")
                try:
                    await page.screenshot(path=name)
                    print(f"Screenshot saved as {name}")
                except Exception as e:
                    print(f"Failed to take screenshot {name}: {e}")
            else:
                print(f"Unknown action: {action}, skipping.")
        
        print("\n--- Automation Finished ---")
        if extracted_data:
            print("\nExtracted Data:")
            print(json.dumps(extracted_data, indent=2))

        await browser.close()


# --- Main execution block ---
async def main():
    while True:
        user_prompt = input("Enter your automation instruction (e.g., 'Navigate to example.com, click on the 'About Us' link'):\nOr type 'exit' to quit.\n> ").strip()
        if user_prompt.lower() == 'exit':
            print("Exiting program.")
            break
        await run_automation(user_prompt)

if __name__ == "__main__":
    asyncio.run(main())