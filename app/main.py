"""
Streamlit 앱 메인 진입점
GitHub raw URL에서 CSV를 읽어 표시
Streamlit >= 1.36 필요 (st.navigation)
"""
import streamlit as st

st.set_page_config(
    page_title="국회 법안 분석",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

import pandas as pd
import requests
from datetime import datetime

# ── 설정 ────────────────────────────────────────────────
try:
    GITHUB_USER = st.secrets.get("GITHUB_USER", "odhinn84")
    GITHUB_REPO = st.secrets.get("GITHUB_REPO", "law_system")
except Exception:
    GITHUB_USER = "odhinn84"
    GITHUB_REPO = "law_system"
BRANCH = "main"
BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{BRANCH}/data"

# ── KSCO 직업 분류 ───────────────────────────────────────
KSCO_GROUPS = {
    "관리자": [
        "공공·기업 고위직", "행정·경영지원 관리직", "전문서비스 관리직",
        "건설·생산 관련 관리직", "판매·고객서비스 관리직",
    ],
    "전문가 및 관련 종사자": [
        "과학 전문가 및 관련직", "정보통신 전문가 및 기술직", "공학 전문가 및 기술직",
        "보건 전문가 및 관련직", "사회복지·종교 전문가 및 관련직", "교육 전문가 및 관련직",
        "법률·행정 전문직", "경영·금융 전문가 및 관련직", "문화·예술·스포츠 전문가 및 관련직",
    ],
    "사무 종사자": [
        "경영·회계 관련 사무직", "금융 사무직", "법률·감사 사무직", "기타 사무직",
    ],
    "서비스 종사자": [
        "경찰·소방·보안 서비스직", "돌봄·보건 서비스직", "미용·예식 서비스직",
        "운송·여가 서비스직", "조리·음식 서비스직",
    ],
    "판매 종사자": ["영업직", "판매직"],
    "농림어업 숙련 종사자": ["농업 숙련직", "임업 숙련직", "어업 숙련직"],
    "기능원 및 관련 기능 종사자": [
        "건설·광업 관련 기능직", "금속 성형 관련 기능직", "운송·기계 관련 기능직",
        "전기·전자 관련 기능직", "정보통신·방송장비 관련 기능직", "식품가공 관련 기능직",
        "섬유·의복·가죽 관련 기능직", "목재·가구·악기 관련 기능직", "기타 기능직",
    ],
    "장치·기계 조작 및 조립 종사자": [
        "식품가공 장치·기계 조작직", "섬유·신발 장치·기계 조작직", "화학 관련 장치·기계 조작직",
        "금속·비금속 장치·기계 조작직", "기계 제조 장치·기계 조작직", "전기·전자 장치·기계 조작직",
        "운전·운송 관련직", "상하수도·재활용 처리직", "기타 장치·기계 조작직",
    ],
    "단순 노무 종사자": [
        "건설·광업 단순 노무직", "운송 관련 단순 노무직", "제조 관련 단순 노무직",
        "청소·경비 단순 노무직", "가사·음식·판매 단순 노무직", "농림어업·기타 단순 노무직",
    ],
    "군인": ["군인"],
}

IMPACT_EMOJI = {
    "positive": "🟢 긍정",
    "negative": "🔴 부정",
    "mixed": "🟡 혼재",
    "neutral": "⚪ 중립",
}


# ── 데이터 로딩 ──────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_bills() -> pd.DataFrame:
    url = f"{BASE_URL}/bills.csv"
    df = pd.read_csv(url, encoding="utf-8-sig")
    for col in ["affected_occ", "affected_age", "affected_social", "affected_region", "keywords"]:
        df[col] = df[col].fillna("").apply(lambda x: x.split("|") if x else [])
    return df


@st.cache_data(ttl=3600)
def load_meta() -> dict:
    try:
        stats = requests.get(f"{BASE_URL}/stats.json", timeout=5).json()
        updated = requests.get(f"{BASE_URL}/last_updated.json", timeout=5).json()
        return {**stats, **updated}
    except Exception:
        return {}


# ── 공통 컴포넌트 ────────────────────────────────────────
def render_bill_card(row, show_impact: bool = False):
    with st.container(border=True):
        col1, col2 = st.columns([5, 1])
        with col1:
            st.markdown(f"**{row['title']}**")
            st.caption(
                f"📅 {row['propose_date']} &nbsp;|&nbsp; "
                f"🏛 {row['committee']} &nbsp;|&nbsp; "
                f"👤 {row['proposer']} ({row['party']})"
            )
            st.write(row["summary"] or "요약 없음")
            tags = list(row["affected_occ"]) + list(row["affected_age"]) + list(row["affected_social"])
            if tags:
                st.markdown(" ".join(f"`{t}`" for t in tags if t))
        with col2:
            if show_impact:
                impact = IMPACT_EMOJI.get(row.get("impact_direction", ""), "")
                if impact:
                    st.markdown(impact)
                detail = row.get("impact_detail", "")
                if detail:
                    st.caption(detail)
            st.markdown(f"[원문 보기]({row['link']})")


def sidebar_meta(df: pd.DataFrame):
    meta = load_meta()
    if meta.get("updated_at"):
        dt = datetime.fromisoformat(meta["updated_at"])
        st.sidebar.caption(f"최종 갱신: {dt.strftime('%Y-%m-%d %H:%M')}")
    st.sidebar.caption(f"총 법안: **{len(df):,}건**")


# ── 페이지 함수 ──────────────────────────────────────────
def page_home():
    df = load_bills()
    sidebar_meta(df)

    st.title("🏠 최근 법안 현황")
    col1, col2, col3 = st.columns(3)
    col1.metric("전체 법안", f"{len(df):,}건")
    col2.metric("처리 완료", f"{df['status'].isin(['가결','부결','대안반영폐기','철회']).sum():,}건")
    col3.metric("심사 중", f"{(~df['status'].isin(['가결','부결','대안반영폐기','철회'])).sum():,}건")

    st.markdown("---")
    st.subheader("최근 발의 법안 (상위 10건)")
    for _, row in df.head(10).iterrows():
        render_bill_card(row)


def page_search():
    df = load_bills()
    sidebar_meta(df)

    st.title("🔍 법안 검색")
    col1, col2 = st.columns(2)
    keyword = col1.text_input("키워드 검색", placeholder="예: 의료, 청년, 부동산")
    status_filter = col2.multiselect("처리상태", df["status"].dropna().unique().tolist())

    filtered = df.copy()
    if keyword:
        filtered = filtered[
            filtered["title"].str.contains(keyword, na=False) |
            filtered["summary"].str.contains(keyword, na=False)
        ]
    if status_filter:
        filtered = filtered[filtered["status"].isin(status_filter)]

    st.caption(f"{len(filtered):,}건 검색됨")
    for _, row in filtered.head(30).iterrows():
        render_bill_card(row)


def page_my_bills():
    df = load_bills()
    sidebar_meta(df)

    st.title("👤 나에게 관련된 법안")
    st.caption("직업·연령·지역을 선택하면 관련 법안과 영향 방향을 보여줍니다.")

    col1, col2 = st.columns(2)
    with col1:
        major_occ = st.selectbox("직업 대분류 (KSCO)", ["선택 안함"] + list(KSCO_GROUPS.keys()))
        sel_occ = st.multiselect("직업 중분류", KSCO_GROUPS[major_occ] if major_occ != "선택 안함" else [])
        sel_age = st.multiselect(
            "연령대",
            ["아동(0~12)", "청소년(13~18)", "청년(19~34)", "중장년(35~59)", "노년(60+)"],
        )
    with col2:
        all_social = sorted({t for lst in df["affected_social"] for t in lst if t})
        sel_social = st.multiselect("사회적 집단", all_social)
        all_region = sorted({t for lst in df["affected_region"] for t in lst if t})
        sel_region = st.multiselect("지역", all_region)

    sel_impact = st.multiselect(
        "영향 방향 필터",
        ["positive", "negative", "mixed", "neutral"],
        format_func=lambda x: IMPACT_EMOJI.get(x, x),
    )

    filtered = df.copy()
    for col, sel in [("affected_occ", sel_occ), ("affected_age", sel_age),
                     ("affected_social", sel_social), ("affected_region", sel_region)]:
        if sel:
            filtered = filtered[filtered[col].apply(lambda lst: any(s in lst for s in sel))]
    if sel_impact:
        filtered = filtered[filtered["impact_direction"].isin(sel_impact)]
    filtered = filtered.sort_values("propose_date", ascending=False)

    st.caption(f"{len(filtered):,}건 해당")
    if filtered.empty:
        st.info("조건에 맞는 법안이 없습니다. 항목을 선택해 주세요.")
    for _, row in filtered.head(30).iterrows():
        render_bill_card(row, show_impact=True)


def page_member_bills():
    df = load_bills()
    sidebar_meta(df)

    st.title("🗺️ 의원별 발의 법안")
    st.caption("의원을 검색하면 발의하거나 참여한 법안을 볼 수 있습니다.")

    tab_map, tab_name = st.tabs(["🗺️ 지역구 지도로 찾기", "🔎 이름으로 바로 찾기"])
    selected_proposer = None

    with tab_map:
        SIDO_LIST = ["서울","부산","대구","인천","광주","대전","울산","세종",
                     "경기","강원","충북","충남","전북","전남","경북","경남","제주"]
        sido = st.selectbox("시·도 선택", ["선택하세요"] + SIDO_LIST)
        if sido != "선택하세요":
            st.info(f"💡 **{sido}** 지역구 의원 지도는 의원 정보 API 연동 후 활성화됩니다. 이름 검색 탭을 이용해 주세요.")

    with tab_name:
        all_proposers = sorted(df["proposer"].dropna().unique().tolist())
        name_query = st.text_input("의원 이름 입력", placeholder="예: 홍길동")
        if name_query:
            matched = [p for p in all_proposers if name_query in p]
            if not matched:
                st.warning(f"'{name_query}' 의원을 찾을 수 없습니다.")
            elif len(matched) == 1:
                selected_proposer = matched[0]
            else:
                selected_proposer = st.selectbox("의원 선택", matched)
        else:
            sel = st.selectbox("또는 목록에서 선택", ["선택하세요"] + all_proposers)
            if sel != "선택하세요":
                selected_proposer = sel

    if selected_proposer:
        st.markdown("---")
        st.subheader(f"📋 {selected_proposer} 의원 발의/참여 법안")
        member_bills = df[df["proposer"].str.contains(selected_proposer, na=False)]
        if member_bills.empty:
            st.info("해당 의원의 법안이 없습니다.")
        else:
            col1, col2 = st.columns(2)
            col1.metric("총 법안 수", f"{len(member_bills)}건")
            col2.metric("처리 완료", f"{member_bills['status'].isin(['가결','부결','대안반영폐기','철회']).sum()}건")
            sort_opt = st.selectbox("정렬", ["최신순", "처리상태순"], key="member_sort")
            if sort_opt == "최신순":
                member_bills = member_bills.sort_values("propose_date", ascending=False)
            else:
                member_bills = member_bills.sort_values("status")
            for _, row in member_bills.head(30).iterrows():
                render_bill_card(row)


def page_stats():
    import plotly.express as px
    df = load_bills()
    sidebar_meta(df)

    st.title("📊 통계")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("처리상태별 법안 수")
        status_cnt = df["status"].value_counts().reset_index()
        status_cnt.columns = ["상태", "건수"]
        fig = px.bar(status_cnt, x="상태", y="건수", color="상태")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("영향 방향 분포")
        impact_cnt = df["impact_direction"].value_counts().reset_index()
        impact_cnt.columns = ["방향", "건수"]
        impact_cnt["방향"] = impact_cnt["방향"].map(IMPACT_EMOJI)
        fig2 = px.pie(impact_cnt, names="방향", values="건수")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("직업군별 영향 법안 수 (KSCO 중분류)")
    occ_counts = {}
    for lst in df["affected_occ"]:
        for item in lst:
            if item:
                occ_counts[item] = occ_counts.get(item, 0) + 1
    if occ_counts:
        occ_df = pd.DataFrame(list(occ_counts.items()), columns=["직업군", "건수"])
        occ_df = occ_df.sort_values("건수", ascending=True)
        fig3 = px.bar(occ_df, x="건수", y="직업군", orientation="h")
        st.plotly_chart(fig3, use_container_width=True)

    st.subheader("정당별 발의 현황")
    party_cnt = df["party"].value_counts().head(10).reset_index()
    party_cnt.columns = ["정당", "건수"]
    fig4 = px.bar(party_cnt, x="정당", y="건수", color="정당")
    st.plotly_chart(fig4, use_container_width=True)


def page_about():
    st.title("ℹ️ 서비스 소개")

    st.markdown("""
    ## 국회 법안 분석 시스템이란?

    국회에서 발의되는 수천 건의 법안을 일반 시민이 쉽게 파악하기 어렵다는 문제 의식에서 출발했습니다.
    이 서비스는 법안의 핵심 내용을 쉬운 언어로 요약하고, 어떤 직업군·연령대·사회 집단에
    영향을 미치는지 자동으로 분류하여 제공합니다.
    """)

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📡 데이터 출처")
        st.markdown("""
        - **법안 목록**: 열린국회정보 Open API (`nzmimeepazxkubdpn`)
        - **제안이유·주요내용**: 열린국회정보 Open API (`BPMBILLSUMMARY`)
        - **원문 링크**: 의안정보시스템 (`likms.assembly.go.kr`)
        - **수집 대상**: 제22대 국회 발의 법안 전체
        - **갱신 주기**: 매일 새벽 3시 자동 업데이트
        """)

        st.markdown("### 🗂️ 직업 분류 기준")
        st.markdown("""
        직업군 분류는 통계청의 **한국표준직업분류(KSCO) 8차 개정** 중분류 체계를 따릅니다.
        자의적인 분류 대신 국가 공식 기준을 사용하여 일관성을 높였습니다.
        """)

    with col2:
        st.markdown("### 🤖 분석 방법")
        st.markdown("""
        법안의 제안이유 및 주요내용 텍스트를 LLM(대형 언어 모델)에 입력하여 다음 항목을 자동 생성합니다.

        - **요약**: 시민이 이해할 수 있는 200자 이내 요약
        - **핵심 변경사항**: 기존 법과 달라지는 점
        - **영향 집단**: 직업군 / 연령대 / 사회적 집단 / 지역
        - **영향 방향**: 긍정 / 부정 / 혼재 / 중립
        """)

        st.markdown("### ⚙️ 사용 모델")
        st.markdown("""
        | 항목 | 내용 |
        |------|------|
        | 모델 | Google Gemma 3 (27B) |
        | 실행 방식 | 로컬 서버 (Ollama) |
        | API | OpenAI 호환 API |
        | 처리 속도 | 법안 1건 약 1분 |
        """)

    st.markdown("---")
    st.markdown("### ⚠️ 이용 시 유의사항")
    st.info("""
    - 법안 요약과 집단 분류는 LLM이 자동 생성한 결과로, **오류가 포함될 수 있습니다.**
    - 중요한 판단은 반드시 **원문 법안**을 직접 확인하시기 바랍니다.
    - 법안 분석은 최신 법안부터 순차 처리되므로, 오래된 법안은 분석이 누락될 수 있습니다.
    - 본 서비스는 법률 자문을 제공하지 않습니다.
    """)

    st.markdown("---")
    st.caption("데이터 출처: 열린국회정보 (open.assembly.go.kr) | 직업 분류: 통계청 한국표준직업분류 8차")


# ── 앱 실행 ──────────────────────────────────────────────
def main():
    try:
        # st.navigation에서 각 페이지 함수가 직접 load_bills()를 호출하므로
        # 에러 처리는 각 페이지 내에서 수행
        pass
    except Exception as e:
        st.error(f"초기화 오류: {e}")
        st.stop()

    pg = st.navigation([
        st.Page(page_home,         title="홈",              icon="🏠", default=True),
        st.Page(page_search,       title="법안 검색",        icon="🔍"),
        st.Page(page_my_bills,     title="나에게 관련된 법안", icon="👤"),
        st.Page(page_member_bills, title="의원별 법안",       icon="🗺️"),
        st.Page(page_stats,        title="통계",             icon="📊"),
        st.Page(page_about,        title="서비스 소개",       icon="ℹ️"),
    ])
    pg.run()


if __name__ == "__main__":
    main()
