"""
Streamlit 앱 메인 진입점
GitHub raw URL에서 CSV를 읽어 표시
"""
import streamlit as st

st.set_page_config(
    page_title="국회 법안 분석",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

import pandas as pd
import json
import requests
from datetime import datetime

# ── 설정 ────────────────────────────────────────────────
# Streamlit Cloud secrets 또는 환경변수로 주입
GITHUB_USER = st.secrets.get("GITHUB_USER", "your_username")
GITHUB_REPO = st.secrets.get("GITHUB_REPO", "your_repo")
BRANCH = "main"

BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{BRANCH}/data"


# ── 데이터 로딩 ──────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_bills() -> pd.DataFrame:
    url = f"{BASE_URL}/bills.csv"
    df = pd.read_csv(url, encoding="utf-8-sig")
    # 영향 집단 필드를 리스트로 파싱
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
IMPACT_EMOJI = {
    "positive": "🟢 긍정",
    "negative": "🔴 부정",
    "mixed": "🟡 혼재",
    "neutral": "⚪ 중립",
}
URGENCY_EMOJI = {
    "high": "🔥 높음",
    "medium": "📌 중간",
    "low": "💤 낮음",
}


def render_bill_card(row):
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

            # 영향 집단 태그
            tags = (
                list(row["affected_occ"]) +
                list(row["affected_age"]) +
                list(row["affected_social"])
            )
            if tags:
                st.markdown(" ".join(f"`{t}`" for t in tags if t))

        with col2:
            st.markdown(IMPACT_EMOJI.get(row["impact_direction"], ""))
            st.markdown(URGENCY_EMOJI.get(row["urgency"], ""))
            st.markdown(f"[원문 보기]({row['link']})")


# ── 사이드바 ─────────────────────────────────────────────
def render_sidebar(df: pd.DataFrame):
    st.sidebar.title("⚖️ 국회 법안 분석")

    meta = load_meta()
    if meta.get("updated_at"):
        dt = datetime.fromisoformat(meta["updated_at"])
        st.sidebar.caption(f"최종 갱신: {dt.strftime('%Y-%m-%d %H:%M')}")

    st.sidebar.markdown("---")
    page = st.sidebar.radio(
        "페이지",
        ["🏠 홈", "🔍 법안 검색", "👤 나에게 관련된 법안", "🗺️ 의원별 법안", "📊 통계"],
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"총 법안 수: **{len(df):,}건**")

    return page


# ── 각 페이지 ────────────────────────────────────────────
def page_home(df: pd.DataFrame):
    st.title("🏠 최근 법안 현황")
    meta = load_meta()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("전체 법안", f"{len(df):,}건")
    col2.metric("긴급도 높음", f"{(df['urgency']=='high').sum():,}건")
    col3.metric("긍정 법안", f"{(df['impact_direction']=='positive').sum():,}건")
    col4.metric("부정 법안", f"{(df['impact_direction']=='negative').sum():,}건")

    st.markdown("---")
    st.subheader("최근 발의 법안 (상위 10건)")
    recent = df.head(10)
    for _, row in recent.iterrows():
        render_bill_card(row)


def page_search(df: pd.DataFrame):
    st.title("🔍 법안 검색")

    col1, col2, col3 = st.columns(3)
    keyword = col1.text_input("키워드 검색", placeholder="예: 의료, 청년, 부동산")
    status_filter = col2.multiselect("처리상태", df["status"].dropna().unique().tolist())
    impact_filter = col3.multiselect(
        "영향 방향",
        ["positive", "negative", "mixed", "neutral"],
        format_func=lambda x: IMPACT_EMOJI.get(x, x),
    )

    filtered = df.copy()
    if keyword:
        mask = (
            df["title"].str.contains(keyword, na=False) |
            df["summary"].str.contains(keyword, na=False)
        )
        filtered = filtered[mask]
    if status_filter:
        filtered = filtered[filtered["status"].isin(status_filter)]
    if impact_filter:
        filtered = filtered[filtered["impact_direction"].isin(impact_filter)]

    st.caption(f"{len(filtered):,}건 검색됨")
    for _, row in filtered.head(30).iterrows():
        render_bill_card(row)


def page_my_bills(df: pd.DataFrame):
    st.title("👤 나에게 관련된 법안")
    st.caption("직업·연령·지역을 선택하면 관련 법안을 보여줍니다.")

    all_occ = sorted({t for lst in df["affected_occ"] for t in lst if t})
    all_age = sorted({t for lst in df["affected_age"] for t in lst if t})
    all_social = sorted({t for lst in df["affected_social"] for t in lst if t})
    all_region = sorted({t for lst in df["affected_region"] for t in lst if t})

    col1, col2 = st.columns(2)
    sel_occ = col1.multiselect("직업군", all_occ)
    sel_age = col1.multiselect("연령대", all_age)
    sel_social = col2.multiselect("사회적 집단", all_social)
    sel_region = col2.multiselect("지역", all_region)
    sel_impact = st.multiselect(
        "영향 방향 필터",
        ["positive", "negative", "mixed", "neutral"],
        format_func=lambda x: IMPACT_EMOJI.get(x, x),
    )

    selections = {
        "affected_occ": sel_occ,
        "affected_age": sel_age,
        "affected_social": sel_social,
        "affected_region": sel_region,
    }

    filtered = df.copy()
    for col, sel in selections.items():
        if sel:
            filtered = filtered[
                filtered[col].apply(lambda lst: any(s in lst for s in sel))
            ]
    if sel_impact:
        filtered = filtered[filtered["impact_direction"].isin(sel_impact)]

    # 긴급도 높은 것 먼저
    urgency_order = {"high": 0, "medium": 1, "low": 2}
    filtered = filtered.sort_values("urgency", key=lambda s: s.map(urgency_order))

    st.caption(f"{len(filtered):,}건 해당")
    if filtered.empty:
        st.info("조건에 맞는 법안이 없습니다. 항목을 선택해 주세요.")
    for _, row in filtered.head(30).iterrows():
        render_bill_card(row)



def page_member_bills(df: pd.DataFrame):
    st.title("🗺️ 의원별 발의 법안")
    st.caption("의원을 검색하면 발의하거나 참여한 법안을 볼 수 있습니다.")

    tab_map, tab_name = st.tabs(["🗺️ 지역구 지도로 찾기", "🔎 이름으로 바로 찾기"])

    selected_proposer = None

    # ── 탭1: 지역구 지도 검색 ──────────────────────────────
    with tab_map:
        st.markdown("#### 지역구 선택")

        # 시도 → 시군구 → 지역구 순차 선택
        # 의원 데이터는 bills CSV의 proposer/party 컬럼 기반
        # 실제 지역구 데이터는 국회 의원 API에서 추가 수집 필요
        # 현재는 시도/시군구 selectbox + SVG 지도 안내로 구현

        SIDO_LIST = [
            "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
            "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
        ]

        col1, col2 = st.columns(2)
        sido = col1.selectbox("시·도 선택", ["선택하세요"] + SIDO_LIST)

        if sido != "선택하세요":
            # bills CSV에서 해당 지역 관련 의원 추출 (지역구 데이터 추가 전 임시)
            # 추후 의원 API 데이터(DISTRICT 필드)와 연동
            st.info(
                f"💡 **{sido}** 지역구 의원 지도는 의원 정보 API 연동 후 활성화됩니다. "
                "현재는 아래 이름 검색 탭을 이용해 주세요."
            )

            # 지도 플레이스홀더 — folium + 선거구 GeoJSON 연동 시 교체
            st.markdown("""
            > **지도 연동 계획**
            > - 데이터: 중앙선거관리위원회 선거구 GeoJSON
            > - 라이브러리: `streamlit-folium`
            > - 클릭 시 해당 지역구 의원 자동 선택
            """)

    # ── 탭2: 이름 검색 ─────────────────────────────────────
    with tab_name:
        st.markdown("#### 의원 이름 검색")

        # bills CSV에서 의원 목록 추출
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
            selected_proposer = st.selectbox(
                "또는 목록에서 선택", ["선택하세요"] + all_proposers
            )
            if selected_proposer == "선택하세요":
                selected_proposer = None

    # ── 선택된 의원의 법안 표시 ────────────────────────────
    if selected_proposer:
        st.markdown("---")
        st.subheader(f"📋 {selected_proposer} 의원 발의/참여 법안")

        # 대표발의자 또는 공동발의자(proposer 필드에 포함) 검색
        member_bills = df[df["proposer"].str.contains(selected_proposer, na=False)]

        if member_bills.empty:
            st.info("해당 의원의 법안이 없습니다.")
        else:
            # 요약 통계
            col1, col2, col3 = st.columns(3)
            col1.metric("총 법안 수", f"{len(member_bills)}건")
            col2.metric(
                "긍정 법안",
                f"{(member_bills['impact_direction']=='positive').sum()}건"
            )
            col3.metric(
                "긴급도 높음",
                f"{(member_bills['urgency']=='high').sum()}건"
            )

            # 정렬
            sort_opt = st.selectbox(
                "정렬",
                ["최신순", "긴급도 높은순", "긍정 영향순"],
                key="member_sort"
            )
            if sort_opt == "최신순":
                member_bills = member_bills.sort_values("propose_date", ascending=False)
            elif sort_opt == "긴급도 높은순":
                urgency_order = {"high": 0, "medium": 1, "low": 2}
                member_bills = member_bills.sort_values(
                    "urgency", key=lambda s: s.map(urgency_order)
                )
            elif sort_opt == "긍정 영향순":
                impact_order = {"positive": 0, "mixed": 1, "neutral": 2, "negative": 3}
                member_bills = member_bills.sort_values(
                    "impact_direction", key=lambda s: s.map(impact_order)
                )

            for _, row in member_bills.head(30).iterrows():
                render_bill_card(row)


def page_stats(df: pd.DataFrame):
    import plotly.express as px

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

    st.subheader("직업군별 영향 법안 수")
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


# ── 앱 실행 ──────────────────────────────────────────────
def main():
    try:
        df = load_bills()
    except Exception as e:
        st.error(f"데이터 로딩 실패: {e}")
        st.stop()

    page = render_sidebar(df)

    if page == "🏠 홈":
        page_home(df)
    elif page == "🔍 법안 검색":
        page_search(df)
    elif page == "👤 나에게 관련된 법안":
        page_my_bills(df)
    elif page == "🗺️ 의원별 법안":
        page_member_bills(df)
    elif page == "📊 통계":
        page_stats(df)


if __name__ == "__main__":
    main()
