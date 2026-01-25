import os
import subprocess
import logging
from datetime import datetime
from services.google_service import google_service
from core.logger import logger

BACKUP_DIR = "backups"

class BackupService:
    def __init__(self):
        self.db_user = os.getenv("POSTGRES_USER", "mvnadmin")
        self.db_password = os.getenv("POSTGRES_PASSWORD", "securepass")
        self.db_name = os.getenv("POSTGRES_DB", "air_conditioners")
        self.db_host = "db" # In docker network it is 'db'
        self.backup_folder_id = os.getenv("BACKUP_FOLDER_ID")
        
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)

    def create_dump(self) -> str:
        """
        Creates a PostgreSQL dump and saves it locally.
        Returns the absolute path to the dump file.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{self.db_name}_{timestamp}.sql"
        filepath = os.path.join(BACKUP_DIR, filename)

        # Securely pass password
        env = os.environ.copy()
        env["PGPASSWORD"] = self.db_password

        command = [
            "pg_dump",
            "-h", self.db_host,
            "-U", self.db_user,
            "-d", self.db_name,
            "-f", filepath,
            "--clean",
            "--if-exists"
        ]

        logger.info(f"Starting backup for {self.db_name}...")
        try:
            subprocess.run(command, env=env, check=True)
            logger.info(f"Backup created successfully: {filepath}")
            return filepath
        except subprocess.CalledProcessError as e:
            logger.error(f"Backup failed: {e}")
            raise Exception("Backup creation failed")

    def perform_backup(self, cleanup: bool = True):
        """
        Full backup cycle: Dump -> Upload -> Clean (optional).
        """
        if not self.backup_folder_id:
            logger.warning("BACKUP_FOLDER_ID not set. Skipping upload.")
            return

        filepath = None
        try:
            # 1. Create Dump
            filepath = self.create_dump()
            filename = os.path.basename(filepath)

            # 2. Upload to Google Drive
            logger.info(f"Uploading {filename} to Google Drive ({self.backup_folder_id})...")
            file_id = google_service.upload_file(
                file_path=filepath,
                filename=filename,
                mime_type="application/sql",
                folder_id=self.backup_folder_id
            )
            logger.info(f"Uploaded successfully. File ID: {file_id}")

            # 3. Clean up local file
            if cleanup and os.path.exists(filepath):
                os.remove(filepath)
                logger.info("Local backup file removed.")
            elif not cleanup:
                logger.info(f"Local backup file kept at: {filepath}")
            
            return file_id

        except Exception as e:
            logger.error(f"Backup cycle failed: {e}")
            # Try to cleanup even if failed
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
            raise e

    async def restore_from_drive(self, file_id: str):
        """
        Downloads backup from Drive and restores it.
        WARNING: Drops existing data!
        """
        logger.warning(f"Starting RESTORE from Drive file {file_id}...")
        
        local_path = os.path.join(BACKUP_DIR, f"restore_{file_id}.sql")
        
        try:
            # 1. Download
            file_io = google_service.download_file(file_id)
            with open(local_path, "wb") as f:
                f.write(file_io.getvalue())
            
            logger.info(f"Downloaded backup to {local_path}")
            
            # 2. Restore
            self.restore_from_file(local_path)
            
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            raise e
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

    def restore_from_file(self, filepath: str):
        """
        Restores DB from a local SQL file.
        """
        # Securely pass password
        env = os.environ.copy()
        env["PGPASSWORD"] = self.db_password

        # psql command
        command = [
            "psql",
            "-h", self.db_host,
            "-U", self.db_user,
            "-d", self.db_name,
            "-f", filepath
        ]
        
        logger.info(f"Restoring database from {filepath}...")
        try:
            subprocess.run(command, env=env, check=True)
            logger.info("Database restored successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Restore command failed: {e}")
            raise Exception("Database restore failed")

    def drop_public_schema(self):
        """
        Drops and recreates the public schema. 
        Useful for cleaning DB before restore if the dump doesn't have --clean.
        """
        env = os.environ.copy()
        env["PGPASSWORD"] = self.db_password
        
        # Command to drop and recreate schema
        sql_command = "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO public;"
        
        command = [
            "psql",
            "-h", self.db_host,
            "-U", self.db_user,
            "-d", self.db_name,
            "-c", sql_command
        ]
        
        logger.warning("Dropping PUBLIC schema...")
        try:
            subprocess.run(command, env=env, check=True)
            logger.info("Schema public reset successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Schema reset failed: {e}")
            raise Exception("Schema reset failed")

backup_service = BackupService()
