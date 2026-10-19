#!/usr/bin/env bash
# 앱 서버 4개를 의존 방향의 역순(불리는 쪽 먼저)으로 띄운다. 로그는 .tmp/logs/에 남는다.
# 사용: scripts/dev.sh start | stop | status
# 사전 조건: scripts/db.sh up, 각 디렉터리의 .venv·node_modules 준비(README 참고)
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
LOG="$ROOT/.tmp/logs"; PIDS="$ROOT/.tmp/pids"
mkdir -p "$LOG" "$PIDS"

wait_port() {
  local port=$1 name=$2
  for _ in $(seq 1 90); do
    if nc -z localhost "$port" 2>/dev/null; then echo "  ✓ $name :$port"; return 0; fi
    sleep 1
  done
  echo "  ✕ $name :$port 가 뜨지 않았습니다. $LOG/$name.log 를 확인하세요"; return 1
}

start_one() {
  local name=$1 dir=$2 port=$3; shift 3
  if nc -z localhost "$port" 2>/dev/null; then echo "  - $name :$port 이미 사용 중(건너뜀)"; return; fi
  # 각 디렉터리의 .env.local(git 미추적)이 있으면 그 프로세스에만 환경변수로 넘긴다. 원천 API 키는 여기에 둔다
  (cd "$ROOT/$dir" && { [ -f .env.local ] && { set -a; . ./.env.local; set +a; echo "  · $name: .env.local 적용"; }; true; } \
    && nohup "$@" > "$LOG/$name.log" 2>&1 & echo $! > "$PIDS/$name.pid")
  wait_port "$port" "$name"
}

case "${1:-start}" in
  start)
    start_one core-service core-service 9100 .venv/bin/uvicorn app.main:app --port 9100
    start_one ai-server ai-server 8100 .venv/bin/uvicorn app.main:app --port 8100
    start_one backend backend 8180 ./gradlew bootRun --console=plain
    start_one frontend frontend 3100 npm run dev
    echo "→ http://localhost:3100  (analyst_001 / senior_001, 비밀번호 password)" ;;
  stop)
    for f in "$PIDS"/*.pid; do
      [ -e "$f" ] || continue
      pid=$(cat "$f"); name=$(basename "$f" .pid)
      pkill -P "$pid" 2>/dev/null; kill "$pid" 2>/dev/null && echo "  정지: $name"
      rm -f "$f"
    done
    # gradlew bootRun이 띄운 JVM은 손자 프로세스라 위에서 닿지 않는다. 우리 포트를 잡고 있는 프로세스를 직접 내린다
    for p in 9100 8100 8180 3100; do
      left=$(lsof -nP -iTCP:"$p" -sTCP:LISTEN -t 2>/dev/null)
      [ -n "$left" ] && kill $left 2>/dev/null && echo "  정지: :$p (pid $left)"
    done ;;
  status)
    for p in 9100:core-service 8100:ai-server 8180:backend 3100:frontend; do
      nc -z localhost "${p%%:*}" 2>/dev/null && echo "  ✓ ${p#*:} :${p%%:*}" || echo "  ✕ ${p#*:} :${p%%:*}"
    done ;;
  *) echo "사용: $0 start|stop|status"; exit 1 ;;
esac
