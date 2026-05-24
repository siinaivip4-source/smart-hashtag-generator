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
        "images": [],
        "results": {},
        "processing": False,
        "db_connected": False,
        "is_mock": True,
        "dropdown_options": {"object_1": [], "object_2": [], "object_3": [], "style": [], "color": []},
        "start_number": 1,
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

    level1 = set()
    level2 = set()
    level3 = set()
    all_objects = set()
    for t in tags:
        cat = t.get("category", "")
        h = t["hashtag"]
        p = parent_map.get(h)
        if cat == "object":
            all_objects.add(h)
            if p is None:
                level1.add(h)
            elif parent_map.get(p) is None:
                level2.add(h)
            else:
                level3.add(h)

    opts["object_1"] = sorted(all_objects)
    opts["object_2"] = sorted(all_objects)
    opts["object_3"] = sorted(all_objects)
    opts["style"] = sorted(set(t["hashtag"] for t in tags if t.get("category") == "style"))
    opts["color"] = sorted(set(t["hashtag"] for t in tags if t.get("category") == "color"))
    st.session_state.dropdown_options = opts
    return opts


# ===================== AI ENGINE =====================
def analyze_image(image_bytes: bytes, app_name: str):
    from config import AI_API_URL, AI_API_KEY, VISION_SYSTEM_PROMPT
    import httpx

    db = get_db()
    existing_tags = ""
    if db and st.session_state.db_connected:
        existing_tags = ", ".join(db.get_tag_list(app_name))

    st.session_state.is_mock = not (AI_API_KEY and AI_API_URL)

    if st.session_state.is_mock:
        import random
        opts = st.session_state.dropdown_options
        return {
            "object_1": random.choice(opts["object_1"]) if opts["object_1"] else "none",
            "object_2": random.choice(opts["object_2"]) if opts["object_2"] else "none",
            "object_3": random.choice(opts["object_3"]) if opts["object_3"] else "none",
            "style": random.choice(opts["style"]) if opts["style"] else "none",
            "color": random.choice(opts["color"]) if opts["color"] else "none",
            "mood": "none",
            "gender": "none",
        }

    prompt = f"""Analyze this image. Return ONLY JSON:
{{
  "object_1": "level1_object",
  "object_2": "level2_object",
  "object_3": "level3_object",
  "style": "art_style",
  "color": "dominant_color",
  "mood": "none",
  "gender": "none"
}}
Use these as reference: {existing_tags[:500]}"""

    try:
        import base64
        b64 = base64.b64encode(image_bytes).decode()
        payload = {
            "model": "vision-v1",
            "messages": [
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]}
            ],
            "temperature": 0.3,
            "max_tokens": 500,
            "response_format": {"type": "json_object"}
        }
        with httpx.Client(timeout=60) as client:
            resp = client.post(AI_API_URL, json=payload, headers={
                "Authorization": f"Bearer {AI_API_KEY}",
                "Content-Type": "application/json"
            })
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            import json
            result = json.loads(content)
            return {
                "object_1": result.get("object_1", "none"),
                "object_2": result.get("object_2", "none"),
                "object_3": result.get("object_3", "none"),
                "style": result.get("style", "none"),
                "color": result.get("color", "none"),
                "mood": "none",
                "gender": "none",
            }
    except Exception:
        return {"object_1": "none", "object_2": "none", "object_3": "none", "style": "none", "color": "none", "mood": "none", "gender": "none"}


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

        uploaded = st.file_uploader("Upload anh", type=["jpg","jpeg","png","webp","gif"],
                                     accept_multiple_files=True, key="sidebar_upload")

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
            fmt = st.radio("Export", ["CSV", "Excel"], horizontal=True)
            data, fname, mime = export_results(fmt.lower())
            st.download_button("Tai xuong", data, file_name=fname, mime=mime, use_container_width=True)

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


# ===================== BATCH PROCESSING =====================
def run_batch():
    app_name = st.session_state.app_name
    load_dropdown_options(app_name)

    st.session_state.processing = True
    st.session_state.results = {}

    progress = st.progress(0)
    status = st.empty()

    for i, img in enumerate(st.session_state.images):
        status.text(f"Dang xu ly {i+1}/{len(st.session_state.images)}: {img['name']}")
        result = analyze_image(img["bytes"], app_name)
        result["status"] = "done"
        st.session_state.results[img["name"]] = result
        progress.progress((i + 1) / len(st.session_state.images))

    status.text(f"Hoan thanh! {len(st.session_state.images)} anh.")
    st.session_state.processing = False
    st.rerun()


# ===================== UI: MAIN GRID =====================
def render_card(img, idx):
    r = st.session_state.results.get(img["name"], {})
    status = r.get("status", "pending")
    opts = st.session_state.dropdown_options

    with st.container():
        st.markdown(f"""
        <div style="border:1px solid #2a2a3a;border-radius:10px;padding:12px;margin-bottom:10px;background:#0d1117;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <span style="color:#8b949e;font-size:11px;">{img['name'][:20]}...</span>
                <span style="color:#58a6ff;font-size:11px;">{img['size_kb']:.1f}KB</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.image(Image.open(io.BytesIO(img["bytes"])), use_container_width=True)

        st.markdown(f"**STT: {img['stt']}** | CLIP (OpenAI) | {'✅ Done' if status == 'done' else '⏳ Pending'}")

        if status == "done":
            cols = st.columns(2)
            with cols[0]:
                r["object_1"] = st.selectbox("Object 1", options=["none"] + opts["object_1"],
                                              index=max(0, (["none"] + opts["object_1"]).index(r.get("object_1","none"))),
                                              key=f"o1_{idx}", label_visibility="collapsed")
                r["object_2"] = st.selectbox("Object 2", options=["none"] + opts["object_2"],
                                              index=max(0, (["none"] + opts["object_2"]).index(r.get("object_2","none"))),
                                              key=f"o2_{idx}", label_visibility="collapsed")
                r["object_3"] = st.selectbox("Object 3", options=["none"] + opts["object_3"],
                                              index=max(0, (["none"] + opts["object_3"]).index(r.get("object_3","none"))),
                                              key=f"o3_{idx}", label_visibility="collapsed")
                r["style"] = st.selectbox("Style", options=["none"] + opts["style"],
                                           index=max(0, (["none"] + opts["style"]).index(r.get("style","none"))),
                                           key=f"sty_{idx}", label_visibility="collapsed")
            with cols[1]:
                r["color"] = st.selectbox("Color", options=["none"] + opts["color"],
                                           index=max(0, (["none"] + opts["color"]).index(r.get("color","none"))),
                                           key=f"clr_{idx}", label_visibility="collapsed")
                r["mood"] = st.selectbox("Mood", options=["none"], index=0, key=f"mood_{idx}", label_visibility="collapsed")
                r["gender"] = st.selectbox("Gender", options=["none"], index=0, key=f"gen_{idx}", label_visibility="collapsed")

            st.session_state.results[img["name"]] = r

            if st.button("▶", key=f"re_{idx}", use_container_width=True):
                new_r = analyze_image(img["bytes"], st.session_state.app_name)
                new_r["status"] = "done"
                st.session_state.results[img["name"]] = new_r
                st.rerun()


def render_grid():
    if not st.session_state.images:
        st.info("Chua co anh. Upload anh o sidebar.")
        return

    n = len(st.session_state.images)
    cols_per_row = 4
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
        .stButton > button { background: #238636; color: white; border: none; }
        .stDownloadButton > button { background: #1f6feb; color: white; border: none; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("#  HashTag AI")
    st.caption("CLIP (OpenAI) | SiinJiuYunShan")
    st.divider()

    left, right = st.columns([1, 3])

    with left:
        render_sidebar()

    with right:
        st.markdown(f"### KET QUA  {len(st.session_state.images)} anh")
        if st.session_state.images:
            c1, c2 = st.columns([5, 1])
            with c2:
                if st.button("🗑 Xoa toan bo anh", use_container_width=True):
                    st.session_state.images = []
                    st.session_state.results = {}
                    st.rerun()
        render_grid()


if __name__ == "__main__":
    main()
