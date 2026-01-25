# Deployment Guide (Backend & Bot)

This guide describes how to deploy the backend services for **MVN.BY**.

## Architecture Overview

*   **Frontend**: Static HTML web application hosted on `mvn.by`.
*   **Backend**: FastAPI application + Telegram Bot hosted on `api.mvn.by`.
*   **Database**: PostgreSQL (Dockerized).

## System Requirements
- Docker 20.10+
- Docker Compose (v2 recommended)
- Git

## 1. Project Setup

Clone the repository and enter the directory:
```bash
git clone <repo_url>
cd mvn
```

## 2. Environment Variables

Create a `.env` file in the root directory.

### Database Credentials
```env
POSTGRES_USER=mvnadmin
POSTGRES_PASSWORD=securepass
POSTGRES_DB=air_conditioners
POSTGRES_SERVER=db
POSTGRES_PORT=5432
```

### Application Settings
```env
BOT_TOKEN=...
ADMIN_USERNAME=...
ADMIN_PASSWORD=...
SECRET_KEY=...
BACKUP_FOLDER_ID=...   # Google Drive Folder ID for backups
```

## 3. Running Services

To build and start the backend services (App, Bot, Database):
```bash
docker compose up -d --build
```
*Note: This starts `app`, `bot`, and `db`. The `web` container is for local development or generation only.*

## 4. Monitoring & Logs

View combined logs:
```bash
docker compose logs -f
```

View specific service logs:
```bash
docker compose logs -f app
docker compose logs -f bot
```

## 5. Updating the Application

To update to the latest version:
```bash
git pull origin main
docker compose up -d --build
```

## 6. Backups and Recovery

### Automated Backups
The system is configured to automatically backup the database every 24 hours. Backups are:
1. Created via `pg_dump`.
2. Uploaded to the configured Google Drive folder (`BACKUP_FOLDER_ID`).
3. Cleaned up locally to save space.

### Manual Backup
To manually trigger a backup (and also keep a local copy in the `backups/` folder):

```bash
./backup_db.sh
```

### Restore
**⚠️ WARNING: Restoring will overwrite the current database!**

#### Option A: Restore from Local File
```bash
docker compose exec app python restore.py --file backups/your_backup_file.sql
```
*Tip: Add `--clean-db` to drop the current database schema before restoring (Recommended if restoring over existing data).*
```bash
docker compose exec app python restore.py --file backups/your_backup_file.sql --clean-db
```

#### Option B: Restore from Google Drive
```bash
docker compose exec app python restore.py --drive-id <GOOGLE_DRIVE_FILE_ID>
```

## 7. Nginx Configuration (api.mvn.by)

The backend server (`api.mvn.by`) acts as the API endpoint for the static site.

```nginx
server {
    listen 80;
    server_name api.mvn.by;

    # Backend API + Admin Panel
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Uploaded media files
    location /media/ {
        alias /var/www/mvn/media/;
    }
}

## 8. Media Synchronization

To synchronize local media files (images, uploads) with the remote server:

```bash
./sync_media.sh
```
This uses `rsync` to upload contents of `./media/` to `/opt/air-api/media` on the `mvn-api` host.
*Note: Requires SSH access configured for `mvn-api` alias.*
```

