"""
Ollama(gemma4:26b)로 법안 분석 → 요약 + 집단 분류 → SQLite 저장
"""
import os
import json
import sqlite3
import logging
import time
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:26b")
DB_PATH = os.path.join(os.path.dirname(__file__), "../local_db/bills.db")
MAX_RETRIES = 3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")


# ── 분류 체계 ────────────────────────────────────────────
# 직업군: LLM이 법안 내용 기반으로 자유롭게 도출
# (추후 국가 직업 분류 체계 도입 시 이 위치에 상수 정의)
AGE_LIST = ["아동(0~12)", "청소년(13~18)", "청년(19~34)", "중장년(35~59)", "노년(60+)"]
SOCIAL_LIST = [
    "취약계층", "장애인", "여성", "다문화가정", "1인가구",
    "저소득층", "임신·육아", "학부모", "세입자", "자가소유자", "중소기업", "대기업",
]
REGION_LIST = ["서울", "수도권", "비수도권", "농어촌", "도심", "지방중소도시"]


# ── 프롬프트 ─────────────────────────────────────────────
ANALYSIS_PROMPT = """당신은 대한민국 법안을 시민 친화적으로 분석하는 전문가입니다.
아래 법안을 분석하고 반드시 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요.

법안명: {title}
제안이유 및 주요내용:
{summary}

응답 JSON 형식:
{{
  "bill_summary": "일반 시민이 이해할 수 있는 요약 (200자 이내, 쉬운 말로)",
  "core_change": "기존과 달라지는 핵심 내용 (1~2문장)",
  "impact_direction": "positive 또는 negative 또는 mixed 또는 neutral",
  "impact_detail": "어떤 면에서 긍정/부정인지 간략히 (1문장)",
  "affected_occupations": ["법안과 직접 관련된 직업군을 자유롭게 명시, 예: 의사, 간호사, 건설업자 등. 해당 없으면 []"],
  "affected_ages": {age_list},
  "affected_social": {social_list},
  "affected_regions": {region_list},
  "keywords": ["키워드1", "키워드2", "키워드3"],
  "urgency": "high 또는 medium 또는 low"
}}

주의:
- affected_occupations는 법안 내용 기반으로 자유롭게 작성 (구체적 직업명 사용)
- affected_age/social/region은 위 제시 목록에서만 선택, 해당 없으면 빈 배열 []
- urgency는 시민 일상생활 영향도 기준
- JSON 외 다른 텍스트 출력 금지"""


def build_prompt(bill: dict) -> str:
    return ANALYSIS_PROMPT.format(
        title=bill["title"],
        summary=bill["summary"][:3000],  # 토큰 절약
        age_list=json.dumps(AGE_LIST, ensure_ascii=False),
        social_list=json.dumps(SOCIAL_LIST, ensure_ascii=False),
        region_list=json.dumps(REGION_LIST, ensure_ascii=False),
    )


# ── LLM 호출 ─────────────────────────────────────────────
def call_llm(prompt: str) -> dict:
    """Ollama 호출 + JSON 파싱. 실패 시 MAX_RETRIES 재시도."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            raw = resp.choices[0].message.content.strip()

            # ```json ... ``` 래핑 제거
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            return json.loads(raw)

        except json.JSONDecodeError as e:
            log.warning("JSON 파싱 실패 (시도 %d/%d): %s", attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                time.sleep(2)
        except Exception as e:
            log.error("LLM 호출 오류 (시도 %d/%d): %s", attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                time.sleep(5)

    return {}  # 모든 재시도 실패


# ── 결과 저장 ────────────────────────────────────────────
def save_analysis(bill_id: str, result: dict, failed: bool = False):
    def join(lst):
        return "|".join(lst) if isinstance(lst, list) else ""

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO bill_analysis
        (bill_id, bill_summary, core_change, impact_direction, impact_detail,
         affected_occ, affected_age, affected_social, affected_region,
         keywords, urgency, analyzed_at, parse_failed)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        bill_id,
        result.get("bill_summary", ""),
        result.get("core_change", ""),
        result.get("impact_direction", "neutral"),
        result.get("impact_detail", ""),
        join(result.get("affected_occupations", [])),
        join(result.get("affected_ages", [])),
        join(result.get("affected_social", [])),
        join(result.get("affected_regions", [])),
        join(result.get("keywords", [])),
        result.get("urgency", "low"),
        datetime.now().isoformat(),
        1 if failed else 0,
    ))
    conn.commit()
    conn.close()


# ── 메인 분석 흐름 ───────────────────────────────────────
def analyze_pending(batch_size: int = 30):
    """미분석 법안을 batch_size만큼 가져와 분석"""
    from collect import get_unanalyzed_bills

    bills = get_unanalyzed_bills(limit=batch_size)
    log.info("분석 대상: %d건", len(bills))

    success, fail = 0, 0
    for i, bill in enumerate(bills, 1):
        log.info("[%d/%d] %s", i, len(bills), bill["title"][:40])
        prompt = build_prompt(bill)
        result = call_llm(prompt)

        if result:
            save_analysis(bill["bill_id"], result, failed=False)
            success += 1
        else:
            save_analysis(bill["bill_id"], {}, failed=True)
            fail += 1
            log.warning("분석 실패 저장: %s", bill["bill_id"])

        time.sleep(1)  # Ollama 부하 조절

    log.info("분석 완료 — 성공: %d, 실패: %d", success, fail)
    return success, fail


if __name__ == "__main__":
    analyze_pending(batch_size=10)
