from ddgs import DDGS
import json

print("Testing NEW ddgs library...")
try:
    with DDGS() as ddgs:
        results = list(ddgs.images("TCL Air Conditioner", max_results=3))
        print(f"Found {len(results)} images.")
        print(json.dumps(results[:1], indent=2))
except Exception as e:
    print(f"Error: {e}")
