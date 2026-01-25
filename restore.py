import asyncio
import argparse
import os
import sys

# Add current directory to path so we can import services
sys.path.append(os.getcwd())

from services.backup_service import backup_service
from core.logger import logger

async def main():
    parser = argparse.ArgumentParser(description="Restore Database from Backup")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=str, help="Path to local SQL dump file")
    group.add_argument("--drive-id", type=str, help="Google Drive File ID to download and restore")
    
    parser.add_argument("--clean-db", action="store_true", help="Drop public schema before restoring (Recommended for old backups)")
    
    args = parser.parse_args()

    try:
        # Optional: Clean DB first (Drop Schema)
        if args.clean_db:
            print("⚠️ Cleaning database (Dropping schema public)...")
            backup_service.drop_public_schema()

        if args.file:
            print(f"Restoring from local file: {args.file}")
            backup_service.restore_from_file(args.file)
        elif args.drive_id:
            print(f"Restoring from Google Drive ID: {args.drive_id}")
            await backup_service.restore_from_drive(args.drive_id)
        
        print("✅ Restore completed successfully!")
    except Exception as e:
        print(f"❌ Restore failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
