import sys
import os
import asyncio
# Add current dir to sys.path
sys.path.append(os.getcwd())

from fastapi.testclient import TestClient
from main import app
from core.security import get_current_username

# Override auth to bypass security
app.dependency_overrides[get_current_username] = lambda: "admin"

client = TestClient(app)

def test_multi_upload():
    print("Testing multi-upload endpoint...")
    
    # Simulate 3 files
    files = [
        ('files', ('test1.jpg', b'fakecontent1', 'image/jpeg')),
        ('files', ('test2.jpg', b'fakecontent2', 'image/jpeg')),
        ('files', ('test3.jpg', b'fakecontent3', 'image/jpeg')),
    ]
    
    try:
        response = client.post("/admin/api/upload_images", files=files)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error Response: {response.text}")
            return

        json_data = response.json()
        print(f"Response Body: {json_data}")
        
        urls = json_data.get("urls", [])
        print(f"URLs count: {len(urls)}")
        
        if len(urls) == 3:
            print("SUCCESS: 3 images uploaded and processed.")
        else:
            print("FAILURE: Mismatch in uploaded count.")
            
    except Exception as e:
        print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    test_multi_upload()
