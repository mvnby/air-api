import httpx
import asyncio

async def test_cors():
    url = "http://localhost:8000/api/v1/health" # Assuming a health endpoint exists
    origins = [
        "https://mvn.by",
        "https://dev.mvn.by",
        "http://localhost:4321",
        "http://evil.com"
    ]
    
    print(f"Testing CORS on {url}")
    
    async with httpx.AsyncClient() as client:
        for origin in origins:
            try:
                response = await client.options(
                    url,
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "GET"
                    }
                )
                allow_origin = response.headers.get("access-control-allow-origin")
                print(f"Origin: {origin:25} | Allowed: {allow_origin == origin} | Header: {allow_origin}")
            except Exception as e:
                print(f"Error testing {origin}: {e}")

if __name__ == "__main__":
    # Note: This requires the server to be running locally
    # asyncio.run(test_cors())
    pass
