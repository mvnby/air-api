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
CORS_ORIGINS=["https://mvn.by","https://dev.mvn.by"]  # Allowed origins (comma-separated json list)
```

### Environment Separation (Dev vs Production)

The project uses **two separate environment files** to prevent configuration conflicts between local development and production:

| Environment | File | Usage |
|-------------|------|-------|
| **Local/Dev** | `.env` | Used by `docker compose up` locally |
| **Production** | `env.prod` | Deployed to server as `.env` |

**Important:**
- `.env` and `env.prod` are both **git-ignored** for security.
- The `deploy_api.sh` script automatically copies `env.prod` to the server as `.env`.
- This separation ensures:
  - Different bot tokens (dev bot vs production bot)
  - Different API URLs (`localhost` vs `https://api.mvn.by`)
  - Different admin credentials if needed

**Example differences:**
```bash
# .env (Local)
BOT_TOKEN=123456:DEV_BOT_TOKEN
PUBLIC_API_BASE=http://localhost:8000/api/v1

# env.prod (Production)
BOT_TOKEN=389060515:PRODUCTION_BOT_TOKEN
PUBLIC_API_BASE=https://api.mvn.by/api/v1
```

## 2.5. DevOps Risks Audit

> [!CAUTION]
> The following are known risks and limitations in the current deployment process. These are documented for transparency and future improvement.

### Secret Management
- **Risk**: Secrets stored in plain text files (`env.prod`, `.env`)
- **Mitigation**: Files are git-ignored and transferred via SSH
- **Future**: Consider using HashiCorp Vault or cloud secret managers

### Local Build Dependencies
- **Risk**: Deployments require a properly configured developer machine with Node.js, npm, Python
- **Mitigation**: Document required versions in README
- **Impact**: Team members need identical dev environments

### SSH Key Requirements
- **Risk**: Deployment scripts require pre-configured SSH access to `mvn-api` and `mvn-web` hosts
- **Mitigation**: Document SSH setup in onboarding
- **Impact**: New team members need SSH keys distributed manually

### No Pre-Deployment Testing
- **Risk**: No automated tests run before deployment
- **Mitigation**: Manual testing recommended
- **Future**: Add GitHub Actions CI/CD pipeline

### Manual Media Syncing
- **Risk**: Media files (`/media/`) must be manually synced with `sync_media.sh`
- **Impact**: Risk of serving stale images if sync is forgotten
- **Future**: Consider object storage (S3/Cloudflare R2)

### Build on Production (VPS Resource Impact)
- **Status**: Previously used multi-stage Docker builds on server
- **Solution**: ✅ **Resolved** - Now using local builds + artifact push strategy
- **Benefit**: Minimal VPS resource usage during deployment

## 3. Deployment Strategy

**We use a "Local Build → Push Artifacts" strategy** to minimize VPS resource usage.

### Key Principles:
1. **Build locally** on your development machine
2. **Push artifacts** (compiled bundles) to servers
3. **Fast Docker rebuilds** (just file copying, no compilation on server)

---

## 4. Deploying Backend API + Manager Dashboard

The backend and manager dashboard are deployed together to `api.mvn.by`.

### Step 1: Build Manager Frontend Locally

```bash
cd manager_frontend
npm install
npm run build
```

This creates `manager_frontend/dist/` with the compiled Vue application.

### Step 2: Deploy to Production

```bash
# From project root
./deploy_api.sh
```

**What happens:**
1. ✅ Pre-flight check: Verifies `manager_frontend/dist` exists
2. 📂 Syncs code + migrations + manager artifacts to server
3. ⚙️ Copies `env.prod` to server as `.env`
4. 🐳 Rebuilds Docker containers (fast - just file copy)
5. 📦 Runs database migrations
6. 🔄 Restarts services

### Step 3: Verify

- **Admin Panel**: https://api.mvn.by/admin/
- **Manager Dashboard**: https://api.mvn.by/manager/
- **Health Check**: https://api.mvn.by/api/health

---

## 5. Deploying Web Frontend

The main website is deployed to either `dev.mvn.by` or `mvn.by`.

### Step 1: Build Web Frontend Locally

```bash
# Option A: Manual build
cd web
npm install
npm run build

# Option B: Recommended (uses production API data)
./build_with_prod_data.sh
```

This creates `web/dist/` with the compiled Astro static site.

### Step 2: Deploy to Dev or Production

```bash
# Deploy to DEV environment (dev.mvn.by)
./deploy_web.sh dev

# Deploy to PRODUCTION (mvn.by)
./deploy_web.sh prod
```

**What happens:**
1. ✅ Pre-flight check: Verifies `web/dist` exists
2. 🖼️ Syncs media from API server (for static assets)
3. 📡 Uploads static files to web host
4. 🤖 Configures robots.txt based on environment

### Step 3: Verify

- **Dev**: https://dev.mvn.by
- **Production**: https://mvn.by

---

## 6. Local Development

To run services locally for development:

```bash
docker compose up -d --build
```

*Note: This starts `app`, `bot`, and `db`. The `web` container is for local development or generation only.*

### Monitoring & Logs

View combined logs:
```bash
docker compose logs -f
```

View specific service logs:
```bash
docker compose logs -f app
docker compose logs -f bot
```

---

## 7. Database Migrations (Alembic)

We use **Alembic** for database schema versioning. This ensures that schema changes are applied consistently across all environments.

> [!CAUTION]
> If there were **database schema changes** (new columns, tables), you MUST run migrations BEFORE restarting Docker containers.

### When to Use Migrations

| Scenario | Action |
|----------|--------|
| Added new column to a model | Create migration |
| Renamed/deleted column | Create migration |
| Changed column type | Create migration |
| Just changed Python code (no DB) | No migration needed |

### Local Development Workflow

**Step 1: Make changes to `models.py`**

**Step 2: Auto-generate migration**
```bash
# Inside the container (or locally if you have Python env)
docker compose exec app alembic revision --autogenerate -m "add installation columns"
```
This creates a new file in `alembic/versions/` with the detected changes.

**Step 3: Review the generated migration**
Open the new file and verify the `upgrade()` and `downgrade()` functions are correct.

**Step 4: Apply migration locally**
```bash
docker compose exec app alembic upgrade head
```

**Step 5: Commit migration file to git**
```bash
git add alembic/versions/
git commit -m "migration: add installation columns"
```

### Production Deployment Workflow

Use the provided scripts from your local machine:
- For Backend/Manager: `./deploy_api.sh`
- For Web: `./deploy_web.sh prod`

These scripts handle syncing, migrations, and restarts automatically.

### Useful Alembic Commands

```bash
# Check current migration version
docker compose exec app alembic current

# Show migration history
docker compose exec app alembic history

# Downgrade one step (rollback)
docker compose exec app alembic downgrade -1

# Generate empty migration (for manual SQL)
docker compose exec app alembic revision -m "manual changes"
```

### Emergency: Manual Schema Fix (Without Migration)

If you need to quickly fix a missing column on production without a migration file:

```bash
# Connect to DB and add column manually
ssh mvn-api "cd /opt/air-api && docker compose exec db psql -U mvnadmin -d air_conditioners -c 'ALTER TABLE tablename ADD COLUMN colname TYPE DEFAULT value;'"
```

> [!WARNING]
> Manual fixes are a **temporary solution**. Always create a proper migration afterwards to keep the schema in sync.

## 8. Backups and Recovery

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

## 9. Nginx Configuration (api.mvn.by)

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

## 10. Media Synchronization

To synchronize local media files (images, uploads) with the remote server:

```bash
./sync_media.sh
```
This uses `rsync` to upload contents of `./media/` to `/opt/air-api/media` on the `mvn-api` host.
*Note: Requires SSH access configured for `mvn-api` alias.*
```

