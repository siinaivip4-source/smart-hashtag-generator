import os
import streamlit as st

# --- Supabase Configuration ---
# Priority: Streamlit secrets > environment variables > hardcoded defaults
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    st.secrets.get("SUPABASE_URL", "")
)
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    st.secrets.get("SUPABASE_KEY", "")
)
SUPABASE_TABLE = os.environ.get(
    "SUPABASE_TABLE",
    st.secrets.get("SUPABASE_TABLE", "core_hashtags")
)

# --- OpenCode Vision API Configuration ---
AI_API_URL = os.environ.get(
    "AI_API_URL",
    st.secrets.get("AI_API_URL", "https://api.opencode.ai/v1/vision/analyze")
)
AI_API_KEY = os.environ.get(
    "AI_API_KEY",
    st.secrets.get("AI_API_KEY", "")
)

# --- Application Constants ---
APP_NAMES = ["W1", "3D1", "3D2", "3D3", "Zipper", "Charging"]
APP_COLUMNS = [a.lower() for a in APP_NAMES]
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
