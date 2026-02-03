import json
import os
import sys

# Add project root to sys.path so we can import main
sys.path.append(os.getcwd())

from main import app

def extract():
    print("Extracting OpenAPI schema...")
    try:
        schema = app.openapi()
        with open("openapi.json", "w") as f:
            json.dump(schema, f, indent=2)
        print("Schema saved to openapi.json")
    except Exception as e:
        print(f"Error extracting schema: {e}")
        sys.exit(1)

if __name__ == "__main__":
    extract()
