#!/usr/bin/env bash
# OpenDART 인증키가 동작하는지 확인한다. 키는 backend/.env.local 에서 읽고, 화면에는 결과 상태만 출력한다(키는 출력하지 않음).
# 사용: scripts/opendart-check.sh [corp_code]   기본 00126380(삼성전자)
set -uo pipefail
cd "$(dirname "$0")/.."
ENV=backend/.env.local
[ -f "$ENV" ] || { echo "✕ $ENV 가 없습니다. backend/.env.example 을 복사해 OPENDART_API_KEY 를 채우세요"; exit 1; }
set -a; . "./$ENV"; set +a
[ -n "${OPENDART_API_KEY:-}" ] || { echo "✕ $ENV 에 OPENDART_API_KEY 가 비어 있습니다"; exit 1; }

CORP=${1:-00126380}
YEAR=$(( $(date +%Y) - 1 ))
call() {  # $1 = API 경로, $2 = 쿼리(키 제외). 응답에서 status·message와 요약 한 줄만 뽑는다
  curl -s --max-time 20 "https://opendart.fss.or.kr/api/$1?crtfc_key=$OPENDART_API_KEY&$2" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print("  ✕ JSON이 아닌 응답"); sys.exit(1)
st, msg = d.get("status"), d.get("message")
mark = "✓" if st == "000" else "✕"
lst = d.get("list")
extra = d.get("corp_name") or (str(len(lst)) + "건" if lst is not None else "")
print(f"  {mark} status={st} {msg} {extra}")
sys.exit(0 if st == "000" else 1)'
}

echo "OpenDART 점검 (corp_code=$CORP)"
echo "- 기업개황(company.json)";                     call company.json "corp_code=$CORP"; ok1=$?
echo "- 정기공시 목록(list.json, 최근 1년)";          call list.json "corp_code=$CORP&bgn_de=$(( YEAR ))0101&pblntf_ty=A&page_count=10"; ok2=$?
echo "- 재무제표(fnlttSinglAcntAll, ${YEAR} 사업보고서 연결)"; call fnlttSinglAcntAll.json "corp_code=$CORP&bsns_year=$YEAR&reprt_code=11011&fs_div=CFS"; ok3=$?
[ $ok1 -eq 0 ] && [ $ok2 -eq 0 ] && [ $ok3 -eq 0 ] && echo "→ 키 정상" || { echo "→ 실패한 항목이 있습니다(status 코드는 OpenDART 개발가이드 참고: 010 미등록 키, 011 사용 불가 키, 020 한도 초과)"; exit 1; }
