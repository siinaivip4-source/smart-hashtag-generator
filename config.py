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
AI_API_URL = _get_config("AI_API_URL", "https://api.opencode.ai/v1/vision/analyze")
AI_API_KEY = _get_config("AI_API_KEY")

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

# --- AI Vision Prompt (Engineering) ---
VISION_SYSTEM_PROMPT = """You are a professional image analyst for social media content creation.
Your task is to analyze the uploaded image and identify hashtags based ONLY on visually observable elements.

STRICT RULES:
1. ONLY identify objects, styles, and colors that are VISIBLE in the image.
2. DO NOT analyze mood, emotion, sentiment, gender, or any non-visual characteristics.
3. DO NOT guess or infer things not present in the image.
4. For objects: identify the main subjects (people, animals, items, scenes).
5. For styles: identify the visual art style (2D, 3D, realistic, anime, cartoon, etc.).
6. For colors: identify the dominant and notable colors in the image.
7. Return ONLY valid JSON, no other text.

Return format (strict JSON):
{
  "exact_matches": ["existing_hashtag_from_provided_list", ...],
  "proposed_objects": ["new_object_proposal", ...],
  "proposed_styles": ["new_style_proposal", ...],
  "proposed_colors": ["new_color_proposal", ...]
}"""


def build_analysis_prompt(existing_tags: str) -> str:
    """Build the user prompt with the existing tag list for matching."""
    return f"""Analyze this image and identify hashtags.

EXISTING HASHTAGS IN DATABASE (use these for exact_matches if you see them in the image):
{existing_tags}

For exact_matches: ONLY include tags from the list above that are ACTUALLY visible in the image.
For proposed_*: propose NEW tags NOT in the list above, based only on what you SEE.

Keep all tags lowercase, no spaces, single words or simple compound words.
Maximum 5 proposed tags per category."""
