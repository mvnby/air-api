import sys
import os
import asyncio
import traceback

# Add project root to path
sys.path.append(os.getcwd())

from httpx import AsyncClient, ASGITransport
from main import app
from core.config import settings

async def verify():
    # Helper to print errors
    def log_fail(msg, resp=None):
        print(f"❌ {msg}")
        if resp:
            print(f"Status: {resp.status_code}")
            try:
                print(f"Response: {resp.json()}")
            except:
                print(f"Response: {resp.text}")

    print("--- Starting Verification ---")
    
    # We use ASGITransport to communicate with the app directly
    transport = ASGITransport(app=app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test Login
        print("\n1. Testing Login Endpoint...")
        payload = {
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD
        }
        resp = await client.post("/login/access-token", data=payload)
        
        if resp.status_code != 200:
            log_fail("Login failed", resp)
            return False
            
        data = resp.json()
        token = data.get("access_token")
        if not token:
            print("❌ No access_token in response")
            return False
            
        print("✅ Login successful. Token obtained.")
        
        # Check Cookies in client
        # httpx client stores cookies automatically
        cookies = client.cookies
        cookie_val = cookies.get("access_token")
        if cookie_val:
            print(f"✅ Cookie 'access_token' found: {cookie_val[:10]}...")
        else:
            print("❌ Cookie 'access_token' NOT found in client")
            # We might continue to see if it works anyway (header?) but goal is cookie
            return False

        # 2. Test Access with Cookie
        print("\n2. Testing Protected Endpoint with Cookie...")
        # Since we are in the same client session, cookies should be sent
        resp2 = await client.get("/api/admin/tags/filterable")
        
        if resp2.status_code != 200:
            log_fail("Protected endpoint with cookie failed", resp2)
            return False
            
        print("✅ Accessed protected endpoint via Cookie!")

    # 3. Test Access with Header (New Client)
    print("\n3. Testing Protected Endpoint with Header...")
    async with AsyncClient(transport=transport, base_url="http://test") as client2:
        resp3 = await client2.get(
            "/api/admin/tags/filterable",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if resp3.status_code != 200:
            log_fail("Protected endpoint with Header failed", resp3)
            return False
            
        print("✅ Accessed protected endpoint via Header!")

    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(verify())
        if success:
            print("\n🎉 VERIFICATION PASSED")
            sys.exit(0)
        else:
            print("\n💀 VERIFICATION FAILED")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
