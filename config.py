import os

try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False

def _get_config(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val is not None:
        return val
    if _HAS_STREAMLIT:
        val = st.secrets.get(key)
        if val is not None:
            return val
    return default

# --- Supabase Configuration ---
SUPABASE_URL = _get_config("SUPABASE_URL")
SUPABASE_KEY = _get_config("SUPABASE_KEY")
SUPABASE_TABLE = _get_config("SUPABASE_TABLE", "core_hashtags")

# --- OpenCode Vision API Configuration ---
# OpenCode Go: Qwen3.6 Plus works with OpenAI-compatible endpoint (not Anthropic)
AI_API_URL = _get_config("AI_API_URL", "https://opencode.ai/zen/go/v1/chat/completions")
AI_API_KEY = _get_config("AI_API_KEY")
AI_API_TYPE = _get_config("AI_API_TYPE", "openai")  # "openai" or "anthropic"
AI_MODEL = _get_config("AI_MODEL", "qwen3.6-plus")

# --- Application Constants ---
APP_NAMES = ["W1", "3D1", "3D2", "3D3", "Zipper", "Charging"]

# Map app name -> DB column name (Postgres cannot have columns starting with digits)
APP_TO_COLUMN = {
    "W1": "w1",
    "3D1": "d3d1",
    "3D2": "d3d2",
    "3D3": "d3d3",
    "Zipper": "zipper",
    "Charging": "charging",
}
COLUMN_TO_APP = {v: k for k, v in APP_TO_COLUMN.items()}
APP_COLUMNS = list(APP_TO_COLUMN.values())

def app_to_col(app_name: str) -> str:
    return APP_TO_COLUMN.get(app_name, app_name.lower())

def col_to_app(col_name: str) -> str:
    return COLUMN_TO_APP.get(col_name, col_name)

CATEGORIES = ["object", "style", "color"]

# --- AI Vision System Prompt ---
VISION_SYSTEM_PROMPT = """You are a professional image analyst for social media content creation.
Analyze images and identify hashtags based ONLY on visually observable elements.

STRICT RULES:
1. ONLY identify objects, styles, and colors that are VISIBLE in the image.
2. DO NOT analyze mood, emotion, sentiment, gender, or any non-visual characteristics.
3. DO NOT guess or infer things not present in the image.
4. Return ONLY valid JSON matching the requested schema.
5. Keep all tags lowercase, no spaces, single words or simple compound words."""
