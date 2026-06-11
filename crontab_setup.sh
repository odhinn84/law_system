#!/bin/bash
# 법안 분석 시스템 cron 등록 스크립트
# 사용법: bash crontab_setup.sh
#
# 등록되는 작업:
#   - 수집 (collect): 매시간 정각 — 신규 법안 수집, 없으면 즉시 종료
#   - 분석 (analyze): 매시간 30분  — 미분석 법안 50건 처리 후 종료
#   - 배포 (export):  매일 새벽 3시 — CSV 생성 후 GitHub push

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE="$SCRIPT_DIR/pipeline"
LOG_DIR="$SCRIPT_DIR/logs"
CONDA_PYTHON=$(which python)  # conda 환경 활성화 상태에서 실행 필요

mkdir -p "$LOG_DIR"

# 기존 등록된 law_system cron 제거 후 재등록
EXISTING=$(crontab -l 2>/dev/null | grep -v "law_system")

NEW_CRONS=$(cat << CRON
# law_system: 수집 — 매시간 정각
0 * * * * cd $PIPELINE && $CONDA_PYTHON collect.py --pages 5 >> $LOG_DIR/collect.log 2>&1
# law_system: 분석 — 매시간 30분
30 * * * * cd $PIPELINE && $CONDA_PYTHON analyze.py >> $LOG_DIR/analyze.log 2>&1
# law_system: 배포 — 매일 새벽 3시
0 3 * * * cd $PIPELINE && $CONDA_PYTHON export.py >> $LOG_DIR/export.log 2>&1
CRON
)

(echo "$EXISTING"; echo "$NEW_CRONS") | crontab -

echo "✅ cron 등록 완료"
echo ""
crontab -l | grep -A1 "law_system"
echo ""
echo "로그 위치: $LOG_DIR/"
echo "  - collect.log  : 수집 로그"
echo "  - analyze.log  : 분석 로그"
echo "  - export.log   : 배포 로그"
