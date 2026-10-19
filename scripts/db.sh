#!/usr/bin/env bash
# MariaDB(Docker, 3307) 기동과 스키마 적용. 사용: scripts/db.sh up | apply | down | shell
# 관리자(root) 계정은 DDL 적용에만 쓴다. 서버들은 gongsi_app·gongsi_audit 계정으로 붙는다.
set -euo pipefail
cd "$(dirname "$0")/.."
NAME=gongsi-mariadb
SQL=(schema/01_schema schema/02_agent_schema schema/03_hitl_schema schema/04_governance_schema schema/05_llm_schema
     schema/06_rag_schema schema/07_ingest_schema schema/08_glossary_schema seed seed_glossary)

apply() {
  for f in "${SQL[@]}"; do
    echo "  적용: db/$f.sql"
    docker exec -i "$NAME" mariadb -uroot -proot < "db/$f.sql"
  done
}

case "${1:-up}" in
  up)
    if ! docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
      docker run -d --name "$NAME" -p 3307:3306 -e MARIADB_ROOT_PASSWORD=root -e MARIADB_DATABASE=gongsi \
        -e TZ=Asia/Seoul mariadb:11 --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci >/dev/null
    else
      docker start "$NAME" >/dev/null
    fi
    printf "MariaDB 기동 대기"
    until docker exec "$NAME" mariadb -uroot -proot -e "select 1" >/dev/null 2>&1; do printf "."; sleep 1; done
    echo " 완료"
    apply ;;
  apply) apply ;;
  down) docker stop "$NAME" ;;
  shell) docker exec -it "$NAME" mariadb -uroot -proot gongsi ;;
  *) echo "사용: $0 up|apply|down|shell"; exit 1 ;;
esac
