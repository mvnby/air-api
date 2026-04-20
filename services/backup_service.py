import asyncio
import gzip
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.config import settings
from core.logger import logger
from services.google_service import get_google_service

BACKUP_DIR = "backups"


class BackupService:
    def __init__(self):
        self.db_user = os.getenv("POSTGRES_USER", "mvnadmin")
        self.db_password = os.getenv("POSTGRES_PASSWORD", "securepass")
        self.db_name = os.getenv("POSTGRES_DB", "air_conditioners")
        self.db_host = os.getenv("POSTGRES_SERVER", "db")
        self.db_port = os.getenv("POSTGRES_PORT", "5432")
        self.backup_folder_id = os.getenv("BACKUP_FOLDER_ID")
        self.media_dir = "media"

        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)

    @staticmethod
    def _parse_created_at(raw_value: Optional[str]) -> datetime:
        if not raw_value:
            return datetime.now()
        try:
            return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now()

    @staticmethod
    def _detect_backup_kind(filename: str, mime_type: Optional[str] = None) -> Optional[str]:
        lower_name = (filename or "").lower()
        lower_mime = (mime_type or "").lower()

        if lower_name.startswith("media_backup_") or lower_name.endswith(".tar.gz"):
            return "media"

        if (
            lower_name.startswith("backup_")
            or lower_name.startswith("backup-air")
            or lower_name.startswith("backup_air_conditioners_")
            or lower_name.endswith(".sql")
            or lower_name.endswith(".sql.gz")
        ):
            if lower_name.endswith(".sql") or lower_name.endswith(".sql.gz") or "sql" in lower_mime:
                return "db"

        if "gzip" in lower_mime and "media" in lower_name:
            return "media"
        if "sql" in lower_mime:
            return "db"

        return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def list_backups(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Returns available backups from Google Drive folder with `db/media` classification.
        """
        if not self.backup_folder_id:
            logger.warning("BACKUP_FOLDER_ID not set. Returning empty backup list.")
            return []

        files = get_google_service().list_files(self.backup_folder_id, limit=limit)
        items: List[Dict[str, Any]] = []
        for item in files:
            name = item.get("name", "")
            kind = self._detect_backup_kind(name, item.get("mimeType"))
            if kind not in {"db", "media"}:
                continue
            items.append(
                {
                    "id": item.get("id"),
                    "name": name,
                    "kind": kind,
                    "created_at": self._parse_created_at(item.get("createdTime")),
                    "size_bytes": self._safe_int(item.get("size")),
                    "mime_type": item.get("mimeType"),
                }
            )

        items.sort(key=lambda x: x.get("created_at") or datetime.min, reverse=True)
        return items

    def create_dump(self, filename_prefix: Optional[str] = None) -> str:
        """
        Creates a PostgreSQL SQL dump and saves it locally.
        Returns absolute path to the dump file.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = filename_prefix or f"backup_{self.db_name}"
        filename = f"{prefix}_{timestamp}.sql"
        filepath = os.path.join(BACKUP_DIR, filename)

        env = os.environ.copy()
        env["PGPASSWORD"] = self.db_password

        command = [
            "pg_dump",
            "-h",
            self.db_host,
            "-p",
            self.db_port,
            "-U",
            self.db_user,
            "-d",
            self.db_name,
            "-f",
            filepath,
            "--clean",
            "--if-exists",
        ]

        logger.info("Starting backup for %s...", self.db_name)
        try:
            subprocess.run(command, env=env, check=True)
            logger.info("Backup created successfully: %s", filepath)
            return filepath
        except subprocess.CalledProcessError as exc:
            logger.error("Backup failed: %s", exc)
            raise Exception("Backup creation failed")

    def create_media_archive(self) -> Optional[str]:
        """
        Archives the media/ directory into a tar.gz file.
        Returns absolute path to the archive if exists.
        """
        if not os.path.exists(self.media_dir):
            logger.warning("Media directory '%s' not found. Skipping media backup.", self.media_dir)
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"media_backup_{timestamp}.tar.gz"
        filepath = os.path.join(BACKUP_DIR, filename)

        command = ["tar", "-czf", filepath, self.media_dir]

        logger.info("Starting media backup for %s...", self.media_dir)
        try:
            subprocess.run(command, check=True)
            logger.info("Media archive created successfully: %s", filepath)
            return filepath
        except subprocess.CalledProcessError as exc:
            logger.error("Media backup failed: %s", exc)
            return None

    def _rotate_backups(self):
        """
        Keeps only the latest 10 backup sets in Google Drive (db + media).
        """
        if not self.backup_folder_id:
            return

        try:
            files = get_google_service().list_files(self.backup_folder_id, limit=50)
            keep_limit = 10 * 2

            if len(files) > keep_limit:
                files_to_delete = files[keep_limit:]
                logger.info("Rotation: deleting %s old backup files...", len(files_to_delete))
                for file_data in files_to_delete:
                    logger.info(
                        "Deleting older backup: %s (created %s)",
                        file_data.get("name"),
                        file_data.get("createdTime"),
                    )
                    get_google_service().delete_file(file_data["id"])
            else:
                logger.info("Rotation check passed: %s files (limit: %s)", len(files), keep_limit)
        except Exception as exc:
            logger.error("Backup rotation failed: %s", exc)

    def perform_backup(self, cleanup: bool = True):
        """
        Full backup cycle: DB dump + media archive -> upload -> rotate -> cleanup.
        """
        if not settings.is_production:
            logger.warning(
                "Backup upload is disabled for ENVIRONMENT=%s. "
                "No scheduled/manual backups will be pushed to Google Drive outside production.",
                settings.ENVIRONMENT,
            )
            return False

        if not self.backup_folder_id:
            logger.warning("BACKUP_FOLDER_ID not set. Skipping upload.")
            return

        created_files: List[str] = []
        try:
            db_filepath = self.create_dump()
            created_files.append(db_filepath)

            media_filepath = self.create_media_archive()
            if media_filepath:
                created_files.append(media_filepath)

            uploaded_count = 0
            for filepath in created_files:
                filename = os.path.basename(filepath)
                mime = "application/sql" if filepath.endswith(".sql") else "application/gzip"
                logger.info("Uploading %s to Google Drive...", filename)
                get_google_service().upload_file(
                    file_path=filepath,
                    filename=filename,
                    mime_type=mime,
                    folder_id=self.backup_folder_id,
                )
                uploaded_count += 1

            logger.info("Uploaded %s backup files successfully.", uploaded_count)
            self._rotate_backups()

            if cleanup:
                for filepath in created_files:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                logger.info("Local backup files removed.")
            else:
                logger.info("Local backup files kept: %s", created_files)

            return True
        except Exception as exc:
            logger.error("Backup cycle failed: %s", exc)
            for filepath in created_files:
                if filepath and os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
            raise

    def download_backup_file(self, file_id: str, destination_path: str) -> str:
        """
        Downloads Google Drive file to local destination path.
        """
        file_io = get_google_service().download_file(file_id)
        with open(destination_path, "wb") as out:
            out.write(file_io.getvalue())
        return destination_path

    @staticmethod
    def decompress_gzip_file(source_path: str, destination_path: str) -> str:
        with gzip.open(source_path, "rb") as source_file, open(destination_path, "wb") as destination_file:
            shutil.copyfileobj(source_file, destination_file)
        return destination_path

    @staticmethod
    def _safe_extract_tar(archive_path: str, destination_dir: str) -> None:
        destination_abs = os.path.abspath(destination_dir)
        with tarfile.open(archive_path, "r:*") as tar:
            for member in tar.getmembers():
                if member.issym() or member.islnk():
                    raise Exception(f"Unsupported link in archive: {member.name}")
                member_path = os.path.abspath(os.path.join(destination_dir, member.name))
                if os.path.commonpath([destination_abs, member_path]) != destination_abs:
                    raise Exception(f"Unsafe path in archive: {member.name}")
            tar.extractall(path=destination_dir)

    def restore_media_from_archive(self, archive_path: str) -> str:
        """
        Restores media directory from tar(.gz) archive.
        Returns path to created safety archive of previous media state (if created).
        """
        if not os.path.exists(archive_path):
            raise Exception(f"Media archive not found: {archive_path}")

        safety_archive = self.create_media_archive()
        temp_dir = tempfile.mkdtemp(prefix="media_restore_", dir=BACKUP_DIR)

        try:
            self._safe_extract_tar(archive_path, temp_dir)

            extracted_media_dir = os.path.join(temp_dir, "media")
            if os.path.isdir(extracted_media_dir):
                restore_source = extracted_media_dir
            else:
                # Fallback for archives with direct files at root.
                restore_source = temp_dir

            if os.path.exists(self.media_dir):
                shutil.rmtree(self.media_dir)

            if restore_source == temp_dir:
                os.makedirs(self.media_dir, exist_ok=True)
                for item in os.listdir(temp_dir):
                    item_path = os.path.join(temp_dir, item)
                    if item_path == self.media_dir:
                        continue
                    shutil.move(item_path, os.path.join(self.media_dir, item))
            else:
                shutil.move(restore_source, self.media_dir)

            logger.info("Media restored successfully from %s", archive_path)
            return safety_archive or ""
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def restore_from_file_async(self, filepath: str):
        """
        Restores DB from local SQL file using non-blocking subprocess.
        """
        env = os.environ.copy()
        env["PGPASSWORD"] = self.db_password
        command = [
            "psql",
            "-h",
            self.db_host,
            "-p",
            self.db_port,
            "-U",
            self.db_user,
            "-d",
            self.db_name,
            "-f",
            filepath,
        ]

        logger.info("Restoring database from %s...", filepath)
        process = await asyncio.create_subprocess_exec(
            *command,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            error_text = stderr.decode("utf-8", errors="ignore").strip()
            logger.error("Restore command failed (%s): %s", process.returncode, error_text)
            raise Exception("Database restore failed")

        if stdout:
            logger.info("Restore output: %s", stdout.decode("utf-8", errors="ignore").strip())
        logger.info("Database restored successfully.")

    async def restore_from_drive(self, file_id: str):
        """
        Downloads backup from Drive and restores it.
        WARNING: drops existing data in the target database.
        """
        logger.warning("Starting RESTORE from Drive file %s...", file_id)
        local_path = os.path.join(BACKUP_DIR, f"restore_{file_id}.sql")
        try:
            await asyncio.to_thread(self.download_backup_file, file_id, local_path)
            logger.info("Downloaded backup to %s", local_path)
            await self.restore_from_file_async(local_path)
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

    def restore_from_file(self, filepath: str):
        """
        Legacy synchronous restore (used by scripts).
        """
        env = os.environ.copy()
        env["PGPASSWORD"] = self.db_password
        command = [
            "psql",
            "-h",
            self.db_host,
            "-p",
            self.db_port,
            "-U",
            self.db_user,
            "-d",
            self.db_name,
            "-f",
            filepath,
        ]

        logger.info("Restoring database from %s...", filepath)
        try:
            subprocess.run(command, env=env, check=True)
            logger.info("Database restored successfully.")
        except subprocess.CalledProcessError as exc:
            logger.error("Restore command failed: %s", exc)
            raise Exception("Database restore failed")

    def drop_public_schema(self):
        """
        Drops and recreates the public schema.
        """
        env = os.environ.copy()
        env["PGPASSWORD"] = self.db_password

        sql_command = "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO public;"
        command = [
            "psql",
            "-h",
            self.db_host,
            "-p",
            self.db_port,
            "-U",
            self.db_user,
            "-d",
            self.db_name,
            "-c",
            sql_command,
        ]

        logger.warning("Dropping PUBLIC schema...")
        try:
            subprocess.run(command, env=env, check=True)
            logger.info("Schema public reset successfully.")
        except subprocess.CalledProcessError as exc:
            logger.error("Schema reset failed: %s", exc)
            raise Exception("Schema reset failed")


backup_service = BackupService()
