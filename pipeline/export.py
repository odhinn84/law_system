"""
SQLite → CSV 변환 후 GitHub push
"""
import os
import json
import sqlite3
import subprocess
import logging
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "../local_db/bills.db")
DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")
REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def export_csv():
    """분석 완료된 법안을 bills.csv로 내보냄"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    df = pd.read_sql_query("""
        SELECT
            b.bill_id,
            b.title,
            b.proposer,
            b.party,
            b.committee,
            b.propose_date,
            b.status,
            b.link,
            a.bill_summary   AS summary,
            a.core_change,
            a.impact_direction,
            a.impact_detail,
            a.affected_occ,
            a.affected_age,
            a.affected_social,
            a.affected_region,
            a.keywords,
            a.urgency,
            a.analyzed_at,
            a.parse_failed
        FROM bills b
        INNER JOIN bill_analysis a ON b.bill_id = a.bill_id
        WHERE a.parse_failed = 0
        ORDER BY b.propose_date DESC
    """, conn)
    conn.close()

    csv_path = os.path.join(DATA_DIR, "bills.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    log.info("CSV 내보냄: %d건 → %s", len(df), csv_path)

    # 통계 JSON
    stats = {
        "total_bills": len(df),
        "by_status": df["status"].value_counts().to_dict(),
        "by_urgency": df["urgency"].value_counts().to_dict(),
        "by_impact": df["impact_direction"].value_counts().to_dict(),
        "last_propose_date": df["propose_date"].max() if len(df) else "",
    }
    with open(os.path.join(DATA_DIR, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    # 갱신 시각
    with open(os.path.join(DATA_DIR, "last_updated.json"), "w", encoding="utf-8") as f:
        json.dump({"updated_at": datetime.now().isoformat()}, f)

    return len(df)


def git_push(message: str = None):
    """data/ 변경사항을 GitHub에 push"""
    if message is None:
        message = f"data: 법안 업데이트 {datetime.now().strftime('%Y-%m-%d')}"

    cmds = [
        ["git", "-C", REPO_ROOT, "add", "data/"],
        ["git", "-C", REPO_ROOT, "commit", "-m", message],
        ["git", "-C", REPO_ROOT, "push"],
    ]

    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # commit 실패는 "nothing to commit"일 수 있으므로 로그만
            if "nothing to commit" in result.stdout + result.stderr:
                log.info("변경사항 없음 — push 생략")
                return False
            log.error("git 오류: %s", result.stderr)
            raise RuntimeError(f"git 명령 실패: {' '.join(cmd)}\n{result.stderr}")
        log.info("git %s 완료", cmd[2])

    log.info("GitHub push 완료")
    return True


def export_members_csv():
    """의원 정보를 members.csv로 내보냄"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM members ORDER BY name", conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()

    if df.empty:
        log.warning("의원 데이터 없음 — python collect.py --members 먼저 실행")
        return 0

    csv_path = os.path.join(DATA_DIR, "members.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    log.info("members.csv 내보냄: %d명 → %s", len(df), csv_path)
    return len(df)


if __name__ == "__main__":
    count = export_csv()
    m_count = export_members_csv()
    git_push()
    print(f"완료: 법안 {count}건 / 의원 {m_count}명 export 및 push")
