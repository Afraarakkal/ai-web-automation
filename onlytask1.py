import asyncio
import json
import re
import os
from playwright.async_api import async_playwright

# Import the Google Generative AI library
import google.generativeai as genai

# --- AI Model Configuration ---
# Use the same model as specified in your existing script
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


# --- Helper function to infer generalized selectors ---

def infer_generic_selectors(description: str) -> list[str]:
    """
    Infers a list of potential Playwright selectors based on a natural language description.
    This function is designed to be flexible and catch common patterns.
    """
    description = description.lower()
    selectors = []

    # --- Specific enhancements for "search bar" and "search button" ---
    if 'search bar' in description or 'search input' in description or 'search box' in description:
        # Prioritize Amazon's specific search bar ID if it's the current context
        # (Heuristic: not perfect but often useful if the user starts on Amazon)
        if "amazon.in" in description or "amazon.com" in description or "amazon" in os.getenv("CURRENT_URL", "").lower():
             selectors.append("#twotabsearchtextbox") # Amazon's main search bar ID
        
        # General search input selectors
        selectors += [
            "input[type='search']", # HTML5 search input type
            "input[placeholder*='search']", # Placeholder containing 'search'
            "input[aria-label*='search']", # ARIA label containing 'search'
            "input[name*='search']", # Name attribute containing 'search'
            "input#search",          # Common ID for search input
            "input.search-input",    # Common class for search input
            "div.nav-search-field input", # Amazon specific path for search input (common)
            "input[role='searchbox']", # Common ARIA role for search inputs
            "form[role='search'] input" # Input inside a search form
        ]
    elif 'search button' in description or 'submit search' in description or 'search icon' in description:
        # General search button selectors
        selectors += [
            "button:has-text('Search')",
            "input[type='submit'][value*='Search']",
            "button[aria-label*='Search']",
            "a[aria-label*='Search']", # Sometimes search buttons are links
            "button#search-button", # Common ID for search button
            "button.search-submit", # Common class for search button
            "button[type='submit'][data-csa-c-type='widget']", # Amazon specific button type
            ".nav-search-submit input[type='submit']", # Amazon specific search submit button
            "div.nav-search-submit input[type='submit']" # Another Amazon specific selector
        ]
        # Include general button selectors as fallback
        selectors += ['button', 'input[type=submit]', '[role="button"]']


    if 'navbar' in description or 'navigation' in description:
        selectors += ['nav', '[role="navigation"]', '.navbar']

    if 'button' in description:
        match = re.search(r'button(?: labeled| with text)? \'?\"?([^\']+)\'?\"?', description)
        if match:
            label = match.group(1)
            # Prioritize exact text match, then value, name, and ARIA label
            selectors += [
                f"button:has-text('{label}')",
                f"input[type=submit][value*='{label}']",
                f"button[name*='{label}']", 
                f"*[aria-label*='{label}'][role='button']"
            ]
        else:
            selectors += ['button', 'input[type=submit}', '[role="button"]']

    if 'product' in description or 'item' in description or 'list' in description:
        # Generic product/item selectors
        selectors += [
            'section.products',
            'div:has-text("Products")',
            'ul.products-list',
            'li.product-item',
            '[data-product-id]', # Common attribute for product elements
            '[data-product-name]', 
            '.product-card', # Common class for product cards
            '.item-card',
            f"text='{description}'" # Direct text match as a fallback
        ]

    if 'link' in description or 'menu item' in description or 'tab' in description:
        match = re.search(r'(?:link|menu item|tab) ?\'?\"?([^\']+)\'?\"?', description)
        if match:
            text = match.group(1)
            # Prioritize exact text matches for links/menu items
            selectors += [
                f"a:has-text('{text}')",
                f"nav a:has-text('{text}')",
                f"li a:has-text('{text}')",
                f"div[role='tab']:has-text('{text}')",
                f"button:has-text('{text}')[role='link']", # Sometimes buttons act as links
            ]
        selectors += ['a', 'nav a', 'li a', '[role="tab"]'] # Fallbacks

    if 'cart' in description:
        selectors += ['div.cart-item', 'li.cart-item', '#cart', '[aria-label="cart"]', '.cart-icon', '.shopping-cart', 'a:has-text("Cart")', 'button:has-text("Cart")']

    if 'modal' in description or 'dialog' in description:
        selectors += ['div[role="dialog"]', '.modal', '.dialog', '[aria-modal="true"]', '#modal']
    
    if 'text input' in description or 'input field' in description:
        # This block will now run AFTER the specific search bar logic
        # if the description is general (e.g., "email input")
        match = re.search(r'(?:text input|input field)(?: labeled| with text| named)? \'?\"?([^\']+)\'?\"?', description)
        if match:
            label = match.group(1)
            # Look for placeholders, associated labels, or ARIA labels
            selectors += [
                f"input[placeholder*='{label}']",
                f"label:has-text('{label}') + input",
                f"input[aria-label*='{label}']",
                f"*[name*='{label}'][type='text']", # Match by name attribute
                f"*[id*='{label}'][type='text']",    # Match by ID attribute
            ]
        # General text input selectors if no specific label found
        selectors += ['input[type="text"]', 'textarea', 'input:not([type="submit"]):not([type="button"]):not([type="checkbox"]):not([type="radio"])']


    # Fallback to direct text or partial text match if no specific selectors were inferred
    # Ensure this is always added as a last resort
    selectors.append(f"text='{description}'")
    selectors.append(f":has-text('{description}')")

    # Remove duplicates while preserving order
    seen = set()
    result = []
    for sel in selectors:
        if sel not in seen:
            seen.add(sel)
            result.append(sel)

    return result


# --- AI function using Gemini ---

async def get_instructions_from_ai(prompt: str) -> dict:
    """
    Sends the user's natural language instruction to the Gemini model
    and expects a JSON array of actions for web automation.
    """
    try:
        # Crucial for structured output: instruct the model to produce JSON
        # Emphasize that the AI should only produce actions based on the prompt.
        system_instruction = (
            "You are an AI assistant that converts user instructions into a JSON array of actions for web automation. "
            "Each action in the array should be a JSON object with an 'action' key and relevant parameters. "
            "Only generate actions explicitly requested or implied by the user's prompt. "
            "Do not add additional actions not specified by the user.\n\n"
            "- For **'navigate'** action: `{\"action\": \"navigate\", \"url\": \"<URL_TO_NAVIGATE_TO>\"}`\n"
            "- For **'click'**, **'wait'**, and **'assert'** actions: `{\"action\": \"<action_type>\", \"selector_description\": \"<NATURAL_LANGUAGE_DESCRIPTION_OF_ELEMENT>\"}`\n"
            "- For **'type'** action (filling text into an input): `{\"action\": \"type\", \"selector_description\": \"<NATURAL_LANGUAGE_DESCRIPTION_OF_INPUT_FIELD>\", \"value\": \"<TEXT_TO_TYPE>\"}`\n"
            "- For **'screenshot'** action: `{\"action\": \"screenshot\", \"name\": \"<FILENAME.png>\"}`\n\n"
            "If the user provides a starting URL, ensure the first action is 'navigate' to that URL. "
            "If the user only gives actions without an explicit URL, assume the actions start from the current page and do not generate a 'navigate' action unless specifically instructed.\n\n"
            "Example JSON output: "
            '`{"actions": [{"action": "navigate", "url": "https://example.com"}, {"action": "type", "selector_description": "username input field", "value": "myuser"}, {"action": "click", "selector_description": "Sign In button"}, {"action": "screenshot", "name": "final_page.png"}]}`'
        )

        print("Sending instruction to Gemini for action planning...")
        response = await gemini_model.generate_content_async( # Corrected: using async version
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

async def try_selectors(page, selectors, action_type, value=None, timeout=15000): # Increased timeout for robustness
    """
    Attempts to perform a Playwright action using a list of selectors in order,
    stopping at the first successful attempt.
    """
    for sel in selectors:
        try:
            # Wait for the element to be visible before interacting
            await page.wait_for_selector(sel, state='visible', timeout=timeout)

            if action_type == 'click':
                await page.click(sel)
                print(f"Successfully clicked using selector: {sel}")
                return True
            elif action_type == 'wait':
                # The wait_for_selector already fulfills the 'wait' action
                print(f"Successfully waited for element using selector: {sel}")
                return True
            elif action_type == 'assert':
                # The wait_for_selector already fulfills the 'assert' action (presence and visibility)
                print(f"Successfully asserted element presence using selector: {sel}")
                return True
            elif action_type == 'type':
                await page.fill(sel, value)
                print(f"Successfully typed '{value}' into selector: {sel}")
                return True
            # Add more actions here if needed (e.g., hover, scroll)
        except Exception as e:
            # print(f"Selector '{sel}' failed for action '{action_type}': {e}") # Uncomment for more verbose debugging
            continue # Try the next selector

    print(f"All selectors failed for action '{action_type}'.")
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
        browser = await p.chromium.launch(headless=False)  # Set to True for silent execution
        page = await browser.new_page()

        for step in actions:
            action = step.get("action")

            if action == "navigate":
                url = step.get("url")
                if url:
                    # Store the current URL in an environment variable for heuristics in infer_generic_selectors
                    os.environ["CURRENT_URL"] = url 
                    print(f"Navigating to {url}")
                    try:
                        await page.goto(url, wait_until='domcontentloaded') # Wait until DOM is loaded
                    except Exception as e:
                        print(f"Failed to navigate to {url}: {e}")
                        break # Stop automation if navigation fails
                else:
                    print("Navigation action missing URL, skipping.")

            elif action in ("click", "wait", "assert"):
                desc = step.get("selector_description")
                if not desc:
                    print(f"Missing selector_description for action {action}, skipping.")
                    continue

                selectors = infer_generic_selectors(desc)
                print(f"Attempting to '{action}' on: '{desc}' using selectors: {selectors}")

                success = await try_selectors(page, selectors, action)
                if not success:
                    print(f"Critical: Failed to {action} on '{desc}'. Automation stopping.")
                    # Take a screenshot on failure for debugging
                    await page.screenshot(path=f"failure_{action}_{desc.replace(' ', '_').replace('/', '_')}.png")
                    break # Stop automation on critical failure

            elif action == "type":
                desc = step.get("selector_description")
                value = step.get("value")
                if not desc or value is None:
                    print(f"Missing selector_description or value for action {action}, skipping.")
                    continue
                
                selectors = infer_generic_selectors(desc)
                print(f"Attempting to '{action}' '{value}' into: '{desc}' using selectors: {selectors}")

                success = await try_selectors(page, selectors, action, value=value)
                if not success:
                    print(f"Critical: Failed to {action} '{value}' into '{desc}'. Automation stopping.")
                    await page.screenshot(path=f"failure_{action}_{desc.replace(' ', '_').replace('/', '_')}.png")
                    break # Stop automation on critical failure

            elif action == "screenshot":
                filename = step.get("name", "screenshot.png")
                # Ensure a valid filename (remove problematic characters)
                filename = re.sub(r'[^\w\-. ]', '_', filename)
                print(f"Taking screenshot: {filename}")
                try:
                    await page.screenshot(path=filename)
                except Exception as e:
                    print(f"Failed to take screenshot {filename}: {e}")

            else:
                print(f"Unknown action '{action}', skipping.")

        print("Automation sequence finished.")
        await browser.close()


# --- Entry point ---

if __name__ == "__main__":
    print("\n--- Flexible AI-Powered Web Automation ---")
    print("This script uses Playwright for browser interaction and Google Gemini for understanding your instructions.")
    print("Ensure you have Playwright browsers installed (`playwright install`) and your GEMINI_API_KEY environment variable set.")

    # Get user input for the starting URL
    start_url_input = input("\nEnter the STARTING URL (e.g., https://www.example.com, or leave blank if your prompt includes navigation):\n> ").strip()
    
    # Get user input for the AI prompt
    ai_prompt_input = input("\nEnter your NATURAL LANGUAGE INSTRUCTION for the AI (e.g., 'Go to the login page, type \"user@example.com\" in the email field, \"mypassword\" in the password field, and click the \"Sign In\" button. Then take a screenshot of the dashboard called \"dashboard.png\".'):\n> ").strip()

    # Combine the URL with the AI prompt. The AI's system instruction will handle
    # adding a 'navigate' action if the URL is provided separately.
    if start_url_input:
        # Add the URL to the prompt to guide the AI's first action
        full_instruction_for_ai = f"First, navigate to \"{start_url_input}\".\n{ai_prompt_input}"
    else:
        full_instruction_for_ai = ai_prompt_input

    # Run the asynchronous automation
    asyncio.run(run_automation(full_instruction_for_ai))