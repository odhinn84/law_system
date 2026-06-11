"""
국회 열린데이터광장 API로 법안 수집 → 로컬 SQLite 저장
"""
import os
import sqlite3
import requests
import logging
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ASSEMBLY_API_KEY")
ASSEMBLY_UNIT = os.getenv("ASSEMBLY_UNIT", "22")
DB_PATH = os.path.join(os.path.dirname(__file__), "../local_db/bills.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ── DB 초기화 ────────────────────────────────────────────
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            bill_id      TEXT PRIMARY KEY,
            bill_no      TEXT,
            title        TEXT,
            proposer     TEXT,
            party        TEXT,
            committee    TEXT,
            propose_date TEXT,
            status       TEXT,
            summary      TEXT,
            link         TEXT,
            collected_at TEXT
        )
    """)
    # 기존 DB에 bill_no 컬럼 없으면 추가 (마이그레이션)
    try:
        conn.execute("ALTER TABLE bills ADD COLUMN bill_no TEXT")
    except Exception:
        pass  # 이미 있으면 무시
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bill_analysis (
            bill_id          TEXT PRIMARY KEY,
            bill_summary     TEXT,
            core_change      TEXT,
            impact_direction TEXT,
            impact_detail    TEXT,
            affected_occ     TEXT,
            affected_age     TEXT,
            affected_social  TEXT,
            affected_region  TEXT,
            keywords         TEXT,
            urgency          TEXT,
            analyzed_at      TEXT,
            parse_failed     INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()
    log.info("DB 초기화 완료: %s", DB_PATH)


# ── 국회 API 호출 ────────────────────────────────────────
def fetch_bill_list(page: int = 1, page_size: int = 100) -> dict:
    """법률안 목록 조회 (열린국회정보 nzmimeepazxkubdpn)"""
    url = "https://open.assembly.go.kr/portal/openapi/nzmimeepazxkubdpn"
    params = {
        "KEY": API_KEY,
        "Type": "json",
        "pIndex": page,
        "pSize": page_size,
        "AGE": ASSEMBLY_UNIT,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_bill_summary(bill_no: str) -> str:
    """BPMBILLSUMMARY API로 제안이유 및 주요내용 텍스트 조회"""
    url = "https://open.assembly.go.kr/portal/openapi/BPMBILLSUMMARY"
    params = {"KEY": API_KEY, "Type": "json", "BILL_NO": bill_no}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["BPMBILLSUMMARY"][1]["row"][0].get("SUMMARY", "")
    except (KeyError, IndexError):
        return ""


def fetch_bill_link(bill_id: str) -> str:
    """ALLBILL API로 공식 LINK_URL 조회. 실패 시 직접 조립."""
    url = "https://open.assembly.go.kr/portal/openapi/ALLBILL"
    # ALLBILL은 BILL_NO 필요 — 호출 전 bill_no를 넘기도록 변경
    # 여기서는 fallback만 제공; save_bills에서 직접 호출
    return f"https://likms.assembly.go.kr/bill/billDetail.do?billId={bill_id}"


def make_bill_link(bill_id: str, api_link: str = "") -> str:
    """ALLBILL의 LINK_URL 우선, 없으면 직접 조립"""
    if api_link and api_link.startswith("http"):
        return api_link
    return f"https://likms.assembly.go.kr/bill/billDetail.do?billId={bill_id}"


# ── 저장 ────────────────────────────────────────────────
def save_bills(bills: list[dict]):
    conn = sqlite3.connect(DB_PATH)
    inserted = 0
    skipped = 0
    for b in bills:
        bill_id = b.get("BILL_ID", "")
        if not bill_id:
            continue
        exists = conn.execute(
            "SELECT 1 FROM bills WHERE bill_id = ?", (bill_id,)
        ).fetchone()
        if exists:
            skipped += 1
            continue
        conn.execute(
            """INSERT OR IGNORE INTO bills
               (bill_id, bill_no, title, proposer, party, committee,
                propose_date, status, summary, link, collected_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                bill_id,
                b.get("BILL_NO", ""),
                b.get("BILL_NAME", ""),
                b.get("PROPOSER", ""),
                b.get("POLY_NM", ""),
                b.get("COMMITTEE", ""),
                b.get("PROPOSE_DT", ""),
                b.get("PROC_RESULT", b.get("BILL_STATUS", "")),
                "",  # summary는 update_summaries(BPMBILLSUMMARY)에서 채움
                make_bill_link(bill_id, b.get("DETAIL_LINK", "")),
                datetime.now().isoformat(),
            ),
        )
        inserted += 1
    conn.commit()
    conn.close()
    return inserted, skipped


def update_bill_summary(bill_id: str, summary: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE bills SET summary = ? WHERE bill_id = ?",
        (summary, bill_id)
    )
    conn.commit()
    conn.close()


# ── 메인 수집 흐름 ───────────────────────────────────────
def collect_bills(max_pages: int = 300, fetch_detail: bool = True):
    """
    법안 목록 수집. 이미 존재하는 bill_id는 건너뜀(증분 수집).
    max_pages: 최대 페이지 수 (100건/페이지 → 300페이지 = 최대 30,000건)
    초기 전체 수집: max_pages=300 / 일일 증분: 기본값 유지
    """
    init_db()
    total_inserted = 0

    for page in range(1, max_pages + 1):
        log.info("페이지 %d 수집 중...", page)
        try:
            data = fetch_bill_list(page=page)
        except Exception as e:
            log.error("API 오류 (page %d): %s", page, e)
            break

        # 응답 파싱
        try:
            rows = data["nzmimeepazxkubdpn"][1]["row"]
        except (KeyError, IndexError):
            log.info("더 이상 데이터 없음 (page %d)", page)
            break

        if not rows:
            break

        inserted, skipped = save_bills(rows)
        total_inserted += inserted
        log.info("  → 신규 %d건 저장, %d건 스킵", inserted, skipped)

        # 일일 증분 수집: 신규 건 없으면 완료로 판단
        # 초기 전체 수집(max_pages=300)에서는 끝까지 순회
        if inserted == 0 and max_pages <= 10:
            log.info("신규 법안 없음 — 증분 수집 완료")
            break

    log.info("수집 완료. 총 신규 저장: %d건", total_inserted)

    # 상세 정보(제안이유) 업데이트
    if fetch_detail:
        update_summaries()

    return total_inserted


def update_summaries(batch_size: int = 0):
    """
    BPMBILLSUMMARY API로 제안이유 텍스트 채움.
    batch_size=0 이면 미수집 전체 처리 (초기 대량 수집용).
    batch_size>0 이면 해당 건수만 처리 (일일 증분용).
    """
    import time
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT bill_id, bill_no FROM bills WHERE (summary = '' OR summary IS NULL)"
    if batch_size > 0:
        query += f" LIMIT {batch_size}"
    rows = conn.execute(query).fetchall()
    conn.close()

    total = len(rows)
    log.info("제안이유 업데이트 대상: %d건", total)
    for i, (bill_id, bill_no) in enumerate(rows, 1):
        if i % 100 == 0:
            log.info("  진행: %d / %d건", i, total)
        try:
            summary = fetch_bill_summary(bill_no)
            if summary:
                update_bill_summary(bill_id, summary)
            else:
                log.debug("제안이유 없음: %s", bill_id)
        except Exception as e:
            log.warning("제안이유 조회 실패 (%s): %s", bill_id, e)
        time.sleep(0.3)  # API 부하 조절


def get_unanalyzed_bills(limit: int = 50) -> list[dict]:
    """분석 안 된 법안 목록 반환"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT b.bill_id, b.bill_no, b.title, b.proposer, b.party,
               b.committee, b.propose_date, b.status, b.summary, b.link
        FROM bills b
        LEFT JOIN bill_analysis a ON b.bill_id = a.bill_id
        WHERE a.bill_id IS NULL AND b.summary IS NOT NULL AND b.summary != ''
        ORDER BY b.propose_date DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    cols = ["bill_id","bill_no","title","proposer","party","committee",
            "propose_date","status","summary","link"]
    return [dict(zip(cols, r)) for r in rows]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="22대 국회 전체 수집 (max_pages=300)")
    parser.add_argument("--pages", type=int, default=5, help="수집 페이지 수 (기본 5)")
    parser.add_argument("--no-detail", action="store_true", help="제안이유 수집 건너뜀")
    args = parser.parse_args()

    max_pages = 300 if args.all else args.pages
    collect_bills(max_pages=max_pages, fetch_detail=not args.no_detail)
