
import os
import sys
from openai import OpenAI
from dotenv import load_dotenv

# Load .env
env_path = r'c:\Users\westi\Documents\MIRO\Mirolepoisson\.env'
load_dotenv(env_path)

api_key = os.environ.get('LLM_API_KEY')
base_url = os.environ.get('LLM_BASE_URL')
model = os.environ.get('LLM_MODEL_NAME')

print(f"Testing with Model: {model}")
print(f"Base URL: {base_url}")

client = OpenAI(api_key=api_key, base_url=base_url)

messages = [
    {"role": "system", "content": "You are a helpful assistant. Respond in JSON."},
    {"role": "user", "content": "Return a JSON with a 'status' field set to 'ok'."}
]

print("\n--- Test 1: With json_object ---")
try:
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"}
    )
    print("Success!")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"Failed: {e}")

print("\n--- Test 2: Without json_object ---")
try:
    response = client.chat.completions.create(
        model=model,
        messages=messages
    )
    print("Success!")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"Failed: {e}")
