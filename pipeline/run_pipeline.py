"""
전체 파이프라인 진입점: 수집 → 분석 → export → push
매일 cron으로 실행됨
"""
import sys
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            f"../logs/pipeline_{datetime.now().strftime('%Y%m%d')}.log",
            encoding="utf-8"
        ),
    ]
)
log = logging.getLogger(__name__)


def run():
    log.info("=" * 50)
    log.info("파이프라인 시작: %s", datetime.now().isoformat())

    # 1. 수집
    log.info("[1/3] 법안 수집")
    try:
        from collect import collect_bills
        inserted = collect_bills(max_pages=10, fetch_detail=True)
        log.info("수집 완료: 신규 %d건", inserted)
    except Exception as e:
        log.error("수집 실패: %s", e)
        sys.exit(1)

    # 2. 분석
    log.info("[2/3] LLM 분석")
    try:
        from analyze import analyze_pending
        success, fail = analyze_pending(batch_size=50)
        log.info("분석 완료: 성공 %d / 실패 %d", success, fail)
    except Exception as e:
        log.error("분석 실패: %s", e)
        sys.exit(1)

    # 3. export + push
    log.info("[3/3] CSV export & GitHub push")
    try:
        from export import export_csv, git_push
        count = export_csv()
        pushed = git_push()
        log.info("export %d건, push: %s", count, "완료" if pushed else "변경없음")
    except Exception as e:
        log.error("export/push 실패: %s", e)
        sys.exit(1)

    log.info("파이프라인 완료: %s", datetime.now().isoformat())
    log.info("=" * 50)


if __name__ == "__main__":
    run()
