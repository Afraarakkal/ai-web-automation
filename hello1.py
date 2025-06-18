import os
import google.generativeai as genai

# Configure your API key
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

def generate_text(text_prompt):
    # Try 'gemini-1.5-flash' or 'gemini-1.5-pro'
    model = genai.GenerativeModel('gemini-1.5-flash') # <-- CHANGE THIS LINE
    response = model.generate_content(text_prompt)
    print(response.text)

generate_text("Write a short poem about spring.")