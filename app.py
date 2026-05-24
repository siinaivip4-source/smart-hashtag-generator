import streamlit as st
import io
import os
import base64
import pandas as pd
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
import threading

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
        "images": [],
        "results": {},
        "processing": False,
        "db_connected": False,
        "is_mock": True,
        "dropdown_options": {"object_1": [], "object_2": [], "object_3": [], "style": [], "color": []},
        "start_number": 1,
        "ai_error": None,
        "batch_stats": {"total": 0, "done": 0, "errors": 0},
        "grid_cols": 4,
        "max_img_size": 800,
        "img_quality": 85,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ===================== IMAGE COMPRESSION =====================
def compress_image(image_bytes: bytes, max_size: int = 800, quality: int = 85) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    if img.width > max_size or img.height > max_size:
        ratio = min(max_size / img.width, max_size / img.height)
        new_w = int(img.width * ratio)
        new_h = int(img.height * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


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


# ===================== OBJECT DEDUP =====================
def normalize_objects(result: dict) -> dict:
    objects = [result.get("object_1", "none"), result.get("object_2", "none"), result.get("object_3", "none")]
    seen = set()
    cleaned = []
    for obj in objects:
        obj = str(obj).strip().lower()
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


# ===================== AUTO-FILL EMPTY FIELDS =====================
def auto_fill_empty(result: dict, image_bytes: bytes) -> dict:
    """If AI returned 'none', re-analyze with a stronger creative prompt."""
    needs_retry = False
    obj_all_none = all(result.get(f, "none") in ("none", "", "nan") for f in ["object_1", "object_2", "object_3"])
    style_none = result.get("style", "none") in ("none", "", "nan")
    color_none = result.get("color", "none") in ("none", "", "nan")

    if obj_all_none or style_none or color_none:
        needs_retry = True

    if not needs_retry:
        return result

    # Re-analyze with a more forceful creative prompt
    from ai_engine import AIVisionEngine
    engine = AIVisionEngine()
    retry_prompt = f"""Analyze this image AGAIN. Previous attempt failed to identify objects/style/color.

RULES:
- object_1 is MANDATORY — propose the main subject you SEE
- style is MANDATORY — identify the art style (2d, 3d, realistic, anime, cartoon, sketch, etc.)
- color is MANDATORY — identify the dominant color
- BE CREATIVE if nothing matches exactly
- Return ONLY JSON: {{"object_1": "...", "object_2": "none", "object_3": "none", "style": "...", "color": "...", "mood": "none", "gender": "none"}}"""

    try:
        retry_result = engine.analyze_image(image_bytes, "", custom_prompt=retry_prompt)
        if retry_result:
            if obj_all_none:
                result["object_1"] = retry_result.get("object_1", "none")
                result["object_2"] = retry_result.get("object_2", "none")
                result["object_3"] = retry_result.get("object_3", "none")
                result["_ai_suggested_obj"] = True
            if style_none and retry_result.get("style", "none") not in ("none", "", "nan"):
                result["style"] = retry_result["style"]
                result["_ai_suggested_style"] = True
            if color_none and retry_result.get("color", "none") not in ("none", "", "nan"):
                result["color"] = retry_result["color"]
                result["_ai_suggested_color"] = True
    except Exception:
        pass

    # Fallback: ensure style & color are NEVER "none"
    opts = st.session_state.dropdown_options

    # Object 1 is mandatory
    if result.get("object_1", "none") in ("none", "", "nan"):
        if opts["object_1"]:
            result["object_1"] = opts["object_1"][0]
        else:
            result["object_1"] = "unknown_object"
        result["_fallback_obj"] = True

    # Style is mandatory — propose creative fallback
    if result.get("style", "none") in ("none", "", "nan"):
        creative_styles = ["realistic", "animeart", "2d", "3d", "cartoon", "sketch", "illustration", "photorealistic"]
        if opts["style"]:
            result["style"] = opts["style"][0]
        else:
            result["style"] = creative_styles[0]
        result["_fallback_style"] = True

    # Color is mandatory — propose creative fallback
    if result.get("color", "none") in ("none", "", "nan"):
        creative_colors = ["black", "white", "red", "blue", "green", "yellow", "multicolor"]
        if opts["color"]:
            result["color"] = opts["color"][0]
        else:
            result["color"] = creative_colors[0]
        result["_fallback_color"] = True

    return result
def analyze_image(image_bytes: bytes, app_name: str) -> dict:
    from ai_engine import AIVisionEngine
    from config import AI_API_KEY, AI_API_URL

    db = get_db()
    existing_tags = ""
    if db and st.session_state.db_connected:
        existing_tags = ", ".join(db.get_tag_list(app_name))

    st.session_state.is_mock = not (AI_API_KEY and AI_API_URL)

    engine = AIVisionEngine()
    result = engine.analyze_image(image_bytes, existing_tags)
    result = normalize_objects(result)
    return auto_fill_empty(result, image_bytes)


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

        # Image compression settings
        with st.expander("🖼 Nen anh (tăng tốc)"):
            st.session_state.max_img_size = st.slider("Max size (px)", 400, 1200, 800, key="max_size_slider")
            st.session_state.img_quality = st.slider("Chat luong JPEG", 50, 100, 85, key="quality_slider")

        st.divider()
        st.markdown("### 📁 Nguon anh")

        # Folder-like upload
        uploaded = st.file_uploader(
            "Tai anh (chon nhieu file = upload folder)",
            type=["jpg","jpeg","png","webp","gif"],
            accept_multiple_files=True, key="folder_upload"
        )

        if uploaded:
            # Compress and store
            st.session_state.images = []
            max_size = st.session_state.max_img_size
            quality = st.session_state.img_quality
            for i, uf in enumerate(uploaded):
                raw = uf.read()
                compressed = compress_image(raw, max_size, quality)
                img = Image.open(io.BytesIO(compressed))
                st.session_state.images.append({
                    "name": uf.name,
                    "bytes": compressed,
                    "size_kb": len(compressed) / 1024,
                    "stt": st.session_state.start_number + i,
                })
            orig_size = sum(len(uf.read() if hasattr(uf, 'read') else b'') for uf in uploaded) / 1024
            new_size = sum(img["size_kb"] for img in st.session_state.images)
            st.success(f"Da chon {len(uploaded)} anh")
            if orig_size > 0:
                st.caption(f"Nen: {orig_size:.0f}KB → {new_size:.0f}KB ({100-new_size/orig_size*100:.0f}% giam)")

        # Run button
        if st.button("▶ Chay toan bo", type="primary", use_container_width=True,
                      disabled=not st.session_state.app_name or not st.session_state.images):
            run_batch_parallel()

        # Export
        if st.session_state.results:
            st.divider()
            st.markdown("### 📤 Xuat File")
            fmt = st.radio("Dinh dang", ["CSV", "Excel"], horizontal=True, key="export_fmt")
            data, fname, mime = export_results(fmt.lower())
            st.download_button(f"Tai xuong {fmt}", data, file_name=fname, mime=mime, use_container_width=True)

            bs = st.session_state.batch_stats
            if bs.get("total", 0) > 0:
                with st.expander("Thong ke"):
                    st.metric("Tong", bs["total"])
                    st.metric("Xong", bs["done"])
                    st.metric("Loi", bs["errors"])

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


# ===================== PARALLEL BATCH PROCESSING =====================
def process_single(img_data: dict, app_name: str) -> tuple:
    try:
        result = analyze_image(img_data["bytes"], app_name)
        result["status"] = "done"
        return img_data["name"], result, None
    except Exception as e:
        return img_data["name"], {"status": "error", "error": str(e)[:200]}, str(e)[:200]

def run_batch_parallel():
    app_name = st.session_state.app_name
    load_dropdown_options(app_name)

    st.session_state.processing = True
    st.session_state.results = {}
    st.session_state.batch_stats = {"total": len(st.session_state.images), "done": 0, "errors": 0}

    progress = st.progress(0)
    status = st.empty()

    # Parallel processing with ThreadPoolExecutor (I/O bound, more workers = faster)
    max_workers = min(8, len(st.session_state.images))
    import time as _time
    _t0 = _time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_single, img, app_name): img["name"] for img in st.session_state.images}
        for i, future in enumerate(as_completed(futures)):
            name, result, error = future.result()
            st.session_state.results[name] = result
            if error:
                st.session_state.batch_stats["errors"] += 1
            else:
                st.session_state.batch_stats["done"] += 1
            progress.progress((i + 1) / len(st.session_state.images))
            status.text(f"Da xu ly {i+1}/{len(st.session_state.images)}")

    elapsed = _time.time() - _t0
    status.text(f"Hoan thanh! {st.session_state.batch_stats['done']} xong, {st.session_state.batch_stats['errors']} loi trong {elapsed:.1f}s")
    st.session_state.processing = False
    st.rerun()


# ===================== SUGGEST MISSING =====================
def suggest_missing(img: dict, idx: int):
    """When a card has 'none' fields, this re-analyzes with a fallback prompt or picks from DB."""
    r = st.session_state.results.get(img["name"], {})
    opts = st.session_state.dropdown_options
    import random

    # Check what's missing and fill from DB
    changed = False
    if r.get("object_1", "none") in ("none", "", "nan") and opts["object_1"]:
        r["object_1"] = random.choice(opts["object_1"][:20]) if len(opts["object_1"]) > 20 else random.choice(opts["object_1"])
        r["_suggested_obj"] = True
        changed = True
    if r.get("style", "none") in ("none", "", "nan") and opts["style"]:
        r["style"] = random.choice(opts["style"][:10]) if len(opts["style"]) > 10 else random.choice(opts["style"])
        r["_suggested_style"] = True
        changed = True
    if r.get("color", "none") in ("none", "", "nan") and opts["color"]:
        r["color"] = random.choice(opts["color"][:10]) if len(opts["color"]) > 10 else random.choice(opts["color"])
        r["_suggested_color"] = True
        changed = True

    if changed:
        st.session_state.results[img["name"]] = r
        st.toast(f"Da goi y hashtag cho {img['name'][:20]}...", icon="💡")
    else:
        st.toast("Tat ca cac truong deu da co du lieu", icon="✅")
def safe_index(options, value):
    try:
        return options.index(value)
    except ValueError:
        return 0


def render_card(img, idx):
    r = st.session_state.results.get(img["name"], {})
    status = r.get("status", "pending")
    opts = st.session_state.dropdown_options

    # Status badge
    if status == "done":
        badge = '<span style="color:#3fb950;font-size:10px;">● Đã xong</span>'
    elif status == "processing":
        badge = '<span style="color:#d29922;font-size:10px;">● Đang xử lý...</span>'
    elif status == "error":
        badge = '<span style="color:#f85149;font-size:10px;">● Lỗi</span>'
    else:
        badge = '<span style="color:#8b949e;font-size:10px;">○ Chưa chạy</span>'

    with st.container():
        # Header bar
        st.markdown(f"""
        <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:6px 10px;margin-bottom:4px;display:flex;justify-content:space-between;align-items:center;">
            <span style="color:#8b949e;font-size:10px;">{img['name'][:18]}...</span>
            <span style="color:#58a6ff;font-size:10px;">{img['size_kb']:.0f}KB</span>
        </div>
        """, unsafe_allow_html=True)

        # Image
        st.image(Image.open(io.BytesIO(img["bytes"])), use_container_width=True)

        # Info line
        st.markdown(f"**STT:{img['stt']}** | Qwen3.6 | {badge}", unsafe_allow_html=True)

        if status == "done":
            # Show suggestion badges
            if r.get("_ai_suggested_obj") or r.get("_ai_suggested_style") or r.get("_ai_suggested_color"):
                st.caption("🤖 AI tự đề xuất hashtag mới (không có trong DB)")
            if r.get("_fallback_obj"):
                st.caption("⚠️ Không nhận diện được Object — lấy từ DB")

            # OBJECT section
            st.markdown('<div style="font-size:9px;color:#8b949e;margin-top:4px;">🔹 OBJECT</div>', unsafe_allow_html=True)
            o1_opts = ["none"] + opts["object_1"]
            r["object_1"] = st.selectbox("Object 1", options=o1_opts,
                                          index=safe_index(o1_opts, r.get("object_1","none")),
                                          key=f"o1_{idx}", label_visibility="collapsed")
            o2_opts = ["none"] + opts["object_2"]
            r["object_2"] = st.selectbox("Object 2", options=o2_opts,
                                          index=safe_index(o2_opts, r.get("object_2","none")),
                                          key=f"o2_{idx}", label_visibility="collapsed")
            o3_opts = ["none"] + opts["object_3"]
            r["object_3"] = st.selectbox("Object 3", options=o3_opts,
                                          index=safe_index(o3_opts, r.get("object_3","none")),
                                          key=f"o3_{idx}", label_visibility="collapsed")

            # STYLE/COLOR section
            st.markdown('<div style="font-size:9px;color:#8b949e;margin-top:4px;"> STYLE / COLOR</div>', unsafe_allow_html=True)
            s_opts = ["none"] + opts["style"]
            r["style"] = st.selectbox("Style", options=s_opts,
                                       index=safe_index(s_opts, r.get("style","none")),
                                       key=f"sty_{idx}", label_visibility="collapsed")
            c_opts = ["none"] + opts["color"]
            r["color"] = st.selectbox("Color", options=c_opts,
                                       index=safe_index(c_opts, r.get("color","none")),
                                       key=f"clr_{idx}", label_visibility="collapsed")
            r["mood"] = st.selectbox("Mood", options=["none"], index=0, key=f"mood_{idx}", label_visibility="collapsed")
            r["gender"] = st.selectbox("Gender", options=["none"], index=0, key=f"gen_{idx}", label_visibility="collapsed")

            st.session_state.results[img["name"]] = r

            # Buttons: re-analyze + suggest
            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("🔄 Chay lai", key=f"re_{idx}", use_container_width=True):
                    st.session_state.results[img["name"]] = {"status": "processing"}
                    st.rerun()
                    new_r = analyze_image(img["bytes"], st.session_state.app_name)
                    new_r["status"] = "done"
                    st.session_state.results[img["name"]] = new_r
                    st.rerun()
            with bc2:
                if st.button("✨ Goi y", key=f"sug_{idx}", use_container_width=True):
                    suggest_missing(img, idx)
                    st.rerun()

        elif status == "pending":
            st.caption("Hashtag sẽ xuất hiện ở đây sau khi chạy.")
            if st.button("▶", key=f"run_{idx}", use_container_width=True):
                st.session_state.results[img["name"]] = {"status": "processing"}
                st.rerun()
                new_r = analyze_image(img["bytes"], st.session_state.app_name)
                new_r["status"] = "done"
                st.session_state.results[img["name"]] = new_r
                st.rerun()

        elif status == "processing":
            with st.spinner("Đang xử lý..."):
                pass

        elif status == "error":
            st.error(f"Lỗi: {r.get('error', 'Unknown')}")
            if st.button("▶ Thử lại", key=f"retry_{idx}", use_container_width=True):
                st.session_state.results[img["name"]] = {"status": "processing"}
                st.rerun()
                new_r = analyze_image(img["bytes"], st.session_state.app_name)
                new_r["status"] = "done"
                st.session_state.results[img["name"]] = new_r
                st.rerun()


def render_grid():
    if not st.session_state.images:
        st.info("Chưa có ảnh. Upload ảnh ở sidebar (chọn nhiều file = upload folder).")
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
        .stSlider > div > div > div { background: #21262d; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("#  HashTag AI")
    st.caption("Qwen3.6 Plus Vision | SiinJiuYunShan")
    st.divider()

    left, right = st.columns([1, 3])

    with left:
        render_sidebar()

    with right:
        bs = st.session_state.batch_stats
        total = len(st.session_state.images)
        done = bs.get("done", 0)
        errors = bs.get("errors", 0)
        st.markdown(f"### KẾT QUẢ  {total} ảnh · {done} xong · {errors} lỗi")

        if st.session_state.images:
            c1, c2, c3 = st.columns([4, 1, 1])
            with c2:
                st.session_state.grid_cols = st.selectbox(
                    "Số cột", [2, 3, 4, 5], index=2,
                    key="grid_cols_sel", label_visibility="collapsed"
                )
            with c3:
                if st.button("🗑 Xóa hết", use_container_width=True):
                    st.session_state.images = []
                    st.session_state.results = {}
                    st.session_state.batch_stats = {"total": 0, "done": 0, "errors": 0}
                    st.rerun()
        render_grid()


if __name__ == "__main__":
    main()
