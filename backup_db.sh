#!/bin/bash

# Execute backup inside the container, keeping the local file
docker compose exec app python -c "from services.backup_service import backup_service; print(f'Backup ID: {backup_service.perform_backup(cleanup=False)}')"
