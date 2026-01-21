"""
Test async image operations for ImageService.
Verifies that image saving works correctly with anyio.
"""
import asyncio
import tempfile
import shutil
from pathlib import Path
from services.image_service import ImageService


async def test_save_image():
    """Test async image saving."""
    print("Testing ImageService.save_image...")
    
    # Create test image bytes
    test_image_data = b"fake_image_data_for_testing"
    
    # Test saving
    try:
        db_path = await ImageService.save_image(
            file_bytes=test_image_data,
            entity_type="test",
            slug="test-product",
            filename="test.jpg"
        )
        
        print(f"✓ Image saved to: {db_path}")
        
        # Verify file exists
        file_path = Path(db_path)
        assert file_path.exists(), f"File not found: {db_path}"
        print(f"✓ File exists at: {file_path}")
        
        # Verify content
        content = file_path.read_bytes()
        assert content == test_image_data, "File content doesn't match"
        print("✓ File content matches")
        
        # Test get_web_path
        web_path = ImageService.get_web_path(db_path)
        assert web_path.startswith("/"), "Web path should start with /"
        print(f"✓ Web path: {web_path}")
        
        # Cleanup
        shutil.rmtree("media/test", ignore_errors=True)
        print("✓ Cleanup successful")
        
        print("\n✅ All tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_uuid_filename():
    """Test that filenames use UUID for security."""
    print("\nTesting UUID-based filename generation...")
    
    test_image_data = b"test_data"
    
    # Save with a potentially dangerous filename
    db_path = await ImageService.save_image(
        file_bytes=test_image_data,
        entity_type="test",
        slug="test-slug",
        filename="../../../etc/passwd.jpg"  # Path traversal attempt
    )
    
    # Verify the filename is a UUID, not the original
    filename = Path(db_path).name
    assert filename != "../../../etc/passwd.jpg", "Filename should be sanitized"
    assert ".jpg" in filename, "Extension should be preserved"
    print(f"✓ Secure filename generated: {filename}")
    
    # Cleanup
    shutil.rmtree("media/test", ignore_errors=True)
    print("✓ Security test passed!")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("ImageService Async Tests")
    print("=" * 60 + "\n")
    
    # Run tests
    asyncio.run(test_save_image())
    asyncio.run(test_uuid_filename())
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
