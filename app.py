import streamlit as st
import time
import io
from PIL import Image
from typing import Optional

from config import APP_NAMES, CATEGORIES
from db import DatabaseManager
from pruning import recursive_prune

st.set_page_config(
    page_title="Smart Hashtag Generator V2.0",
    page_icon="#",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ===================== SESSION STATE =====================
def init_state():
    defaults = {
        "app_name": None,
        "uploaded_image": None,
        "image_bytes": None,
        "analysis_done": False,
        "exact_matches": [],
        "proposed_objects": [],
        "proposed_styles": [],
        "proposed_colors": [],
        "result_text": "",
        "added_proposals": set(),
        "parent_map": {},
        "db_connected": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def get_db() -> Optional[DatabaseManager]:
    if "db" not in st.session_state:
        db = DatabaseManager()
        st.session_state.db_connected = db.connect()
        st.session_state.db = db
    return st.session_state.db


# ===================== DATA LOADING =====================
def load_tags_for_app(app_name: str):
    db = get_db()
    if db and st.session_state.db_connected:
        tags = db.get_all_tags(app_name)
        st.session_state.parent_map = db.get_parent_map(app_name)
        return tags
    return []


# ===================== AI ANALYSIS =====================
def call_ai_vision(image_bytes: bytes, app_name: str):
    from ai_engine import AIVisionEngine

    db = get_db()
    if db and st.session_state.db_connected:
        tags = db.get_tag_list(app_name)
        existing_str = ", ".join(tags)
        st.session_state.parent_map = db.get_parent_map(app_name)
    else:
        existing_str = ""
        st.session_state.parent_map = {}

    engine = AIVisionEngine()
    result = engine.analyze_image(image_bytes, existing_str)

    if result is None:
        return None

    exact = result.get("exact_matches", [])
    if st.session_state.parent_map:
        exact = recursive_prune(exact, st.session_state.parent_map)

    return {
        "exact_matches": exact,
        "proposed_objects": result.get("proposed_objects", []),
        "proposed_styles": result.get("proposed_styles", []),
        "proposed_colors": result.get("proposed_colors", []),
    }


# ===================== DATABASE OPERATIONS =====================
def insert_proposal(hashtag: str, category: str, app_name: str) -> bool:
    db = get_db()
    if db and st.session_state.db_connected:
        ok, msg = db.insert_new_tag(hashtag, category, app_name)
        return ok
    return True


# ===================== UI COMPONENTS =====================
CUSTOM_CSS = """
<style>
    .main-header { font-size: 2rem; font-weight: 700; color: #1F4E79; margin-bottom: 0; }
    .sub-header { font-size: 0.9rem; color: #808080; margin-top: -0.5rem; }
    .stButton > button { border-radius: 6px; transition: all 0.2s; }
    .card-box {
        border: 1px solid #E0E0E0; border-radius: 12px; padding: 1.2rem;
        margin-bottom: 0.8rem; background: #FAFBFC;
    }
    .proposal-item { font-family: 'Courier New', monospace; font-size: 0.85rem;
        background: #F0F0F0; padding: 4px 10px; border-radius: 4px; display: inline-block; }
    div[data-testid="stToast"] > div { font-size: 0.9rem; }
</style>
"""


def render_sidebar():
    with st.sidebar:
        st.markdown("### Cau hinh")
        db = get_db()
        if st.session_state.db_connected:
            st.success("Supabase: Connected")
        else:
            st.warning("Supabase: Not connected (local mode)")

        st.divider()
        st.markdown("**Dev Info**")
        st.caption("Smart Hashtag Generator V2.0")
        st.caption("Powered by OpenCode.ai Vision")
        st.caption("SiinJiuYunShan")


def render_left_panel():
    st.markdown("### Input & Controls")

    prev_app = st.session_state.app_name
    app_choice = st.selectbox(
        "Chon Nen Tang (App)",
        options=["-- Select App --"] + APP_NAMES,
        key="app_selector"
    )

    if app_choice == "-- Select App --":
        st.session_state.app_name = None
    else:
        st.session_state.app_name = app_choice
        if app_choice != prev_app:
            st.session_state.analysis_done = False
            st.session_state.added_proposals = set()

    app_name = st.session_state.app_name

    uploaded = st.file_uploader(
        "Tai anh len (jpg, png, webp)",
        type=["jpg", "jpeg", "png", "webp"],
        disabled=(app_name is None),
        key="file_uploader"
    )

    if uploaded is not None:
        image = Image.open(uploaded)
        st.session_state.uploaded_image = image
        buf = io.BytesIO()
        fmt = image.format or "PNG"
        image.save(buf, format=fmt)
        st.session_state.image_bytes = buf.getvalue()
        st.image(image, caption="Preview", use_container_width=True)
    else:
        st.session_state.uploaded_image = None
        st.session_state.image_bytes = None

    can_run = app_name is not None and st.session_state.image_bytes is not None

    if st.button("Phan Tich Hashtag", type="primary", disabled=not can_run,
                 use_container_width=True, key="analyze_btn"):
        with st.spinner("AI dang phan tich anh..."):
            st.session_state.added_proposals = set()
            st.session_state.analysis_done = False
            result = call_ai_vision(st.session_state.image_bytes, app_name)
            if result:
                st.session_state.exact_matches = result["exact_matches"]
                st.session_state.proposed_objects = result["proposed_objects"]
                st.session_state.proposed_styles = result["proposed_styles"]
                st.session_state.proposed_colors = result["proposed_colors"]
                st.session_state.result_text = (
                    ", ".join(result["exact_matches"])
                    if result["exact_matches"]
                    else "(No matches found)"
                )
                st.session_state.analysis_done = True
            else:
                st.error("AI analysis failed. Please try again.")
            st.rerun()

    # Stats
    if app_name:
        if st.session_state.db_connected:
            tags = load_tags_for_app(app_name)
            st.caption(f"DB: {len(tags)} hashtags loaded for {app_name}")
        else:
            st.caption("DB: Local mode")

        with st.expander("DB Stats"):
            if st.session_state.db_connected:
                try:
                    tags = load_tags_for_app(app_name)
                    cats = {"object": 0, "style": 0, "color": 0}
                    for t in tags:
                        c = t.get("category", "")
                        if c in cats:
                            cats[c] += 1
                    st.metric("Object", cats["object"])
                    st.metric("Style", cats["style"])
                    st.metric("Color", cats["color"])
                except Exception:
                    st.caption("Cannot load stats")


# ===================== RIGHT PANEL (FRAGMENT) =====================
@st.fragment
def render_right_panel():
    """Fragment: results + proposals. Only this re-runs on [+] click."""

    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown("### Ket qua Hashtag")
    with c2:
        if st.session_state.analysis_done and st.session_state.result_text:
            if st.button("Copy All", use_container_width=True, key="copy_btn"):
                st.toast("Copy text ben duoi de sao chep!", icon="📋")

    if st.session_state.analysis_done:
        rt = st.session_state.result_text
        st.text_area(
            "Hashtags",
            value=rt,
            height=120,
            key="result_text_area",
            label_visibility="collapsed",
        )
        if rt and rt != "(No matches found)":
            count = len([h for h in rt.split(", ") if h.strip()])
            st.caption(f"Tim thay {count} hashtag (da qua thuat toan cat tia)")
    else:
        st.info("Chon App, tai anh len, roi nhan [Phan Tich Hashtag] de bat dau.")

    # ---- PROPOSALS ----
    if not st.session_state.analysis_done:
        return

    obj = st.session_state.proposed_objects
    sty = st.session_state.proposed_styles
    clr = st.session_state.proposed_colors

    if not obj and not sty and not clr:
        return

    st.markdown("---")
    st.markdown("### AI De Xuat (Smart Proposals)")

    col_obj, col_sty, col_clr = st.columns(3)

    def proposal_block(col, title, items, category, emoji):
        with col:
            st.markdown(f"**{emoji} {title}**  ({len(items)})")
            if not items:
                st.caption("-- Khong co --")
                return
            for item in items:
                added = item in st.session_state.added_proposals
                b1, b2 = st.columns([5, 1])
                with b1:
                    st.markdown(f'<span class="proposal-item">{item}</span>',
                                unsafe_allow_html=True)
                with b2:
                    if added:
                        st.button("✓", key=f"done_{item}_{category}",
                                  disabled=True, use_container_width=True)
                    else:
                        if st.button("+", key=f"add_{item}_{category}",
                                     use_container_width=True, type="primary"):
                            insert_proposal(item, category, st.session_state.app_name)
                            st.session_state.added_proposals.add(item)
                            current = st.session_state.result_text
                            if current == "(No matches found)":
                                st.session_state.result_text = item
                            else:
                                st.session_state.result_text = (
                                    current + ", " + item if current else item
                                )
                            st.toast(
                                f"Da them [{item}] vao Data cua App [{st.session_state.app_name}]",
                                icon="✅"
                            )
                            st.rerun(scope="fragment")

    proposal_block(col_obj, "Object Moi", obj, "object", "📦")
    proposal_block(col_sty, "Style Moi", sty, "style", "🎨")
    proposal_block(col_clr, "Color Moi", clr, "color", "🌈")


# ===================== MAIN =====================
def main():
    init_state()
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    render_sidebar()

    st.markdown('<p class="main-header"># Smart Hashtag Generator V2.0</p>',
                unsafe_allow_html=True)
    st.markdown('<p class="sub-header">AI Vision + Supabase | SiinJiuYunShan</p>',
                unsafe_allow_html=True)
    st.divider()

    left, right = st.columns([3, 7])

    with left:
        render_left_panel()

    with right:
        render_right_panel()


if __name__ == "__main__":
    main()
