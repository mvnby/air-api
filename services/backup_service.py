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
        self.media_dir = "media"
        
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

    def create_media_archive(self) -> str:
        """
        Archives the media/ directory into a tar.gz file.
        Returns the absolute path to the archive.
        """
        if not os.path.exists(self.media_dir):
            logger.warning(f"Media directory '{self.media_dir}' not found. Skipping media backup.")
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"media_backup_{timestamp}.tar.gz"
        filepath = os.path.join(BACKUP_DIR, filename)

        command = [
            "tar",
            "-czf", filepath,
            self.media_dir
        ]

        logger.info(f"Starting legacy media backup for {self.media_dir}...")
        try:
            subprocess.run(command, check=True)
            logger.info(f"Media archive created successfully: {filepath}")
            return filepath
        except subprocess.CalledProcessError as e:
            logger.error(f"Media backup failed: {e}")
            return None

    def _rotate_backups(self):
        """
        Keeps only the last 10 backups in Google Drive.
        Deletes older files.
        """
        if not self.backup_folder_id:
            return

        try:
            files = google_service.list_files(self.backup_folder_id, limit=50)
            
            # Filter files to likely be ours (optional, but good safety)
            # For now, we assume this folder is dedicated to backups
            
            # If we have distinct types (sql vs tar.gz), we might want to rotate them separately
            # Or just keep last N files total. 
            # Let's keep last 10 SETS (approx 20 files if we have sql + tar.gz)
            # Simple approach: Keep last 20 files.
            
            input_limit = 10 * 2 # 10 SQL + 10 Media
            
            if len(files) > input_limit:
                files_to_delete = files[input_limit:]
                logger.info(f"Rotation: Deleting {len(files_to_delete)} old backup files...")
                
                for f in files_to_delete:
                    logger.info(f"Deleting older backup: {f['name']} (created {f['createdTime']})")
                    google_service.delete_file(f['id'])
            else:
                logger.info(f"Rotation check passed: {len(files)} files (Limit: {input_limit})")

        except Exception as e:
            logger.error(f"Backup rotation failed: {e}")

    def perform_backup(self, cleanup: bool = True):
        """
        Full backup cycle: Dump DB + Archive Media -> Upload -> Rotate -> Clean (optional).
        """
        if not self.backup_folder_id:
            logger.warning("BACKUP_FOLDER_ID not set. Skipping upload.")
            return

        created_files = []
        try:
            # 1. Create DB Dump
            db_filepath = self.create_dump()
            created_files.append(db_filepath)
            
            # 2. Create Media Archive
            media_filepath = self.create_media_archive()
            if media_filepath:
                created_files.append(media_filepath)

            # 3. Upload to Google Drive
            uploaded_count = 0
            for fpath in created_files:
                filename = os.path.basename(fpath)
                mime = "application/sql" if fpath.endswith(".sql") else "application/gzip"
                
                logger.info(f"Uploading {filename} to Google Drive...")
                google_service.upload_file(
                    file_path=fpath,
                    filename=filename,
                    mime_type=mime,
                    folder_id=self.backup_folder_id
                )
                uploaded_count += 1
            
            logger.info(f"Uploaded {uploaded_count} backup files successfully.")

            # 4. Rotate Backups
            self._rotate_backups()

            # 5. Clean up local files
            if cleanup:
                for fpath in created_files:
                    if os.path.exists(fpath):
                        os.remove(fpath)
                logger.info("Local backup files removed.")
            else:
                logger.info(f"Local backup files kept: {created_files}")
            
            return True

        except Exception as e:
            logger.error(f"Backup cycle failed: {e}")
            # Try to cleanup even if failed
            for fpath in created_files:
                if fpath and os.path.exists(fpath):
                    try: os.remove(fpath) 
                    except: pass
            raise e

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
