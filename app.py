import streamlit as st
import io
import time
import base64
from PIL import Image
from typing import List, Dict, Optional

from config import APP_NAMES, APP_TO_COLUMN
from db import DatabaseManager
from pruning import recursive_prune

st.set_page_config(
    page_title="Smart Hashtag Generator V2.0",
    page_icon="#",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ===================== SESSION STATE =====================
INIT_STATE = {
    "app_name": None,
    "batch_mode": False,
    "images_data": [],          # list of {name, bytes, result}
    "analysis_done": False,
    "exact_matches": [],
    "proposed_objects": [],
    "proposed_styles": [],
    "proposed_colors": [],
    "result_text": "",
    "added_proposals": set(),
    "parent_map": {},
    "db_connected": False,
    "is_mock_ai": True,
    "batch_results": [],        # [{filename, matches, objects, styles, colors}]
}

for k, v in INIT_STATE.items():
    if k not in st.session_state:
        st.session_state[k] = v


def get_db() -> Optional[DatabaseManager]:
    if "db" not in st.session_state:
        db = DatabaseManager()
        st.session_state.db_connected = db.connect()
        st.session_state.db = db
    return st.session_state.db


def load_tags_for_app(app_name: str):
    db = get_db()
    if db and st.session_state.db_connected:
        tags = db.get_all_tags(app_name)
        st.session_state.parent_map = db.get_parent_map(app_name)
        return tags
    st.session_state.parent_map = {}
    return []


def run_single_analysis(image_bytes: bytes, app_name: str):
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

    if not engine.api_key or not engine.api_url:
        st.session_state.is_mock_ai = True
    else:
        st.session_state.is_mock_ai = False

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


def insert_proposal(hashtag: str, category: str, app_name: str) -> bool:
    db = get_db()
    if db and st.session_state.db_connected:
        ok, _ = db.insert_new_tag(hashtag, category, app_name)
        return ok
    return True


# ===================== UI: SIDEBAR =====================
def render_sidebar():
    with st.sidebar:
        st.markdown("### Cau hinh")
        db = get_db()

        col_a, col_b = st.columns([3, 2])
        with col_a:
            if st.session_state.db_connected:
                st.success("Supabase: OK")
            else:
                st.warning("Supabase: Offline")
        with col_b:
            if st.button("Test DB", key="test_db_btn"):
                if st.session_state.db_connected:
                    try:
                        tags = db.get_all_tags("W1")
                        st.toast(f"DB OK: {len(tags)} tags for W1", icon="✅")
                    except Exception as e:
                        st.toast(f"DB Err: {e}", icon="❌")
                else:
                    st.toast("Chua cau hinh SUPABASE_URL/KEY", icon="⚠️")

        if st.session_state.is_mock_ai:
            st.info("AI: Mock mode (chua co key)")
        else:
            st.success("AI: Live")

        st.divider()
        st.caption("Smart Hashtag Generator V2.0")
        st.caption("SiinJiuYunShan")


# ===================== UI: LEFT PANEL =====================
def render_left_panel():
    st.markdown("### Input & Controls")

    # --- Mode toggle ---
    mode = st.radio(
        "Che do xu ly",
        options=["Single Image", "Batch Folder"],
        horizontal=True,
        key="mode_radio"
    )
    st.session_state.batch_mode = (mode == "Batch Folder")

    # --- App selector ---
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
            st.session_state.batch_results = []

    app_name = st.session_state.app_name

    if st.session_state.batch_mode:
        render_batch_upload(app_name)
    else:
        render_single_upload(app_name)

    # --- DB Stats ---
    if app_name and st.session_state.db_connected:
        with st.expander("DB Stats"):
            tags = load_tags_for_app(app_name)
            cats = {"object": 0, "style": 0, "color": 0}
            for t in tags:
                c = t.get("category", "")
                if c in cats:
                    cats[c] += 1
            c1, c2, c3 = st.columns(3)
            c1.metric("Object", cats["object"])
            c2.metric("Style", cats["style"])
            c3.metric("Color", cats["color"])
            st.caption(f"Total: {len(tags)} tags for {app_name}")


def render_single_upload(app_name):
    uploaded = st.file_uploader(
        "Tai anh len (jpg, png, webp)",
        type=["jpg", "jpeg", "png", "webp"],
        disabled=(app_name is None),
        key="single_uploader"
    )

    if uploaded is not None:
        image = Image.open(uploaded)
        buf = io.BytesIO()
        fmt = image.format or "PNG"
        image.save(buf, format=fmt)
        st.session_state.images_data = [{
            "name": uploaded.name,
            "bytes": buf.getvalue(),
            "image": image
        }]
        st.image(image, caption=uploaded.name, use_container_width=True)
    else:
        st.session_state.images_data = []

    can_run = app_name is not None and len(st.session_state.images_data) > 0

    if st.button("Phan Tich Hashtag", type="primary", disabled=not can_run,
                 use_container_width=True, key="analyze_single_btn"):
        with st.spinner(f"AI dang phan tich anh... (Mock: {st.session_state.is_mock_ai})"):
            st.session_state.added_proposals = set()
            st.session_state.analysis_done = False
            result = run_single_analysis(st.session_state.images_data[0]["bytes"], app_name)
            if result:
                st.session_state.exact_matches = result["exact_matches"]
                st.session_state.proposed_objects = result["proposed_objects"]
                st.session_state.proposed_styles = result["proposed_styles"]
                st.session_state.proposed_colors = result["proposed_colors"]
                st.session_state.result_text = (
                    ", ".join(result["exact_matches"])
                    if result["exact_matches"]
                    else "(No exact matches - check proposals below)"
                )
                st.session_state.analysis_done = True
            else:
                st.error("AI analysis failed.")
            st.rerun()


def render_batch_upload(app_name):
    uploaded_files = st.file_uploader(
        "Tai nhieu anh (jpg, png, webp)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        disabled=(app_name is None),
        key="batch_uploader"
    )

    can_run = False
    if uploaded_files:
        st.session_state.images_data = []
        for uf in uploaded_files:
            image = Image.open(uf)
            buf = io.BytesIO()
            fmt = image.format or "PNG"
            image.save(buf, format=fmt)
            st.session_state.images_data.append({
                "name": uf.name,
                "bytes": buf.getvalue(),
                "image": image
            })
        st.caption(f"Da chon {len(uploaded_files)} anh")
        can_run = app_name is not None and len(uploaded_files) > 0

        with st.expander("Preview anh"):
            cols = st.columns(3)
            for i, img_data in enumerate(st.session_state.images_data):
                with cols[i % 3]:
                    st.image(img_data["image"], caption=img_data["name"], use_container_width=True)
    else:
        st.session_state.images_data = []

    if st.button("Phan Tich TAT CA Anh (Batch)", type="primary", disabled=not can_run,
                 use_container_width=True, key="analyze_batch_btn"):
        st.session_state.batch_results = []
        st.session_state.analysis_done = False
        progress_bar = st.progress(0)
        status_text = st.empty()

        total = len(st.session_state.images_data)
        for i, img_data in enumerate(st.session_state.images_data):
            status_text.text(f"Dang xu ly {i+1}/{total}: {img_data['name']}...")
            result = run_single_analysis(img_data["bytes"], app_name)
            if result:
                st.session_state.batch_results.append({
                    "filename": img_data["name"],
                    "matches": result["exact_matches"],
                    "objects": result["proposed_objects"],
                    "styles": result["proposed_styles"],
                    "colors": result["proposed_colors"],
                })
            else:
                st.session_state.batch_results.append({
                    "filename": img_data["name"],
                    "matches": [],
                    "objects": [],
                    "styles": [],
                    "colors": [],
                    "error": True
                })
            progress_bar.progress((i + 1) / total)

        status_text.text(f"Hoan thanh! Da xu ly {total} anh.")
        st.session_state.analysis_done = True
        st.rerun()


# ===================== UI: RIGHT PANEL =====================
@st.fragment
def render_right_panel():
    if st.session_state.batch_mode and st.session_state.batch_results:
        render_batch_results()
    else:
        render_single_results()


def render_single_results():
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown("### Ket qua Hashtag")
    with c2:
        if st.session_state.analysis_done and st.session_state.result_text:
            if st.button("Copy All", use_container_width=True, key="copy_btn"):
                st.toast("Copy text ben duoi de sao chep!", icon="📋")

    if not st.session_state.analysis_done:
        st.info("Chon App, tai anh, roi nhan [Phan Tich Hashtag] de bat dau.")
        if st.session_state.is_mock_ai:
            st.caption("⚠️ Dang chay o Mock Mode. Them AI_API_KEY vao secrets de phan tich anh thuc te.")
        return

    # Mock mode banner
    if st.session_state.is_mock_ai:
        st.warning("MOCK MODE: Ket qua la du lieu mau. Them AI_API_KEY de phan tich thuc te.")

    # Result text area
    rt = st.session_state.result_text
    st.text_area(
        "Hashtags", value=rt, height=120,
        key="result_text_area", label_visibility="collapsed"
    )
    if rt and rt != "(No exact matches - check proposals below)":
        count = len([h for h in rt.split(", ") if h.strip()])
        st.caption(f"Tim thay {count} hashtag (da qua thuat toan cat tia)")

    # Proposals
    obj = st.session_state.proposed_objects
    sty = st.session_state.proposed_styles
    clr = st.session_state.proposed_colors

    if not obj and not sty and not clr:
        if st.session_state.analysis_done:
            st.caption("AI khong co de xuat moi.")
        return

    st.markdown("---")
    st.markdown("### AI De Xuat (Smart Proposals)")
    st.caption("Click [+] de them hashtag vao Database va Text Area")

    col_obj, col_sty, col_clr = st.columns(3)

    def proposal_block(col, title, items, category, emoji):
        with col:
            st.markdown(f"**{emoji} {title}** ({len(items)})")
            if not items:
                st.caption("-- Khong co --")
                return
            for item in items:
                added = item in st.session_state.added_proposals
                b1, b2 = st.columns([5, 1])
                with b1:
                    st.code(item, language=None)
                with b2:
                    if added:
                        st.button("✓", key=f"done_{item}_{category}",
                                  disabled=True, use_container_width=True)
                    else:
                        if st.button("+", key=f"add_{item}_{category}",
                                     use_container_width=True, type="primary"):
                            insert_proposal(item, category, st.session_state.app_name)
                            st.session_state.added_proposals.add(item)
                            cur = st.session_state.result_text
                            if "(No exact matches" in cur:
                                st.session_state.result_text = item
                            else:
                                st.session_state.result_text = (
                                    cur + ", " + item if cur else item
                                )
                            st.toast(
                                f"Da them [{item}] vao App [{st.session_state.app_name}]",
                                icon="✅"
                            )
                            st.rerun(scope="fragment")

    proposal_block(col_obj, "Object Moi", obj, "object", "📦")
    proposal_block(col_sty, "Style Moi", sty, "style", "🎨")
    proposal_block(col_clr, "Color Moi", clr, "color", "🌈")


def render_batch_results():
    st.markdown("### Ket qua Batch")

    results = st.session_state.batch_results
    total_matches = sum(len(r["matches"]) for r in results)
    total_objects = sum(len(r["objects"]) for r in results)
    total_styles = sum(len(r["styles"]) for r in results)
    total_colors = sum(len(r["colors"]) for r in results)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Anh da xu ly", len(results))
    c2.metric("Matches", total_matches)
    c3.metric("Object de xuat", total_objects)
    c4.metric("Style de xuat", total_styles)

    # Download button
    csv_lines = ["filename,matches,proposed_objects,proposed_styles,proposed_colors"]
    for r in results:
        csv_lines.append(
            f'"{r["filename"]}","{",".join(r["matches"])}","{",".join(r["objects"])}","{",".join(r["styles"])}","{",".join(r["colors"])}"'
        )
    csv_data = "\n".join(csv_lines)
    b64 = base64.b64encode(csv_data.encode("utf-8")).decode()
    st.download_button(
        "Tai xuong CSV", data=csv_data,
        file_name="batch_hashtag_results.csv",
        mime="text/csv", use_container_width=True
    )

    st.divider()

    # Per-image results
    for i, r in enumerate(results):
        with st.expander(f"📷 {r['filename']} ({len(r['matches'])} matches, {len(r['objects'])} objects, {len(r['styles'])} styles, {len(r['colors'])} colors)"):
            if r.get("error"):
                st.error("Failed to analyze this image")
            else:
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("**Matches:**")
                    st.code(", ".join(r["matches"]) if r["matches"] else "(none)")
                    st.markdown("**Proposed Objects:**")
                    st.code(", ".join(r["objects"]) if r["objects"] else "(none)")
                with col_b:
                    st.markdown("**Proposed Styles:**")
                    st.code(", ".join(r["styles"]) if r["styles"] else "(none)")
                    st.markdown("**Proposed Colors:**")
                    st.code(", ".join(r["colors"]) if r["colors"] else "(none)")

                # Combine all for this image
                all_tags = r["matches"] + r["objects"] + r["styles"] + r["colors"]
                tag_text = ", ".join(all_tags)
                st.text_area(f"Copy tags for {r['filename']}", value=tag_text,
                             key=f"batch_copy_{i}", height=70, label_visibility="collapsed")


# ===================== CSS =====================
CUSTOM_CSS = """
<style>
    .main-header { font-size: 2rem; font-weight: 700; color: #1F4E79; margin-bottom: 0; }
    .sub-header { font-size: 0.9rem; color: #808080; margin-top: -0.5rem; }
    .stButton > button { border-radius: 6px; transition: all 0.2s; }
    div[data-testid="stToast"] > div { font-size: 0.9rem; }
</style>
"""


# ===================== MAIN =====================
def main():
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
