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
    import re as _re
    df["status"] = df["status"].fillna("심사중")
    for col in ["party", "committee", "proposer", "summary", "core_change", "impact_detail"]:
        df[col] = df[col].fillna("")
    # party가 비어있는 경우 members.csv에서 발의자 이름으로 조인
    if df["party"].eq("").all():
        try:
            mdf = pd.read_csv(f"{BASE_URL}/members.csv", encoding="utf-8-sig").fillna("")
            _n2p = dict(zip(mdf["name"], mdf["party"]))
            def _party_from_proposer(p: str) -> str:
                s = _re.sub(r"의원.*", "", str(p))
                m = _re.match(r"([가-힣]{2,4})", s)
                return _n2p.get(m.group(1), "") if m else ""
            df["party"] = df["proposer"].apply(_party_from_proposer)
        except Exception:
            pass
    for col in ["affected_occ", "affected_age", "affected_social", "affected_region", "keywords", "benefited_groups", "harmed_groups"]:
        df[col] = df[col].fillna("").apply(lambda x: x.split("|") if x else [])
    return df


@st.cache_data(ttl=3600)
def load_members() -> pd.DataFrame:
    url = f"{BASE_URL}/members.csv"
    try:
        df = pd.read_csv(url, encoding="utf-8-sig")
        return df.fillna("")
    except Exception:
        return pd.DataFrame()


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
                f"👤 {row['proposer']}" + (f" ({row['party']})" if row.get('party') else "")
            )
            st.write(row["summary"] or "요약 없음")
            tags = list(row["affected_occ"]) + list(row["affected_age"]) + list(row["affected_social"])
            if tags:
                st.markdown(" ".join(f"`{t}`" for t in tags if t))
            # 혜택/불이익 집단
            benefited = [g for g in row.get("benefited_groups", []) if g]
            harmed = [g for g in row.get("harmed_groups", []) if g]
            if benefited:
                st.markdown(" ".join(f"<span style='background:#d1fae5;color:#065f46;padding:1px 7px;border-radius:3px;font-size:0.8em'>✅ {g}</span>" for g in benefited), unsafe_allow_html=True)
            if harmed:
                st.markdown(" ".join(f"<span style='background:#fee2e2;color:#991b1b;padding:1px 7px;border-radius:3px;font-size:0.8em'>⚠️ {g}</span>" for g in harmed), unsafe_allow_html=True)
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


# 시도 좌표 (selectbox 폴백용)
SIDO_COORDS = {
    "서울": (37.5665, 126.9780), "부산": (35.1796, 129.0756),
    "대구": (35.8714, 128.6014), "인천": (37.4563, 126.7052),
    "광주": (35.1595, 126.8526), "대전": (36.3504, 127.3845),
    "울산": (35.5384, 129.3114), "세종": (36.4800, 127.2890),
    "경기": (37.4138, 127.5183), "강원": (37.8228, 128.1555),
    "충북": (36.8000, 127.7000), "충남": (36.5184, 126.8000),
    "전북": (35.7175, 127.1530), "전남": (34.8161, 126.4630),
    "경북": (36.4919, 128.8889), "경남": (35.4606, 128.2132),
    "제주": (33.4996, 126.5312),
}

# GeoJSON 시도 전체명 -> 단축명
SIDO_FULL_TO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
    "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원도": "강원", "강원특별자치도": "강원",
    "충청북도": "충북", "충청남도": "충남",
    "전라북도": "전북", "전북특별자치도": "전북",
    "전라남도": "전남", "경상북도": "경북",
    "경상남도": "경남", "제주특별자치도": "제주",
}

# 시도별 행정구역 코드 (GeoJSON SIG_CD 앞 2자리 기준)
SIDO_CODE = {
    "서울": "11", "부산": "26", "대구": "27", "인천": "28",
    "광주": "29", "대전": "30", "울산": "31", "세종": "36",
    "경기": "41", "강원": "42", "충북": "43", "충남": "44",
    "전북": "45", "전남": "46", "경북": "47", "경남": "48", "제주": "50",
}

PARTY_COLORS = {
    "더불어민주당": "#1C5FA5",
    "국민의힘": "#E61E2B",
    "조국혁신당": "#004EA2",
    "개혁신당": "#FF7210",
    "진보당": "#D6001C",
    "기본소득당": "#00C73C",
    "사회민주당": "#EC008C",
    "무소속": "#888888",
}


def parse_sido(orig_nm: str) -> str:
    if not orig_nm or orig_nm == "비례대표":
        return "비례대표"
    return orig_nm.split()[0]


def parse_gungu(orig_nm: str) -> str:
    """'서울 강남구갑' -> '강남구'"""
    import re
    if not orig_nm or orig_nm == "비례대표":
        return ""
    parts = orig_nm.split()
    if len(parts) < 2:
        return ""
    return re.sub(r"[갑을병정]$", "", parts[1])


@st.cache_data(ttl=86400)
def load_korea_geojson():
    """한국 시도/시군구 GeoJSON 로드 (southkorea-maps 2018)"""
    base = (
        "https://raw.githubusercontent.com/southkorea/"
        "southkorea-maps/master/kostat/2018/json"
    )
    try:
        prov = requests.get(
            f"{base}/skorea-provinces-2018-geo.json", timeout=15
        ).json()
        muni = requests.get(
            f"{base}/skorea-municipalities-2018-geo.json", timeout=15
        ).json()
        return prov, muni
    except Exception:
        return None, None


def render_member_card(m: pd.Series, on_click_key: str = None):
    party_color = PARTY_COLORS.get(m.get("party", ""), "#888888")
    with st.container(border=True):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(
                f"**{m['name']}** "
                f"<span style='background:{party_color};color:white;padding:2px 8px;"
                f"border-radius:4px;font-size:0.8em'>{m.get('party','')}</span>",
                unsafe_allow_html=True,
            )
            district = m.get("orig_nm", "")
            cmit = m.get("cmit_nm", "")
            info_parts = [p for p in [district, cmit] if p]
            if info_parts:
                st.caption(" | ".join(info_parts))
            if m.get("homepage"):
                st.markdown(f"[홈페이지]({m['homepage']})")
        with col2:
            if on_click_key:
                return st.button("법안 보기", key=on_click_key, use_container_width=True)
    return False


def _get_geo_name_key(features: list) -> str:
    if not features:
        return "name"
    props = features[0]["properties"]
    for k in ("CTP_KOR_NM", "SIG_KOR_NM", "name", "NAME"):
        if k in props:
            return k
    return list(props.keys())[0]


def _match_gungu_to_geo(gungu: str, geo_names: list) -> str:
    if not gungu:
        return ""
    if gungu in geo_names:
        return gungu
    for gn in geo_names:
        if len(gn) >= 2 and gungu.endswith(gn):
            return gn
    return ""


def _render_member_bills(name: str, df: pd.DataFrame, members_df: pd.DataFrame):
    """선택된 의원의 법안 뷰 (지도 UI를 완전히 대체)"""
    col_title, col_back = st.columns([5, 1])
    col_title.subheader(f"📋 {name} 의원 발의/참여 법안")
    if col_back.button("← 목록으로", key="back_btn"):
        st.session_state["selected_proposer_member"] = None
        st.rerun()

    if not members_df.empty:
        m_info = members_df[members_df["name"] == name]
        if not m_info.empty:
            m = m_info.iloc[0]
            party_color = PARTY_COLORS.get(m.get("party", ""), "#888888")
            st.markdown(
                f"<span style='background:{party_color};color:white;padding:3px 10px;"
                f"border-radius:4px'>{m.get('party','')}</span> &nbsp;"
                f"**{m.get('orig_nm','')}** &nbsp;|&nbsp; {m.get('cmit_nm','')}",
                unsafe_allow_html=True,
            )

    member_bills = df[df["proposer"].str.contains(name, na=False, regex=False)]
    if member_bills.empty:
        st.info("해당 의원의 법안이 없습니다.")
        return

    c1, c2 = st.columns(2)
    c1.metric("총 법안 수", f"{len(member_bills)}건")
    c2.metric(
        "처리 완료",
        f"{member_bills['status'].isin(['가결','부결','대안반영폐기','철회']).sum()}건",
    )
    sort_opt = st.selectbox("정렬", ["최신순", "처리상태순"], key="member_sort")
    member_bills = member_bills.sort_values(
        "propose_date", ascending=(sort_opt != "최신순")
    )
    for _, row in member_bills.head(30).iterrows():
        render_bill_card(row)


def page_member_bills():
    import plotly.graph_objects as go

    df = load_bills()
    members_df = load_members()
    sidebar_meta(df)

    st.title("🗺️ 의원별 발의 법안")

    # ── 의원 선택됨: 법안 뷰로 전환 ─────────────────────────
    selected_proposer = st.session_state.get("selected_proposer_member")
    if selected_proposer:
        _render_member_bills(selected_proposer, df, members_df)
        return

    tab_map, tab_name = st.tabs(["🗺️ 지역구 지도로 찾기", "🔎 이름으로 바로 찾기"])

    with tab_map:
        if members_df.empty:
            st.warning("의원 데이터를 불러올 수 없습니다.")
            return

        members_df = members_df.copy()
        members_df["sido"] = members_df["orig_nm"].apply(parse_sido)
        members_df["gungu"] = members_df["orig_nm"].apply(parse_gungu)

        map_sido = st.session_state.get("map_sido")
        map_gungu = st.session_state.get("map_gungu")  # 필터 용도 (navigation 아님)

        # 뒤로가기
        if map_sido:
            if st.button("◀ 전국 지도로"):
                st.session_state.pop("map_sido", None)
                st.session_state.pop("map_gungu", None)
                st.rerun()

        # ── 레벨 1: 시도 choropleth ─────────────────────────────
        if not map_sido:
            prov_geo, _ = load_korea_geojson()
            map_col, ctrl_col = st.columns([3, 1])

            with ctrl_col:
                st.markdown("**시도 선택**")
                with st.container(height=500):
                    for sido in sorted(SIDO_COORDS.keys()):
                        cnt = members_df[members_df["sido"] == sido].shape[0]
                        if st.button(
                            f"{sido}  {cnt}명",
                            key=f"sido_btn_{sido}",
                            use_container_width=True,
                        ):
                            st.session_state["map_sido"] = sido
                            st.session_state.pop("map_gungu", None)
                            st.rerun()
                    if st.button("비례대표", key="sido_btn_pr", use_container_width=True):
                        st.session_state["map_sido"] = "비례대표"
                        st.session_state.pop("map_gungu", None)
                        st.rerun()

            with map_col:
                if prov_geo:
                    name_key = _get_geo_name_key(prov_geo["features"])
                    full_names = [
                        f["properties"].get(name_key, "") for f in prov_geo["features"]
                    ]
                    short_names = [SIDO_FULL_TO_SHORT.get(n, n) for n in full_names]
                    hover_texts = [
                        f"{s}<br>{members_df[members_df['sido']==s].shape[0]}명"
                        for s in short_names
                    ]
                    fig = go.Figure(
                        go.Choropleth(
                            geojson=prov_geo,
                            locations=full_names,
                            featureidkey=f"properties.{name_key}",
                            z=[1] * len(full_names),
                            colorscale=[[0, "#93C5FD"], [1, "#93C5FD"]],
                            showscale=False,
                            marker_line_color="white",
                            marker_line_width=1.5,
                            text=hover_texts,
                            hovertemplate="%{text}<extra></extra>",
                        )
                    )
                    fig.update_geos(fitbounds="locations", visible=False)
                    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=500)
                    st.caption("💡 지도를 클릭하거나 우측 목록에서 선택하세요")
                    event = st.plotly_chart(
                        fig, on_select="rerun", key="sido_choro", use_container_width=True
                    )
                    if event and hasattr(event, "selection") and event.selection.points:
                        clicked_full = event.selection.points[0].get("location", "")
                        clicked_short = SIDO_FULL_TO_SHORT.get(clicked_full, clicked_full)
                        if clicked_short:
                            st.session_state["map_sido"] = clicked_short
                            st.session_state.pop("map_gungu", None)
                            st.rerun()
                else:
                    st.warning("지도 데이터를 불러오지 못했습니다.")

        # ── 레벨 2: 시도 의원 목록 + 시군구 필터 ─────────────────
        else:
            sido_members = members_df[members_df["sido"] == map_sido]

            # 시군구 필터 적용
            if map_gungu:
                display_members = sido_members[
                    sido_members["gungu"].str.contains(map_gungu, na=False, regex=False)
                    | sido_members["orig_nm"].str.contains(map_gungu, na=False, regex=False)
                ]
            else:
                display_members = sido_members

            map_col, ctrl_col = st.columns([3, 1])

            with ctrl_col:
                st.markdown("**시군구 필터**")
                with st.container(height=520):
                    # 전체 버튼
                    all_label = f"{'▶ ' if not map_gungu else ''}전체  {len(sido_members)}명"
                    if st.button(all_label, key="gu_all", use_container_width=True):
                        st.session_state.pop("map_gungu", None)
                        st.rerun()

                    gu_list = sorted([g for g in sido_members["gungu"].unique() if g])
                    for gu in gu_list:
                        cnt = sido_members[
                            sido_members["gungu"].str.contains(gu, na=False, regex=False)
                        ].shape[0]
                        label = f"{'▶ ' if map_gungu == gu else ''}{gu}  {cnt}명"
                        if st.button(label, key=f"gu_btn_{gu}", use_container_width=True):
                            if map_gungu == gu:
                                st.session_state.pop("map_gungu", None)
                            else:
                                st.session_state["map_gungu"] = gu
                            st.rerun()

            with map_col:
                header = f"**{map_sido}{'  ·  ' + map_gungu if map_gungu else '  전체'}  —  {len(display_members)}명**"
                st.markdown(header)
                with st.container(height=520):
                    for i, (_, m) in enumerate(display_members.reset_index(drop=True).iterrows()):
                        party_color = PARTY_COLORS.get(m.get("party", ""), "#888888")
                        c_info, c_btn = st.columns([5, 1])
                        with c_info:
                            st.markdown(
                                f"**{m['name']}** "
                                f"<span style='background:{party_color};color:white;"
                                f"padding:1px 6px;border-radius:3px;font-size:0.75em'>"
                                f"{m.get('party','')}</span>"
                                f"<br><small style='color:#666'>{m.get('orig_nm','')} "
                                f"| {m.get('cmit_nm','')}</small>",
                                unsafe_allow_html=True,
                            )
                        with c_btn:
                            if st.button("법안", key=f"mc_{map_sido}_{i}", use_container_width=True):
                                st.session_state["selected_proposer_member"] = m["name"]
                                st.rerun()

    # ── 이름 검색 탭 ─────────────────────────────────────────
    with tab_name:
        if not members_df.empty:
            name_list = sorted(members_df["name"].dropna().unique().tolist())
        else:
            name_list = sorted(df["proposer"].dropna().unique().tolist())

        name_query = st.text_input(
            "의원 이름 검색", placeholder="예: 홍길동", key="name_search"
        )
        if name_query:
            matched = [n for n in name_list if name_query in n]
            if not matched:
                st.warning(f"'{name_query}' 의원을 찾을 수 없습니다.")
            else:
                for name in matched:
                    if st.button(f"{name} 법안 보기", key=f"name_btn_{name}"):
                        st.session_state["selected_proposer_member"] = name
                        st.rerun()
        else:
            sel = st.selectbox(
                "또는 목록에서 선택", ["선택하세요"] + name_list, key="name_full"
            )
            if sel != "선택하세요":
                if st.button(f"{sel} 법안 보기", key="name_full_btn"):
                    st.session_state["selected_proposer_member"] = sel
                    st.rerun()


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
    import re
    members_df = load_members()
    name_to_party = (
        dict(zip(members_df["name"], members_df["party"]))
        if not members_df.empty else {}
    )
    def _resolve_party(proposer: str) -> str:
        if not proposer:
            return "기타"
        # "김희정의원 등 10인" -> "김희정"
        s = re.sub(r"의원.*", "", str(proposer))
        m = re.match(r"([가-힣]{2,4})", s)
        name = m.group(1) if m else ""
        return name_to_party.get(name, "기타")
    party_series = df["proposer"].apply(_resolve_party)
    party_cnt = party_series.value_counts().head(10).reset_index()
    party_cnt.columns = ["정당", "건수"]
    party_cnt = party_cnt[party_cnt["정당"] != "기타"]
    if not party_cnt.empty:
        party_colors = {k: v for k, v in PARTY_COLORS.items() if k in party_cnt["정당"].values}
        fig4 = px.bar(
            party_cnt, x="정당", y="건수",
            color="정당", color_discrete_map=party_colors,
        )
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("정당 정보를 불러올 수 없습니다.")


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
        | 모델 | Google Gemma 4 (27B) |
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
