import asyncio
import sys
import difflib
from collections import Counter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

sys.path.append('.')
from core.config import settings
from models import Product
from services.spec_normalizer import KEY_MAP

# Define system keys (target keys)
SYSTEM_KEYS = set(KEY_MAP.values())

async def analyze_keys():
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("🔍 Scanning database for unmapped spec keys...")
    
    unmapped_counter = Counter()
    unmapped_examples = {} # key -> example value
    
    async with async_session() as session:
        result = await session.execute(select(Product))
        products = result.scalars().all()
        
        total_products = len(products)
        products_with_specs = 0
        
        for p in products:
            if not p.specs: continue
            products_with_specs += 1
            
            for key, val in p.specs.items():
                # 1. Check if it's already a known system key
                if key in SYSTEM_KEYS:
                    continue
                    
                # 2. Check if it's already mapped
                if key in KEY_MAP:
                    continue
                
                # 3. It's UNMAPPED!
                unmapped_counter[key] += 1
                if key not in unmapped_examples:
                    unmapped_examples[key] = val

    print(f"\n📊 Analysis Complete")
    print(f"   Total Products: {total_products}")
    print(f"   Products w/ Specs: {products_with_specs}")
    
    if not unmapped_counter:
        print("\n✨ All keys are mapped or normalized! Great job.")
        return

    print(f"\n⚠️  Found {len(unmapped_counter)} unique unmapped keys:")
    print("-" * 60)
    print(f"{'Count':<8} | {'Unmapped Key':<40} | {'Suggestion (Confidence)'}")
    print("-" * 60)
    
    # Sort by frequency (descending)
    for key, count in unmapped_counter.most_common():
        # Try to find a suggestion from known keys (Russian keys in KEY_MAP)
        # We prefer matching against the SOURCE keys (Russian) because variations likely resemble them
        # But we can also check System keys.
        
        candidates = list(KEY_MAP.keys()) + list(SYSTEM_KEYS)
        matches = difflib.get_close_matches(key, candidates, n=1, cutoff=0.6)
        
        suggestion = ""
        if matches:
            match = matches[0]
            # Calculate a rough confidence score
            ratio = difflib.SequenceMatcher(None, key, match).ratio()
            mapped_to = KEY_MAP.get(match, "[System Key]")
            suggestion = f"-> {match} ({int(ratio*100)}%)"
            
        print(f"{count:<8} | {key:<40} | {suggestion}")
        
    print("-" * 60)
    print("\n💡 Tip: Add frequent keys to `KEY_MAP` in `services/spec_normalizer.py`")

if __name__ == "__main__":
    asyncio.run(analyze_keys())
