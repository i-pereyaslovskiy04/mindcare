#!/usr/bin/env bash
# Переключение между двумя режимами MindCare.
#
#   demo  — постоянный локально-сетевой стенд для заказчика:
#           один uvicorn (serve_demo:app) на :3000, собранный SPA + API,
#           под systemd (автозапуск после перезагрузки, рестарт при падении).
#   dev   — отладка как раньше: CRA (:3000) + uvicorn app.main:app --reload (:8000).
#
# Режимы взаимоисключающие: оба претендуют на порт 3000.
#
#   scripts/mindcare-mode.sh demo [--build]
#   scripts/mindcare-mode.sh dev
#   scripts/mindcare-mode.sh stop
#   scripts/mindcare-mode.sh status
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT/mindcare_api"
WEB_DIR="$ROOT/mindcare_web"
UNIT="mindcare-demo.service"
LOG_DIR="$ROOT/.logs"
DEV_API_LOG="$LOG_DIR/dev-api.log"
DEV_WEB_LOG="$LOG_DIR/dev-web.log"
DEV_PIDS="$LOG_DIR/dev.pids"

die() { echo "ОШИБКА: $*" >&2; exit 1; }

# node_modules/.bin/react-scripts может отсутствовать даже после успешного
# npm install: /media/data2 смонтирован как exFAT, который не поддерживает
# symlink'и — npm падает (EPERM) на их создании для части бинарников
# (например node_modules/.bin/parser у @babel/parser), из-за чего
# react-scripts тоже не долинкован. `npm install --no-bin-links` обходит
# сам EPERM, но .bin/react-scripts тогда не создаётся вообще. Вызываем
# JS-файл react-scripts напрямую через node — не зависит от .bin в любом
# случае. Дочерний процесс (build/start.js) react-scripts всё равно
# порождает через spawn, так что pkill -f "react-scripts/scripts/start"
# в stop_dev ниже продолжает его находить.
run_react_scripts() {
    (cd "$WEB_DIR" && node node_modules/react-scripts/bin/react-scripts.js "$@")
}

stop_dev() {
    if [[ -f "$DEV_PIDS" ]]; then
        while read -r pid; do
            [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
        done < "$DEV_PIDS"
        rm -f "$DEV_PIDS"
    fi
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    pkill -f "react-scripts/scripts/start" 2>/dev/null || true
    sleep 1
}

stop_demo() {
    sudo systemctl stop "$UNIT" 2>/dev/null || true
}

case "${1:-status}" in
    demo)
        stop_dev
        if [[ "${2:-}" == "--build" || ! -f "$WEB_DIR/build/index.html" ]]; then
            echo "==> Сборка фронтенда (react-scripts build)…"
            CI=false run_react_scripts build
        fi
        echo "==> Запуск демо-стенда ($UNIT)…"
        sudo systemctl enable --now "$UNIT"
        sudo systemctl restart "$UNIT"
        sleep 2
        systemctl is-active --quiet "$UNIT" \
            && echo "Демо работает: http://$(hostname -I | awk '{print $1}'):3000" \
            || die "юнит не поднялся, смотрите: journalctl -u $UNIT -n 50"
        ;;

    dev)
        stop_demo
        stop_dev
        mkdir -p "$LOG_DIR"
        echo "==> Backend: uvicorn app.main:app --reload (:8000)"
        (cd "$API_DIR" && nohup .venv/bin/uvicorn app.main:app --reload --port 8000 \
            > "$DEV_API_LOG" 2>&1 & echo $! >> "$DEV_PIDS")
        echo "==> Frontend: react-scripts start (:3000)"
        (cd "$WEB_DIR" && BROWSER=none nohup node node_modules/react-scripts/bin/react-scripts.js start \
            > "$DEV_WEB_LOG" 2>&1 & echo $! >> "$DEV_PIDS")
        echo "Логи: $DEV_API_LOG · $DEV_WEB_LOG"
        echo "Остановить: scripts/mindcare-mode.sh stop"
        ;;

    stop)
        stop_demo
        stop_dev
        echo "Оба режима остановлены."
        ;;

    status)
        echo "── demo ($UNIT) ──"
        systemctl is-enabled "$UNIT" 2>/dev/null | sed 's/^/  автозапуск: /' || true
        systemctl is-active "$UNIT" 2>/dev/null | sed 's/^/  состояние:  /' || true
        echo "── dev ──"
        pgrep -f "uvicorn app.main:app" >/dev/null && echo "  backend :8000 работает" || echo "  backend :8000 остановлен"
        pgrep -f "react-scripts/scripts/start" >/dev/null && echo "  frontend :3000 работает" || echo "  frontend :3000 остановлен"
        echo "── порты ──"
        ss -tlnp 2>/dev/null | grep -E ':(3000|8000)' || echo "  3000/8000 свободны"
        ;;

    *)
        die "неизвестный режим: $1 (ожидается demo | dev | stop | status)"
        ;;
esac
