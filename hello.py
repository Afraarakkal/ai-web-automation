import google.generativeai as genai
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise Exception("GOOGLE_API_KEY not set in .env")

genai.configure(api_key=API_KEY)

def list_models():
    models = genai.list_models()  # this returns a generator
    print("Available models:")
    for model in models:  # iterate directly over the generator, no `.models` here
        print(f"- {model.name}")

if __name__ == "__main__":
    list_models()
