# Deployment Guide (Docker & PostgreSQL)

This guide describes how to deploy the MVN project using Docker and PostgreSQL.

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

Create a `.env` file in the root directory. You can use `.env.example` as a template.

### Database Credentials
These variables are used by both the PostgreSQL container and the application:
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
```

## 3. Running with Docker Compose

To build and start all services (App, Bot, Database):
```bash
docker compose up -d --build
```

This will:
- Start PostgreSQL on port `5432` (internal and external).
- Start the FastAPI application on port `8000`.
- Start the Telegram Bot.

## 4. First Run & Data Migration

If you are migrating from an existing SQLite database:

1. Ensure `air_conditioners.db` is present in the project root.
2. Run the migration script inside the running container:
   ```bash
   docker compose exec app python scripts/migrate_sqlite_to_pg.py
   ```
   *Note: This script also resets PostgreSQL sequences for auto-increment fields.*

## 5. Monitoring & Logs

View combined logs:
```bash
docker compose logs -f
```

View specific service logs:
```bash
docker compose logs -f app
docker compose logs -f bot
```

## 6. Updating the Application

To update to the latest version:
```bash
git pull origin main
docker compose up -d --build
```

## 7. Backups and Recovery

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
This script runs the backup process inside the container and ensures the local file is preserved.

### Restore

You can restore the database using the `restore.py` script included in the image.

**⚠️ WARNING: Restoring will overwrite the current database!**

#### Option A: Restore from Local File
If you have a `.sql` file in your `backups/` folder (or mapped volume):

```bash
docker compose exec app python restore.py --file backups/your_backup_file.sql
```

#### Option B: Restore from Google Drive
If you know the File ID from Google Drive:

```bash
docker compose exec app python restore.py --drive-id <GOOGLE_DRIVE_FILE_ID>
```

---

### Legacy Manual Methods (Direct PG Access)

#### PostgreSQL Dump (Raw)
```bash
docker compose exec db pg_dump -U mvnadmin air_conditioners > backup.sql
```

#### Restore (Raw)
```bash
cat backup.sql | docker compose exec -T db psql -U mvnadmin air_conditioners
```

## Nginx Configuration (Optional Reverse Proxy)

If you are using Nginx on the host machine to proxy to the Docker container:

```nginx
server {
    listen 80;
    server_name crm.mvn.by;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Uploaded files
    location /static/uploads {
        alias /var/www/mvn/static/uploads;
    }
}
```
