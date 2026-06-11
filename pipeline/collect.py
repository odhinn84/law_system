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


def fetch_bill_detail(bill_id: str) -> dict:
    """법률안 상세 조회 (제안이유 + 주요내용)"""
    url = "https://open.assembly.go.kr/portal/openapi/nwbpacrgavhjryiph"
    params = {
        "KEY": API_KEY,
        "Type": "json",
        "pSize": 1,
        "BILL_ID": bill_id,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    try:
        rows = data.get("nwbpacrgavhjryiph", [{}])
        if len(rows) > 1:
            return rows[1].get("row", [{}])[0]
    except Exception:
        pass
    return {}


def make_bill_link(bill_id: str, api_link: str = "") -> str:
    """
    원문 링크 반환.
    API 응답에 LINK_URL 필드가 있으면 그 값을 우선 사용하고,
    없으면 의안정보시스템 딥링크 패턴으로 조립 (크롤링 아님).
    """
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
               (bill_id, title, proposer, party, committee,
                propose_date, status, summary, link, collected_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                bill_id,
                b.get("BILL_NAME", ""),
                b.get("PROPOSER", ""),
                b.get("POLY_NM", ""),
                b.get("COMMITTEE", ""),
                b.get("PROPOSE_DT", ""),
                b.get("PROC_RESULT", b.get("BILL_STATUS", "")),
                b.get("PROPOSE_DT", ""),  # summary는 상세 조회 후 업데이트
                make_bill_link(bill_id, b.get("LINK_URL", b.get("LINK", ""))),
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
def collect_bills(max_pages: int = 50, fetch_detail: bool = True):
    """
    법안 목록 수집. 이미 존재하는 bill_id는 건너뜀(증분 수집).
    max_pages: 최대 페이지 수 (100건/페이지 → 기본 5,000건)
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

        # 신규 건 없으면 증분 수집 완료로 판단
        if inserted == 0:
            log.info("신규 법안 없음 — 증분 수집 완료")
            break

    log.info("수집 완료. 총 신규 저장: %d건", total_inserted)

    # 상세 정보(제안이유) 업데이트
    if fetch_detail:
        update_summaries()

    return total_inserted


def update_summaries():
    """summary가 비어있는 법안의 제안이유를 상세 API로 채움"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT bill_id FROM bills WHERE summary = '' OR summary IS NULL LIMIT 200"
    ).fetchall()
    conn.close()

    log.info("제안이유 업데이트 대상: %d건", len(rows))
    for (bill_id,) in rows:
        try:
            detail = fetch_bill_detail(bill_id)
            summary = detail.get("PROPOSE_DT", "") or detail.get("DETAIL_CONTENT", "")
            # 실제 필드명은 API 응답 확인 후 조정 필요
            propose_reason = detail.get("PROPOSE_REASON", "")
            main_content = detail.get("MAIN_CONTENT", "")
            combined = f"{propose_reason} {main_content}".strip()
            if combined:
                update_bill_summary(bill_id, combined)
        except Exception as e:
            log.warning("상세 조회 실패 (%s): %s", bill_id, e)


def get_unanalyzed_bills(limit: int = 50) -> list[dict]:
    """분석 안 된 법안 목록 반환"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT b.bill_id, b.title, b.proposer, b.party,
               b.committee, b.propose_date, b.status, b.summary, b.link
        FROM bills b
        LEFT JOIN bill_analysis a ON b.bill_id = a.bill_id
        WHERE a.bill_id IS NULL AND b.summary IS NOT NULL AND b.summary != ''
        ORDER BY b.propose_date DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    cols = ["bill_id","title","proposer","party","committee",
            "propose_date","status","summary","link"]
    return [dict(zip(cols, r)) for r in rows]


if __name__ == "__main__":
    collect_bills(max_pages=5, fetch_detail=True)
