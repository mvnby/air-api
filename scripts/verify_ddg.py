import asyncio
import logging
from duckduckgo_search import DDGS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_search():
    query = "Air Conditioner"
    print(f"🔍 Searching for: {query}")
    
    try:
        # Simulate the async execution used in the router
        results = await asyncio.to_thread(
            lambda: list(DDGS().images(query, max_results=5))
        )
        
        if not results:
            print("⚠️ No results returned (List is empty)")
            return False
            
        print(f"✅ Found {len(results)} images")
        for i, res in enumerate(results):
            print(f"   {i+1}. {res.get('title', 'No Title')} - {res.get('image', 'No URL')[:50]}...")
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(verify_search())
        if success:
            exit(0)
        else:
            exit(1)
    except ImportError:
        print("❌ ImportError: duckduckgo_search not found. Please install it.")
        exit(1)
