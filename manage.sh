#!/bin/bash

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
VENV_UVICORN="$PROJECT_DIR/.venv/bin/uvicorn"
LOG_FILE="$PROJECT_DIR/app.log"
BOT_SCRIPT="$PROJECT_DIR/bot.py"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 {start|stop|restart|status|logs}"
    exit 1
}

get_api_pid() {
    ps aux | grep "uvicorn main:app" | grep -v grep | awk '{print $2}'
}

get_bot_pid() {
    ps aux | grep "bot.py" | grep -v grep | awk '{print $2}'
}

start() {
    echo -e "${YELLOW}Starting services...${NC}"

    # 1. API Server
    API_PID=$(get_api_pid)
    if [ -n "$API_PID" ]; then
        echo -e "${YELLOW}API is already running (PID: $API_PID)${NC}"
    else
        echo -n "Starting API Server... "
        nohup env PYTHONUNBUFFERED=1 "$VENV_UVICORN" main:app --host 127.0.0.1 --port 8000 --reload >> server.log 2>&1 &
        echo -e "${GREEN}DONE${NC}"
    fi

    # 2. Bot
    BOT_PID=$(get_bot_pid)
    if [ -n "$BOT_PID" ]; then
        echo -e "${YELLOW}Bot is already running (PID: $BOT_PID)${NC}"
    else
        echo -n "Starting Telegram Bot... "
        nohup "$VENV_PYTHON" "$BOT_SCRIPT" >> bot.log 2>&1 &
        echo -e "${GREEN}DONE${NC}"
    fi
}

stop() {
    echo -e "${YELLOW}Stopping services...${NC}"

    API_PID=$(get_api_pid)
    if [ -n "$API_PID" ]; then
        echo -n "Stopping API (PID: $API_PID)... "
        kill -9 $API_PID
        echo -e "${GREEN}DONE${NC}"
    else
        echo -e "API is not running."
    fi

    BOT_PID=$(get_bot_pid)
    if [ -n "$BOT_PID" ]; then
        echo -n "Stopping Bot (PID: $BOT_PID)... "
        kill -9 $BOT_PID
        echo -e "${GREEN}DONE${NC}"
    else
        echo -e "Bot is not running."
    fi
}

status() {
    echo -e "${YELLOW}--- Service Status ---${NC}"
    
    API_PID=$(get_api_pid)
    if [ -n "$API_PID" ]; then
        echo -e "API Server:   ${GREEN}RUNNING${NC} (PID: $API_PID)"
    else
        echo -e "API Server:   ${RED}STOPPED${NC}"
    fi

    BOT_PID=$(get_bot_pid)
    if [ -n "$BOT_PID" ]; then
        echo -e "Telegram Bot: ${GREEN}RUNNING${NC} (PID: $BOT_PID)"
    else
        echo -e "Telegram Bot: ${RED}STOPPED${NC}"
    fi
}

logs() {
    tail -f "$LOG_FILE"
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 1
        start
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    *)
        usage
        ;;
esac
