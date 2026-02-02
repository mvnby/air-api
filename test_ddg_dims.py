
from ddgs import DDGS
import json

def test_search():
    try:
        results = list(DDGS().images("iphone 15", max_results=5))
        print(json.dumps(results, indent=2))
    except Exception as e:
        print(e)

if __name__ == "__main__":
    test_search()
