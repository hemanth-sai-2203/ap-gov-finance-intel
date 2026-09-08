import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

print(f"API Key present: {bool(api_key)}, Length: {len(api_key) if api_key else 0}")

try:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    
    # Try gemini-1.5-flash or gemini-2.0-flash
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("Hello! What is 2 + 2? Answer in one word.")
    print("\n[SUCCESS] Gemini 1.5 Flash Response:")
    print(response.text)
except Exception as e:
    print(f"\n[NOTICE] google.generativeai error: {e}")

try:
    from google import genai as genai_v2
    client = genai_v2.Client(api_key=api_key)
    res2 = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Hello! Confirm connection in 3 words."
    )
    print("\n[SUCCESS] Gemini 2.5 Flash Response:")
    print(res2.text)
except Exception as e:
    print(f"\n[NOTICE] google-genai error: {e}")
