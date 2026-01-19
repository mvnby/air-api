# Deployment Guide

## System Requirements
- Python 3.10+
- SQLite (included)
- Nginx (optional, for reverse proxy)
- Systemd (for service management)

## 1. Environment Setup

Copy `.env.example` to `.env` and fill in:
```bash
cp .env.example .env
nano .env
```

Ensure `SECRET_KEY` is secure in production!

## 2. Running with Gunicorn (Production)

Do not use `uvicorn` directly in production. Use `gunicorn` with uvicorn workers.

```bash
gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## 3. Systemd Service

Create `/etc/systemd/system/mvn-crm.service`:

```ini
[Unit]
Description=MVN CRM API
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/mvn
Environment="PATH=/var/www/mvn/.venv/bin"
ExecStart=/var/www/mvn/.venv/bin/gunicorn main:app --workers 3 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

## 4. Nginx Configuration

Create `/etc/nginx/sites-available/mvn`:

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

    location /static {
        alias /var/www/mvn/static;
    }
}
```

## 5. Updates
To update the application:
```bash
git pull origin main
./manage.sh migrate  # If migration script exists
systemctl restart mvn-crm
```
