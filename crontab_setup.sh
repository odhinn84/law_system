#!/bin/bash
# 매일 오전 6시 파이프라인 실행 cron 등록
# 사용법: bash crontab_setup.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE_CMD="cd $SCRIPT_DIR/pipeline && python run_pipeline.py"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

CRON_JOB="0 6 * * * $PIPELINE_CMD >> $LOG_DIR/cron.log 2>&1"

# 기존 cron에 추가 (중복 방지)
(crontab -l 2>/dev/null | grep -v "run_pipeline"; echo "$CRON_JOB") | crontab -

echo "cron 등록 완료:"
crontab -l | grep run_pipeline
