from duckduckgo_search import DDGS
import time

print("Testing DDG Search...")
try:
    with DDGS() as ddgs:
        results = list(ddgs.images("Test Search", max_results=5))
        print(f"Found {len(results)} images.")
        for r in results:
            print(r['image'])
except Exception as e:
    print(f"Error: {e}")
