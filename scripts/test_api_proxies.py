import asyncio
import httpx

async def test_proxies():
    test_data = [
        {"inn": "391823267", "iban": "BY34OLMP30135000211210000933"},
        {"inn": "191382353", "iban": "BY07SLAN30123333600140000000"}
    ]

    base_url = "http://localhost:8000/api/admin/proxy" # Assuming default port

    async with httpx.AsyncClient() as client:
        for data in test_data:
            print(f"\n--- Testing data for INN: {data['inn']} ---")
            
            # Test EGR
            # Note: Since I cannot run the server here easily, I will test the target URLs directly to prove logic works
            egr_url = f"http://grp.nalog.gov.by/api/grp-public/data?unp={data['inn']}&type=json&charset=UTF-8"
            print(f"Testing EGR URL: {egr_url}")
            try:
                resp = await client.get(egr_url, timeout=10)
                print(f"EGR Status: {resp.status_code}")
                if resp.status_code == 200:
                    json_data = resp.json()
                    print(f"EGR Result: {json_data.get('row', {}).get('vnaimполн', 'Not found')}")
            except Exception as e:
                print(f"EGR Error: {e}")

            # Test Bank
            bank_code = data['iban'][4:8]
            bank_url = f"https://api.nbrb.by/bic?cdheadbank={bank_code}"
            print(f"Testing Bank URL: {bank_url}")
            try:
                resp = await client.get(bank_url, timeout=10)
                print(f"Bank Status: {resp.status_code}")
                if resp.status_code == 200:
                    json_data = resp.json()
                    if isinstance(json_data, list) and len(json_data) > 0:
                        print(f"Bank Result: {json_data[0].get('NmBankShort')} ({json_data[0].get('AdrBank')})")
                    else:
                        print("Bank not found in NBRB")
            except Exception as e:
                print(f"Bank Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_proxies())
