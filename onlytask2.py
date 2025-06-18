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

# --- Helper function to infer generalized selectors ---

def infer_generic_selectors(description: str) -> list[str]:
    """
    Infers a list of potential Playwright selectors based on a natural language description.
    This function is designed to be flexible and catch common patterns.
    """
    description_lower = description.lower()
    selectors = []
    current_url = os.getenv("CURRENT_URL", "").lower() # Get current URL for context
    button_text_match = None 
    input_label = None
    # --- Common Elements & Actions ---
    # Sign in/Log in buttons - generic approach
    if 'sign in' in description_lower or 'log in' in description_lower or 'login' in description_lower:
        # Prioritize visible, interactive elements that likely represent sign-in buttons
        selectors += [
            "button:has-text('Sign in')",
            "button:has-text('Log in')",
            "a:has-text('Sign in')",
            "a:has-text('Log in')",
            "[aria-label*='Sign in']",
            "[aria-label*='Log in']",
            "[data-testid*='login-button']",  # Common test ID pattern
            "[data-tracking*='login']",  # Common analytics tracking pattern
            ".login-button",  # Common class name
            ".signin-button",
            "[role='button']:has-text('Sign in')",  # For accessible buttons
            "input[value*='Sign in'][type='submit']",  # Submit buttons
            "input[value*='Log in'][type='submit']",
            "nav a:has-text('Sign in')",  # In navigation
            "header a:has-text('Sign in')",  # In header
            "#login-button",  # Common ID
            "#signin-button",
            "button[type='button']:has-text('Sign in')",
            "a[href*='login']",  # Links containing login
            "a[href*='signin']",
            "a[href*='auth']",  # Common auth paths
        ]

        # Add variations with different capitalizations
        selectors += [
            "button:has-text('Sign In')",
            "button:has-text('Log In')",
            "a:has-text('Sign In')",
            "a:has-text('Log In')",
        ]

        # Add language variations
        selectors += [
            "button:has-text('Se connecter')",  # French
            "button:has-text('Anmelden')",  # German
            "button:has-text('Iniciar sesión')",  # Spanish
        ]
    
    # Search bar/input field
    if 'search bar' in description_lower or 'search input' in description_lower or 'search box' in description_lower:
        if "amazon.in" in current_url or "amazon.com" in current_url:
            selectors.append("#twotabsearchtextbox") # Amazon's main search bar ID
        selectors += [
            "input[type='search']",
            "input[placeholder*='search']",
            "input[aria-label*='search']",
            "input[name*='search']",
            "input#search",
            "input.search-input",
            "div.nav-search-field input", # Amazon specific
            "input[role='searchbox']",
            "form[role='search'] input",
            "input[type='text'][name*='q']", # Common for search query
            "input.query-input",
        ]
    # Search button
    elif 'search button' in description_lower or 'submit search' in description_lower or 'search icon' in description_lower:
        if "amazon.in" in current_url or "amazon.com" in current_url:
            selectors += [".nav-search-submit input[type='submit']", "button[type='submit'][data-csa-c-type='widget']"]
        selectors += [
            "button:has-text('Search')",
            "input[type='submit'][value*='Search']",
            "button[aria-label*='Search']",
            "a[aria-label*='Search']",
            "button#search-button",
            "button.search-submit",
            "button[type='submit']",
            "input[type='submit']",
            "[role='button']:has-text('Search')",
            "i.search-icon", # Common for icon-only search buttons
            "button.search-icon",
        ]

    # --- Sorting/Filtering/Dropdowns ---
    elif 'filter by' in description_lower or 'sort by' in description_lower or 'order by' in description_lower or 'cost high to low' in description_lower or 'price' in description_lower:
        if 'dropdown' in description_lower or 'select' in description_lower or 'option' in description_lower:
            selectors += [
                "select[aria-label*='sort']",
                "select[name*='sort']",
                "select[id*='sort']",
                "select.sort-by",
                "select",
                "div[role='combobox'][aria-haspopup='listbox']", # Common pattern for accessible custom dropdowns
                "button:has-text('Sort by')", # If the dropdown is opened by a button
                "a:has-text('Sort by')",    # If the dropdown is a link
                "span:has-text('Sort by') ~ select", # If the label is a span next to the select
                "div.select-wrapper select", # Common wrapper class
                "div.dropdown-menu-button", # Generic dropdown trigger
                "label:has-text('Sort by') + select", # Label preceding a select
            ]
            
            # Extract the specific option text from the description if present
            # e.g., "Sort by 'Price: High to Low'"
            option_match = re.search(r"'(.*?)'", description)
            option_text = option_match.group(1) if option_match else description.replace("sort by ", "").strip()

            if option_text:
                selectors += [
                    f"option:has-text('{option_text}')",
                    f"option[label='{option_text}']",
                    f"option[value*='{option_text.lower().replace(' ', '_')}']", # for values like price_desc
                    f"option[value*='{option_text.lower().replace(' ', '')}']", # for values like pricehightolow
                    f"div[role='option']:has-text('{option_text}')", # for custom dropdowns
                    f"a:has-text('{option_text}')", # for custom dropdowns where options are links
                    f"button:has-text('{option_text}')", # for custom dropdowns where options are buttons
                ]
        # General price/cost related options that might not be in a dropdown directly
        price_sort_keywords = ["price", "cost", "high to low", "low to high", "descending", "ascending"]
        for keyword in price_sort_keywords:
            if keyword in description_lower:
                selectors += [
                    f"button:has-text('{description}')", 
                    f"a:has-text('{description}')",
                    f"button:has-text('{keyword}')",
                    f"a:has-text('{keyword}')",
                    f"*[aria-label*='{keyword}'][role='button']",
                    f"*[aria-label*='{keyword}'][role='link']",
                    f".sort-option:has-text('{description}')", 
                    f".filter-option:has-text('{description}')",
                ]
        # Add general text-based selector for the dropdown if no specific element is inferred
        if 'dropdown' in description_lower:
            selectors.append(f"text='{description.replace('dropdown', '').strip()}'")


    # --- Brand/Filter Checkboxes/Links ---
    # --- Brand/Filter Checkboxes/Links ---
    # This section is generally for any type of filter, including checkboxes.
    # We can generalize the text extraction for checkboxes here.
    elif 'brand' in description_lower or 'filter by brand' in description_lower or 'checkbox' in description_lower or 'terms' in description_lower or 'agree' in description_lower:
        # Extract the specific name/label from the description for the checkbox/filter
        # e.g., "checkbox labeled 'Boat'" or "click 'I agree to terms'"
        # Use a more generic regex to capture the label for checkboxes/links
        
        # Priority 1: Text within single quotes (e.g., 'Boat', 'I agree to the terms')
        label_match = re.search(r"'(.*?)'", description_lower)
        extracted_label_text = label_match.group(1).strip() if label_match else None

        # Priority 2: Common checkbox phrases if no quoted text was found
        if not extracted_label_text:
            if 'checkbox for' in description_lower:
                match = re.search(r"checkbox for\s*(.*?)(?:\s+in|\s+section)?", description_lower)
                if match: extracted_label_text = match.group(1).strip()
            elif 'checkbox labeled' in description_lower:
                match = re.search(r"checkbox labeled\s*(.*?)(?:\s+in|\s+section)?", description_lower)
                if match: extracted_label_text = match.group(1).strip()
            # Add more common phrases if needed, e.g., "accept terms", "subscribe to newsletter"

        # Priority 3: Infer common 'terms' or 'agree' texts if keywords are present but no specific label found
        if not extracted_label_text and ('terms' in description_lower or 'agree' in description_lower):
            if 'agree to the terms' in description_lower:
                extracted_label_text = 'agree to the terms'
            elif 'terms and conditions' in description_lower:
                extracted_label_text = 'terms and conditions'
            # Add more specific common terms related to checkboxes if necessary

        # Now, use the extracted_label_text for generating selectors
        if extracted_label_text:
            # Selectors for a checkbox/radio button labeled with extracted_label_text
            selectors += [
                f"input[type='checkbox'][value*='{extracted_label_text}']",
                f"input[type='radio'][value*='{extracted_label_text}']",
                f"label:has-text('{extracted_label_text}') input[type='checkbox']", # checkbox with adjacent label
                f"label:has-text('{extracted_label_text}') input[type='radio']",
                f"div.a-checkbox:has-text('{extracted_label_text}') input", # Amazon-specific checkbox
                f"span.a-checkbox-label:has-text('{extracted_label_text}') input", # Another Amazon-specific checkbox
                f"input[type='checkbox'][aria-label*='{extracted_label_text}']",
                f"input[type='radio'][aria-label*='{extracted_label_text}']",
                
                # --- NEW/IMPROVED SELECTORS FOR CHECKBOXES ---
                # XPath to find a checkbox associated with a label containing the text
                f"//label[contains(., '{extracted_label_text}')]/input[@type='checkbox']", 
                # Find a checkbox input that is a descendant of a div containing the text
                f"div:has-text('{extracted_label_text}') input[type='checkbox']",
                # Find a checkbox input that is a descendant of a span containing the text
                f"span:has-text('{extracted_label_text}') input[type='checkbox']",
            ]
            
            # Selectors for a link/button representing a brand filter (these still use brand_name contextually)
            # We keep these separate because they are specifically for links/buttons, not necessarily checkboxes.
            # If the extracted_label_text is used for a "brand" context, these apply.
            selectors += [
                f"a:has-text('{extracted_label_text}')",
                f"button:has-text('{extracted_label_text}')",
                f"div.s-navigation-item-label:has-text('{extracted_label_text}') a", # Amazon-specific link
                f"li:has-text('{extracted_label_text}') a", # Link within a list item
                f"[data-csa-c-content-id*='{extracted_label_text}']", # Common data attribute for filters
                f".brand-name:has-text('{extracted_label_text}')", # Common class for brand names
            ]
        
        # General brand filter section selectors (if description is less specific)
        # These are usually for finding the *section* itself, not a specific checkbox within it.
        # It's fine for these to remain somewhat generic.
        selectors += [
            "div.s-filters div.s-card-border:has-text('Brand')", # Amazon-like brand filter section
            "section:has-text('Brand')",
            "#brandsRefinements", # Common ID for brand filter sections
            ".brand-filter-section",
            ".s-navigation-group:has-text('Brand')", # Another Amazon-specific navigation group
            "[aria-label*='Brand filter']",
            "h3:has-text('Brand') + div", # Section title followed by filter options
            "h2:has-text('Brand') + div",
        ]
        
        # Fallback if only 'checkbox' is mentioned without a specific label (and no label was extracted)
        # This will add generic checkbox selectors if no specific text was identified
        if 'checkbox' in description_lower and not extracted_label_text:
            selectors += ["input[type='checkbox']", "[role='checkbox']"]


    # --- Extracting Information Selectors ---
    elif 'product title' in description_lower:
        selectors += [
            ".product-title", ".product__title", "h1.title", "h2.product-name",
            "[data-test='product-title']", "a.product-link",
            "span[itemprop='name']", "h3.item-name",
            ".a-color-base.a-text-normal", # Amazon specific search result titles
            "a.a-link-normal.a-text-normal", # Another Amazon specific for links with titles
        ]
        selectors.append(".product-grid .product-title")
        selectors.append(".product-list .product-title")
        selectors.append(".s-main-result .s-title-instructions") # Amazon search result title
        
    elif 'product price' in description_lower or 'item price' in description_lower:
        selectors += [
            ".price", ".product-price", "span.price", "div.price",
            "[data-test='product-price']",
            "span[itemprop='price']", "span[data-a-color='price']",
            "span.final-price", ".offer-price",
            ".a-price-whole", ".a-price-fraction", ".a-price-symbol", # Amazon price parts
            ".a-offscreen", # Sometimes prices are hidden for accessibility
        ]
        selectors.append(".product-grid .price")
        selectors.append(".product-list .price")
        selectors.append(".s-main-result .a-price") # Amazon search result price
        
    elif 'product description' in description_lower:
        selectors += [
            ".product-description", "#product-description", "div.description",
            "div[itemprop='description']", ".details-content",
            "#feature-bullets", "#productDescription", # Amazon specific
            ".product-specs", ".item-details",
        ]
    elif 'image' in description_lower:
        selectors += [
            "img[alt*='product']", "img.product-image", ".product-gallery img",
            "img[role='img']", "img[srcset]",
            "img.s-image", # Amazon search result images
        ]
    elif 'review' in description_lower:
        selectors += [
            ".review-text", ".customer-review", ".review-body",
            "[data-hook='review-body']", # Amazon specific
            ".cr-review-text", ".review-comment",
        ]
    elif 'all' in description_lower and ('products' in description_lower or 'items' in description_lower):
        selectors += [
            ".s-main-result", # Amazon search results container
            ".product-grid .product-card", 
            ".product-list .product-item",
            "[data-asin]", "[data-item-id]", # Common e-commerce item attributes
            ".product-tile", ".search-result-item",
            ".item-cell", ".grid-item",
        ]

    # --- Navigation & General Interaction ---
    if 'navbar' in description_lower or 'navigation' in description_lower:
        selectors += ['nav', '[role="navigation"]', '.navbar', '#main-navigation', '.header-nav']

    if 'link' in description_lower or 'menu item' in description_lower or 'tab' in description_lower:
        match = re.search(r'(?:link|menu item|tab|go to) ?\'?\"?([^\']+)\'?\"?', description_lower)
        if match:
            text = match.group(1)
            selectors += [
                f"a:has-text('{text}')",
                f"nav a:has-text('{text}')",
                f"li a:has-text('{text}')",
                f"div[role='tab']:has-text('{text}')",
                f"button:has-text('{text}')[role='link']", 
                f"[aria-label*='{text}'][role='link']",
                f"link[rel='{text}']", # For actual link tags
            ]
        selectors += ['a', 'nav a', 'li a', '[role="tab"]'] 

    if 'button' in description_lower:
        # Improved button text extraction
        button_text_match = re.search(r'button(?: labeled| with text)?\s*\'?\"?([^\']+)\'?\"?', description_lower)
        button_text = button_text_match.group(1) if button_text_match else None

        if button_text:
            selectors += [
                f"button:has-text('{button_text}')",
                f"input[type=submit][value*='{button_text}']",
                f"button[name*='{button_text}']", 
                f"*[aria-label*='{button_text}'][role='button']",
                f"a[role='button']:has-text('{button_text}')", # link styled as button
                f"button[aria-label*='{button_text}']"
                
 
            ]
        else: # Generic button selectors if no specific text is found
            selectors += ['button', 'input[type=submit}', '[role="button"]']

    if 'cart' in description_lower or 'checkout' in description_lower or 'add to cart' in description_lower:
        selectors += [
            'div.cart-item', 'li.cart-item', '#cart', '[aria-label="cart"]', '.cart-icon', '.shopping-cart',
            'a:has-text("Cart")', 'button:has-text("Cart")',
            'a:has-text("Checkout")', 'button:has-text("Checkout")',
            '#add-to-cart-button', '.add-to-cart', 'button:has-text("Add to Cart")',
        ]

    if 'modal' in description_lower or 'dialog' in description_lower or 'popup' in description_lower:
        selectors += ['div[role="dialog"]', '.modal', '.dialog', '[aria-modal="true"]', '#modal', '.popup', '[data-modal-id]']
    
    # Inside infer_generic_selectors function

# --- Text Input Fields (username, email, password, general textboxes) ---
    if 'input field' in description_lower or 'textbox' in description_lower or 'input' in description_lower:
        input_label = None # Initialize to None

    # 1. Try to extract exact quoted text (e.g., 'First name', 'Email address')
    label_match_quoted = re.search(r"'(.*?)' (?:input|text)?(?:field|box)", description_lower)
    if label_match_quoted:
        input_label = label_match_quoted.group(1).strip().lower()
    else:
        # 2. Try to extract common patterns like 'email input', 'password field'
        # Note: 'Password' should be handled first due to type='password'
        common_labels = ["password", "email address", "email", "first name", "last name", "company name", "username"]
        for common_label in common_labels:
            if common_label in description_lower:
                input_label = common_label
                break

    # --- IMPORTANT: Handle password fields FIRST and with high specificity ---
        if 'password' in description_lower:
             selectors += [
            "input[type='password']", # Most specific: exact type
            "input[name*='password']", # Common name pattern
            "input[id*='password']",   # Common ID pattern
            "input[placeholder*='Password']", # Common placeholder
            "label:has-text('Password') + input[type='password']", # Label + specific type
        ]
        if 'confirm' in description_lower: # For confirm password if it exists
            selectors += [
                "input[type='password'][name*='confirm']",
                "input[type='password'][id*='confirm']",
                "input[placeholder*='Confirm Password']",
                "label:has-text('Confirm Password') + input[type='password']",
            ]
         # Important: If it's a password field, we're done here, return its specific selectors.
                        # This prevents generic selectors from being added to it.


    # --- Handle other specific input fields (First name, Last name, Email, Company) ---
    if input_label:
        # Use Playwright's `has-placeholder` which is very effective
        if input_label == 'first name':
            selectors.append("input[placeholder*='First name']")
            selectors.append("input[name*='first_name']")
            selectors.append("input[id*='first_name']")
            selectors.append("label:has-text('First name') + input")
        elif input_label == 'last name':
            selectors.append("input[placeholder*='Last name']")
            selectors.append("input[name*='last_name']")
            selectors.append("input[id*='last_name']")
            selectors.append("label:has-text('Last name') + input")
        elif input_label == 'email' or input_label == 'email address':
            selectors.append("input[type='email']") # Prioritize specific type
            selectors.append("input[placeholder*='Email address']")
            selectors.append("input[name*='email']")
            selectors.append("input[id*='email']")
            selectors.append("label:has-text('Email address') + input")
        elif input_label == 'company name':
            selectors.append("input[placeholder*='Company name']")
            selectors.append("input[name*='company']")
            selectors.append("input[id*='company']")
            selectors.append("label:has-text('Company name') + input")
        elif input_label == 'username':
            selectors.append("input[placeholder*='Username']")
            selectors.append("input[name*='username']")
            selectors.append("input[id*='username']")
            selectors.append("label:has-text('Username') + input")

        # Add a generic fallback for any extracted label that wasn't explicitly handled above
        # This should be *after* specific matches, but before truly generic inputs
        selectors.append(f"input[placeholder*='{input_label}']") # General placeholder match
        selectors.append(f"label:has-text('{input_label}') + input") # General label + input match

    # --- General / Fallback text input selectors (lowest priority) ---
    # These should only be used if no specific label was identified and matched
    if not selectors: # Only add if no specific selectors have been added yet
        selectors.append("input[type='text']") # Broadest text input type
        selectors.append("textarea")
        selectors.append("input") # Matches ANY input, should be last resort if used at all here
    # Fallback to direct text or partial text match if no specific selectors were inferred
    if not selectors or not any(s for s in selectors if not s.startswith("text=") and not s.startswith(":has-text=")):    
        # Only add generic text selectors if no more specific selectors were found
        selectors.append(f"text='{description}'")
        selectors.append(f":has-text('{description}')")
    if 'button' in description_lower:
        # Regex to capture text like 'button "TEXT"', 'button labeled "TEXT"', 'the "TEXT" button'
        # This regex is a bit more robust for various phrasings
        button_text_match = re.search(r'(?:button(?: labeled| with text)?|the)\s*\'?\"?([^\']+)\'?\"?\s*button', description_lower)
        # If the above doesn't work, try just capturing text after 'button'
        if not button_text_match:
            button_text_match = re.search(r'button\s*\'?\"?([^\']+)\'?\"?', description_lower)

        button_text = button_text_match.group(1) if button_text_match else None

        if button_text:
            # Prioritize selectors based on visible text
            selectors += [
                f"button:has-text('{button_text}')",
                f"a[role='button']:has-text('{button_text}')", # link styled as button
                f"input[type=submit][value='{button_text}']", # Exact value match for submit inputs
                f"input[type=button][value='{button_text}']", # Exact value match for button inputs
                f"*[aria-label='{button_text}'][role='button']", # Exact aria-label match
                f"button[name='{button_text}']", # Exact name match
                f"#signup-button",
                # Then exact text matches
                f"button:has-text('{button_text}')",
                f"a[role='button']:has-text('{button_text}')", 
                f"input[type=submit][value='{button_text}']", 
                 # ... and so on
            ]
            # Add partial matches if exact doesn't work, but they are less precise
            selectors += [
                f"button:has-text('{button_text.lower()}')", # Case-insensitive text
                f"button[name*='{button_text}']", # Partial name match
                f"*[aria-label*='{button_text}'][role='button']", # Partial aria-label match
                f"button[aria-label*='{button_text}']",
                f"input[type=submit][value*='{button_text}']", # Partial value match
            ]
        else: # Generic button selectors if no specific text is found
            # Ensure the typo is fixed here
            selectors += ['button', 'input[type=submit]', '[role="button"]', 'input[type=button]']

    # Your line 350 (or similar) check:
    # This specific line `if not button_text_match:` implies that if no button text was extracted,
    # you might want to add other selectors or handle that case.
    # Given the new robust text extraction, this might be less critical.
    # Ensure this block doesn't overwrite your primary button selectors.
    if not button_text_match and 'button' in description_lower: # Only if 'button' was mentioned but no text
         selectors += ['button', 'input[type=submit]', '[role="button"]', 'input[type=button]']


    # --- Input related logic ---
    # This is where your input_label would be assigned.
    # Example (adjust based on your actual code for input field recognition):
    if any(word in description_lower for word in ['input', 'field', 'text box']):
        # Attempt to extract text like "First name input field" or "Email address"
        input_label_match = re.search(r'(?:input|field|text box)\s*(?:labeled|with text)?\s*\'?\"?([^\']+)\'?\"?', description_lower)
        if not input_label_match: # Try capturing just the label if "input/field" isn't present
             input_label_match = re.search(r'\"?([^\"]+)\"?\s*(?:input|field|text box)', description_lower)

        input_label = input_label_match.group(1) if input_label_match else None

    if input_label:
        # Generate selectors for input fields based on the extracted label
        selectors += [
            f"input[placeholder*='{input_label}']",
            f"input[name*='{input_label}']",
            f"input[id*='{input_label}']",
            f"label:has-text('{input_label}') + input",
            f"input[placeholder*='{input_label.lower()}']",
            f"label:has-text('{input_label.lower()}') + input",
            f"*[aria-label*='{input_label}']",
            f"input[data-qa*='{input_label}']", # Common for QA/test automation attributes
            f"textarea[name*='{input_label}']", # Also consider textareas
            f"textarea[id*='{input_label}']"
        ]
    else:
        # Generic input selectors if no specific label is found
        selectors += [
            'input[type="text"]', 
            'input[type="email"]', 
            'input[type="password"]', 
            'textarea',
            'input' # generic input selector
        ]

    # --- Checkbox related logic ---
    if 'checkbox' in description_lower:
        checkbox_label_match = re.search(r'checkbox(?: next to| labeled)?\s*\'?\"?([^\']+)\'?\"?', description_lower)
        checkbox_label = checkbox_label_match.group(1) if checkbox_label_match else None

        if checkbox_label:
            selectors += [
                f"input[type='checkbox']:has(~ label:has-text('{checkbox_label}'))", # Checkbox with sibling label
                f"input[type='checkbox']:has-text('{checkbox_label}')", # Direct text (less common for checkboxes)
                f"label:has-text('{checkbox_label}') > input[type='checkbox']", # Checkbox inside label
                f"input[type='checkbox'][aria-label*='{checkbox_label}']",
                f"*[role='checkbox'][aria-label*='{checkbox_label}']",
                f"input[type='checkbox'][name*='{checkbox_label}']",
                f"input[type='checkbox'][id*='{checkbox_label}']"
            ]
        else:
            selectors += ["input[type='checkbox']", "[role='checkbox']"]
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
            "- For **'type'** action (filling text into an input): `{\"action\": \"type\", \"selector_description\": \"<NATURAL_LANGUAGE_DESCRIPTION_OF_INPUT_FIELD>\", \"value\": \"<TEXT_TO_TYPE>\"}`. "
            "If the user asks to 'randomly fill' a textbox, you should generate a random string (e.g., 'randomuser123', 'test@example.com', 'password123'). "
            "If the user asks to 'fill all textboxes', you should identify common types of textboxes (e.g., 'email input', 'password input', 'username input', 'name input', 'address input') and generate separate 'type' actions for each, using appropriate random values.\n"
            "- For **'click'**, **'wait'**, and **'assert'** actions: `{\"action\": \"<action_type>\", \"selector_description\": \"<NATURAL_LANGUAGE_DESCRIPTION_OF_ELEMENT>\"}`. "
            "If the user asks to 'randomly select/check all checkboxes', you should generate separate 'click' actions for each, identifying them by common descriptions (e.g., 'terms and conditions checkbox', 'newsletter opt-in checkbox').\n"        
        )

        print("Sending instruction to Gemini for action planning...")
        response = await gemini_model.generate_content_async(
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

async def try_selectors(page, selectors, action_type, value=None, timeout=15000):
    """
    Attempts to perform a Playwright action using a list of selectors in order,
    stopping at the first successful attempt.
    """
    for sel in selectors:
        try:
            # Wait for the element to be visible before interacting for click/type/select
            if action_type in ['click', 'type', 'select']:
                await page.wait_for_selector(sel, state='visible', timeout=timeout)
            # For assert/wait, just check presence, might not need to be visible for all cases
            elif action_type in ['wait', 'assert']:
                await page.wait_for_selector(sel, timeout=timeout)
            # For extract, we just need it to exist
            elif action_type == 'extract':
                    await page.wait_for_selector(sel, timeout=timeout)


            if action_type == 'click':
                await page.click(sel)
                print(f"Successfully clicked using selector: {sel}")
                return True
            elif action_type == 'wait':
                print(f"Successfully waited for element using selector: {sel}")
                return True
            elif action_type == 'assert':
                print(f"Successfully asserted element presence using selector: {sel}")
                return True
            elif action_type == 'type':
                await page.fill(sel, value)
                print(f"Successfully typed '{value}' into selector: {sel}")
                return True
            elif action_type == 'select': 
                # CRITICAL CHANGE: Try selecting by label first, then by value
                try:
                    await page.select_option(sel, label=value) # Try by visible text
                    print(f"Successfully selected option '{value}' from selector: {sel} by label.")
                    return True
                except Exception:
                    try:
                        await page.select_option(sel, value=value) # Try by value attribute
                        print(f"Successfully selected option '{value}' from selector: {sel} by value.")
                        return True
                    except Exception as inner_e:
                        # Continue to the next selector if both label and value fail for the current selector
                        # This print helps in debugging which specific selector failed for select
                        # print(f"Selector '{sel}' failed to select option '{value}' by both label and value: {inner_e}")
                        continue # Try the next selector in the list
            elif action_type == 'extract': # NEW action type handling
                # Determine if we should extract single or multiple
                if 'all ' in value.lower() or 'multiple' in value.lower() or 'list' in value.lower(): # 'value' here is the `name` field from the AI
                    elements = await page.locator(sel).all()
                    extracted_texts = []
                    for element in elements:
                        text = await element.text_content()
                        if text:
                            extracted_texts.append(text.strip())
                    print(f"Extracted multiple items for '{value}' using selector '{sel}': {extracted_texts}")
                    extracted_data[value] = extracted_texts
                else: # Assume single element extraction
                    element = await page.locator(sel).first
                    extracted_text = await element.text_content()
                    if extracted_text:
                        print(f"Extracted single item for '{value}' using selector '{sel}': {extracted_text.strip()}")
                        extracted_data[value] = extracted_text.strip()
                    else:
                        print(f"Extracted no text for '{value}' using selector '{sel}'")
                        extracted_data[value] = None
                return True # Extraction considered successful even if no text found for a single element

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
                    os.environ["CURRENT_URL"] = url  
                    print(f"Navigating to {url}")
                    try:
                        await page.goto(url, wait_until='domcontentloaded')  
                    except Exception as e:
                        print(f"Failed to navigate to {url}: {e}")
                        break  
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
                    await page.screenshot(path=f"failure_{action}_{desc.replace(' ', '_').replace('/', '_')}.png")
                    break  

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
                    break  

            elif action == "select":  
                desc = step.get("selector_description")
                value = step.get("value")
                if not desc or value is None:
                    print(f"Missing selector_description or value for action {action}, skipping.")
                    continue
                
                selectors = infer_generic_selectors(desc)
                print(f"Attempting to '{action}' option '{value}' from: '{desc}' using selectors: {selectors}")

                success = await try_selectors(page, selectors, action, value=value)
                if not success:
                    print(f"Critical: Failed to {action} option '{value}' from '{desc}'. Automation stopping.")
                    await page.screenshot(path=f"failure_{action}_{desc.replace(' ', '_').replace('/', '_')}.png")
                    break  

            elif action == "scroll":  
                scroll_to = step.get("to")
                selector_desc = step.get("selector_description") # Optional for scrolling a specific element

                if scroll_to not in ["top", "bottom"]:
                    print(f"Invalid 'to' value for scroll action: {scroll_to}. Skipping.")
                    continue

                if selector_desc:
                    selectors = infer_generic_selectors(selector_desc)
                    if not selectors:
                        print(f"Could not infer selectors for scrollable element: '{selector_desc}'. Skipping.")
                        continue
                    
                    found_element = None
                    for sel in selectors:
                        try:
                            found_element = await page.wait_for_selector(sel, state='visible', timeout=10000)
                            break
                        except Exception:
                            continue
                    
                    if found_element:
                        if scroll_to == "bottom":
                            print(f"Scrolling element '{selector_desc}' to bottom using selector: {found_element.selector}")
                            await found_element.evaluate("el => el.scrollTop = el.scrollHeight")
                        elif scroll_to == "top":
                            print(f"Scrolling element '{selector_desc}' to top using selector: {found_element.selector}")
                            await found_element.evaluate("el => el.scrollTop = 0")
                    else:
                        print(f"Failed to find element to scroll: '{selector_desc}'. Skipping.")
                else:
                    if scroll_to == "bottom":
                        print("Scrolling page to bottom.")
                        # This iteratively scrolls to handle infinite scroll loading (common)
                        last_height = await page.evaluate("document.body.scrollHeight")
                        while True:
                            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            await asyncio.sleep(2) # Wait for content to load
                            new_height = await page.evaluate("document.body.scrollHeight")
                            if new_height == last_height:
                                break
                            last_height = new_height
                        print("Reached end of scrollable content.")

                    elif scroll_to == "top":
                        print("Scrolling page to top.")
                        await page.evaluate("window.scrollTo(0, 0)")
                
                # A small pause after scroll is often useful
                await asyncio.sleep(1)  

            elif action == "extract": # NEW action type handling
                desc = step.get("selector_description")
                name = step.get("name")
                if not desc or not name:
                    print(f"Missing selector_description or name for action {action}, skipping.")
                    continue
                
                selectors = infer_generic_selectors(desc)
                print(f"Attempting to '{action}' data for '{name}' from: '{desc}' using selectors: {selectors}")

                success = await try_selectors(page, selectors, action, value=name) # Pass 'name' as value to try_selectors
                if not success:
                    print(f"Warning: Failed to {action} data for '{name}' from '{desc}'. Continuing automation.")
                    # We don't make extraction critical failure unless explicitly required

            elif action == "screenshot":
                filename = step.get("name", "screenshot.png")
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
        
        if extracted_data:
            print("\n--- Extracted Data ---")
            for key, value in extracted_data.items():
                print(f"{key}: {value}")
            print("----------------------")


# --- Entry point ---

if __name__ == "__main__":
    print("\n--- Flexible AI-Powered Web Automation ---")
    print("This script uses Playwright for browser interaction and Google Gemini for understanding your instructions.")
    print("Ensure you have Playwright browsers installed (`playwright install`) and your GEMINI_API_KEY environment variable set.")

    start_url_input = input("\nEnter the STARTING URL (e.g., https://www.example.com, or leave blank if your prompt includes navigation):\n> ").strip()
    
    # Updated example prompt to include 'extract' action
    ai_prompt_input = input("\nEnter your NATURAL LANGUAGE INSTRUCTION for the AI (e.g., 'Go to Amazon.in, search for \"headphones\", then click the search button. Sort by \"Price: High to Low\". Click the checkbox labeled \"Boat\" in the Brand filter section. Scroll to the bottom of the page. Extract all product titles and their prices. Take a screenshot of the results page called \"headphones_results.png\".'):\n> ").strip()

    if start_url_input:
        full_instruction_for_ai = f"First, navigate to \"{start_url_input}\".\n{ai_prompt_input}"
    else:
        full_instruction_for_ai = ai_prompt_input

    asyncio.run(run_automation(full_instruction_for_ai))