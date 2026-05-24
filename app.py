import streamlit as st
import io
import time
import base64
import pandas as pd
from PIL import Image
from typing import List, Dict, Optional

from config import APP_NAMES
from db import DatabaseManager

st.set_page_config(
    page_title="HashTag AI",
    page_icon="#",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ===================== SESSION STATE =====================
def init_state():
    defaults = {
        "app_name": None,
        "batch_mode": True,
        "images": [],
        "results": {},
        "processing": False,
        "db_connected": False,
        "is_mock": True,
        "dropdown_options": {"object_1": [], "object_2": [], "object_3": [], "style": [], "color": []},
        "start_number": 1,
        "ai_error": None,
        "batch_stats": {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ===================== DB HELPERS =====================
def get_db():
    if "db" not in st.session_state:
        db = DatabaseManager()
        st.session_state.db_connected = db.connect()
        st.session_state.db = db
    return st.session_state.db

def load_dropdown_options(app_name: str):
    db = get_db()
    opts = {"object_1": [], "object_2": [], "object_3": [], "style": [], "color": [], "mood": ["none"], "gender": ["none"]}
    if not db or not st.session_state.db_connected:
        return opts

    tags = db.get_all_tags(app_name)
    parent_map = {}
    for t in tags:
        parent_map[t["hashtag"]] = t.get("parent_hashtag") or None

    all_objects = set()
    for t in tags:
        if t.get("category") == "object":
            all_objects.add(t["hashtag"])

    opts["object_1"] = sorted(all_objects)
    opts["object_2"] = sorted(all_objects)
    opts["object_3"] = sorted(all_objects)
    opts["style"] = sorted(set(t["hashtag"] for t in tags if t.get("category") == "style"))
    opts["color"] = sorted(set(t["hashtag"] for t in tags if t.get("category") == "color"))
    st.session_state.dropdown_options = opts
    return opts


# ===================== OBJECT DEDUP LOGIC =====================
def normalize_objects(result: dict) -> dict:
    objects = [
        result.get("object_1", "none"),
        result.get("object_2", "none"),
        result.get("object_3", "none"),
    ]
    seen = set()
    cleaned = []
    for obj in objects:
        obj = obj.strip().lower()
        if obj in ("none", "", "nan"):
            cleaned.append("none")
        elif obj not in seen:
            seen.add(obj)
            cleaned.append(obj)
        else:
            cleaned.append("none")

    result["object_1"] = cleaned[0]
    result["object_2"] = cleaned[1]
    result["object_3"] = cleaned[2]
    return result


# ===================== AI ENGINE =====================
def analyze_image(image_bytes: bytes, app_name: str):
    from ai_engine import AIVisionEngine
    from config import AI_API_KEY, AI_API_URL

    db = get_db()
    existing_tags = ""
    if db and st.session_state.db_connected:
        existing_tags = ", ".join(db.get_tag_list(app_name))

    st.session_state.is_mock = not (AI_API_KEY and AI_API_URL)

    engine = AIVisionEngine()
    result = engine.analyze_image(image_bytes, existing_tags)
    return normalize_objects(result)


# ===================== EXPORT =====================
def export_results(fmt="csv"):
    rows = []
    for img in st.session_state.images:
        r = st.session_state.results.get(img["name"], {})
        rows.append({
            "STT": img.get("stt", ""),
            "Filename": img["name"],
            "Object 1": r.get("object_1", ""),
            "Object 2": r.get("object_2", ""),
            "Object 3": r.get("object_3", ""),
            "Style": r.get("style", ""),
            "Color": r.get("color", ""),
            "Mood": r.get("mood", "none"),
            "Gender": r.get("gender", "none"),
            "Status": r.get("status", "pending"),
        })
    df = pd.DataFrame(rows)
    if fmt == "csv":
        return df.to_csv(index=False).encode("utf-8-sig"), "results.csv", "text/csv"
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue(), "results.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ===================== UI: SIDEBAR =====================
def render_sidebar():
    with st.sidebar:
        st.markdown("### ⚙️ Cấu hình")

        st.selectbox("Chon App", options=["-- Select --"] + APP_NAMES, key="app_sel")
        if st.session_state.app_sel != "-- Select --":
            st.session_state.app_name = st.session_state.app_sel
        else:
            st.session_state.app_name = None

        st.number_input("Bat dau tu so", min_value=1, value=st.session_state.start_number, key="start_num")
        st.session_state.start_number = st.session_state.start_num

        st.divider()
        st.markdown("### 📁 Nguon anh")

        st.session_state.batch_mode = st.toggle("Batch Folder (nhieu anh)", value=True, key="batch_toggle")

        if st.session_state.batch_mode:
            uploaded = st.file_uploader(
                "Tai nhieu anh cung luc", type=["jpg","jpeg","png","webp","gif"],
                accept_multiple_files=True, key="batch_upload"
            )
        else:
            uploaded = st.file_uploader(
                "Tai 1 anh", type=["jpg","jpeg","png","webp","gif"],
                accept_multiple_files=False, key="single_upload"
            )
            uploaded = [uploaded] if uploaded else []

        if uploaded:
            st.session_state.images = []
            for i, uf in enumerate(uploaded):
                img = Image.open(uf)
                buf = io.BytesIO()
                img.save(buf, format=img.format or "PNG")
                st.session_state.images.append({
                    "name": uf.name,
                    "bytes": buf.getvalue(),
                    "size_kb": len(buf.getvalue()) / 1024,
                    "stt": st.session_state.start_number + i,
                })
            st.success(f"Da chon {len(uploaded)} anh")

        if st.button("▶ Chay hashtag", type="primary", use_container_width=True,
                      disabled=not st.session_state.app_name or not st.session_state.images):
            run_batch()

        if st.session_state.results:
            st.divider()
            st.markdown("### 📤 Xuat File")
            fmt = st.radio("Dinh dang", ["CSV", "Excel"], horizontal=True, key="export_fmt")
            data, fname, mime = export_results(fmt.lower())
            st.download_button(f"Tai xuong {fmt}", data, file_name=fname, mime=mime, use_container_width=True)

            if st.session_state.batch_stats:
                with st.expander("Thong ke Batch"):
                    bs = st.session_state.batch_stats
                    st.metric("Anh da xu ly", bs.get("total", 0))
                    st.metric("Co Object", bs.get("has_obj", 0))
                    st.metric("Co Style", bs.get("has_style", 0))
                    st.metric("Co Color", bs.get("has_color", 0))

        st.divider()
        db = get_db()
        if st.session_state.db_connected:
            st.success("Supabase: OK")
        else:
            st.warning("Supabase: Offline")
        if st.session_state.is_mock:
            st.info("AI: Mock mode")
        else:
            st.success("AI: Live")
        if st.session_state.get("ai_error"):
            st.error(f"AI Error: {st.session_state.ai_error}")


# ===================== BATCH PROCESSING =====================
def run_batch():
    app_name = st.session_state.app_name
    load_dropdown_options(app_name)

    st.session_state.processing = True
    st.session_state.results = {}

    progress = st.progress(0)
    status = st.empty()

    stats = {"total": 0, "has_obj": 0, "has_style": 0, "has_color": 0}

    for i, img in enumerate(st.session_state.images):
        status.text(f"Dang xu ly {i+1}/{len(st.session_state.images)}: {img['name']}")
        result = analyze_image(img["bytes"], app_name)
        result["status"] = "done"
        st.session_state.results[img["name"]] = result

        stats["total"] += 1
        if result.get("object_1", "none") != "none":
            stats["has_obj"] += 1
        if result.get("style", "none") != "none":
            stats["has_style"] += 1
        if result.get("color", "none") != "none":
            stats["has_color"] += 1

        progress.progress((i + 1) / len(st.session_state.images))

    st.session_state.batch_stats = stats
    status.text(f"Hoan thanh! {stats['total']} anh, {stats['has_obj']} co Object, {stats['has_style']} co Style, {stats['has_color']} co Color")
    st.session_state.processing = False
    st.rerun()


# ===================== UI: MAIN GRID =====================
def safe_index(options, value):
    try:
        return options.index(value)
    except ValueError:
        return 0


def render_card(img, idx):
    r = st.session_state.results.get(img["name"], {})
    status = r.get("status", "pending")
    opts = st.session_state.dropdown_options

    with st.container():
        st.markdown(f"""
        <div style="border:1px solid #30363d;border-radius:10px;padding:10px;margin-bottom:8px;background:#0d1117;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                <span style="color:#8b949e;font-size:10px;">{img['name'][:22]}</span>
                <span style="color:#58a6ff;font-size:10px;">{img['size_kb']:.1f}KB</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.image(Image.open(io.BytesIO(img["bytes"])), use_container_width=True)

        st.markdown(f"**STT: {img['stt']}** | Qwen3.6 | {'✅ Done' if status == 'done' else '⏳ Pending'}")

        if r.get("_mock"):
            st.caption("⚠️ MOCK MODE")
        if r.get("error"):
            st.error(f"AI Error: {r['error']}")

        if status == "done":
            st.markdown("**🔹 OBJECT**")
            o1_opts = ["none"] + opts["object_1"]
            r["object_1"] = st.selectbox("Object 1", options=o1_opts,
                                          index=safe_index(o1_opts, r.get("object_1","none")),
                                          key=f"o1_{idx}", label_visibility="visible")
            o2_opts = ["none"] + opts["object_2"]
            r["object_2"] = st.selectbox("Object 2", options=o2_opts,
                                          index=safe_index(o2_opts, r.get("object_2","none")),
                                          key=f"o2_{idx}", label_visibility="visible")
            o3_opts = ["none"] + opts["object_3"]
            r["object_3"] = st.selectbox("Object 3", options=o3_opts,
                                          index=safe_index(o3_opts, r.get("object_3","none")),
                                          key=f"o3_{idx}", label_visibility="visible")

            st.markdown("**🎨 STYLE / COLOR / MOOD**")
            s_opts = ["none"] + opts["style"]
            r["style"] = st.selectbox("Style", options=s_opts,
                                       index=safe_index(s_opts, r.get("style","none")),
                                       key=f"sty_{idx}", label_visibility="visible")
            c_opts = ["none"] + opts["color"]
            r["color"] = st.selectbox("Color", options=c_opts,
                                       index=safe_index(c_opts, r.get("color","none")),
                                       key=f"clr_{idx}", label_visibility="visible")
            r["mood"] = st.selectbox("Mood", options=["none"], index=0, key=f"mood_{idx}", label_visibility="visible")
            r["gender"] = st.selectbox("Gender", options=["none"], index=0, key=f"gen_{idx}", label_visibility="visible")

            st.session_state.results[img["name"]] = r

            if st.button("🔄 Phan tich lai", key=f"re_{idx}", use_container_width=True):
                new_r = analyze_image(img["bytes"], st.session_state.app_name)
                new_r["status"] = "done"
                st.session_state.results[img["name"]] = new_r
                st.rerun()


def render_grid():
    if not st.session_state.images:
        st.info("Chua co anh. Upload anh o sidebar (bat Batch Folder de tai nhieu anh).")
        return

    n = len(st.session_state.images)
    cols_per_row = st.session_state.get("grid_cols", 4)
    for i in range(0, n, cols_per_row):
        row_cols = st.columns(cols_per_row)
        for j in range(cols_per_row):
            idx = i + j
            if idx < n:
                with row_cols[j]:
                    render_card(st.session_state.images[idx], idx)


# ===================== MAIN =====================
def main():
    st.markdown("""
    <style>
        body { background: #0d1117; color: #c9d1d9; }
        .stApp { background: #0d1117; }
        [data-testid="stSidebar"] { background: #161b22; }
        .stSelectbox > div > div { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; }
        .stButton > button { background: #238636; color: white; border: none; border-radius: 6px; }
        .stDownloadButton > button { background: #1f6feb; color: white; border: none; border-radius: 6px; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("#  HashTag AI")
    st.caption("Qwen3.6 Plus Vision | SiinJiuYunShan")
    st.divider()

    left, right = st.columns([1, 3])

    with left:
        render_sidebar()

    with right:
        st.markdown(f"### KET QUA  {len(st.session_state.images)} anh")
        if st.session_state.images:
            c1, c2, c3 = st.columns([4, 1, 1])
            with c2:
                st.session_state.grid_cols = st.selectbox(
                    "So cot", [2, 3, 4], index=2,
                    key="grid_cols_sel", label_visibility="collapsed"
                )
            with c3:
                if st.button("🗑 Xoa het", use_container_width=True):
                    st.session_state.images = []
                    st.session_state.results = {}
                    st.session_state.batch_stats = {}
                    st.rerun()
        render_grid()


if __name__ == "__main__":
    main()
