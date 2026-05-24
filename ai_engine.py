import json
import base64
import httpx
from typing import Dict, List, Optional

from config import AI_API_URL, AI_API_KEY, AI_API_TYPE, AI_MODEL, VISION_SYSTEM_PROMPT


class AIVisionEngine:
    """Handles communication with AI Vision API for image analysis."""

    def __init__(self):
        self.api_url = AI_API_URL
        self.api_key = AI_API_KEY
        self.api_type = AI_API_TYPE
        self.model = AI_MODEL
        self.timeout = 90.0

    def analyze_image(self, image_bytes: bytes, existing_tags: str,
                      mime_type: str = "image/png", custom_prompt: str = None) -> Optional[Dict]:
        if not self.api_key or not self.api_url:
            return self._mock_analyze(existing_tags)

        if custom_prompt:
            user_prompt = custom_prompt
        else:
            user_prompt = self._build_prompt(existing_tags)

        try:
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

            if self.api_type == "anthropic":
                return self._call_anthropic(image_b64, mime_type, user_prompt)
            else:
                return self._call_openai(image_b64, mime_type, user_prompt)

        except Exception as e:
            return {"error": str(e)[:200], "exact_matches": [],
                    "proposed_objects": [], "proposed_styles": [],
                    "proposed_colors": [], "object_1": "none",
                    "object_2": "none", "object_3": "none",
                    "style": "none", "color": "none", "mood": "none", "gender": "none"}

    def _call_anthropic(self, image_b64: str, mime_type: str, prompt: str) -> Dict:
        media_type = mime_type if mime_type.startswith("image/") else "image/png"
        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "system": VISION_SYSTEM_PROMPT,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image", "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_b64
                    }}
                ]
            }]
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "SmartHashtagGenerator/2.0"
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(self.api_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = data["content"][0]["text"]
        return self._parse_response(content)

    def _call_openai(self, image_b64: str, mime_type: str, prompt: str) -> Dict:
        data_url = f"data:{mime_type};base64,{image_b64}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]}
            ],
            "temperature": 0.3,
            "max_tokens": 1024,
            "response_format": {"type": "json_object"}
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "SmartHashtagGenerator/2.0"
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(self.api_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        return self._parse_response(content)

    def _build_prompt(self, existing_tags: str) -> str:
        return f"""Analyze this image and identify hashtags.

Return ONLY JSON with these fields:
{{
  "object_1": "main_subject",
  "object_2": "secondary_subject_or_none",
  "object_3": "detail_subject_or_none",
  "style": "art_style",
  "color": "dominant_color",
  "mood": "none",
  "gender": "none"
}}

EXISTING DATABASE TAGS: {existing_tags[:600]}

CRITICAL RULES:
- IF you see a match in the existing tags list → use that exact tag
- IF nothing matches in existing tags → CREATE A NEW TAG based on what you SEE
- NEVER return "none" for object_1, style, or color — always propose something
- object_1 is MANDATORY, must be a real value
- style and color must NEVER be "none" — if unsure, propose the closest match
- object_2 and object_3 can be "none" if image has only 1 main subject
- Mood and gender must always be "none"
- Keep all tags lowercase, no spaces, simple words
- Return ONLY valid JSON, no markdown"""

    def _parse_response(self, content: str) -> Dict:
        if not content:
            return self._empty_result()

        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

        try:
            data = json.loads(content)
            return {
                "object_1": str(data.get("object_1", "none")).lower().replace(" ", ""),
                "object_2": str(data.get("object_2", "none")).lower().replace(" ", ""),
                "object_3": str(data.get("object_3", "none")).lower().replace(" ", ""),
                "style": str(data.get("style", "none")).lower().replace(" ", ""),
                "color": str(data.get("color", "none")).lower().replace(" ", ""),
                "mood": "none",
                "gender": "none",
            }
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                try:
                    data = json.loads(content[start:end + 1])
                    return {
                        "object_1": str(data.get("object_1", "none")).lower().replace(" ", ""),
                        "object_2": str(data.get("object_2", "none")).lower().replace(" ", ""),
                        "object_3": str(data.get("object_3", "none")).lower().replace(" ", ""),
                        "style": str(data.get("style", "none")).lower().replace(" ", ""),
                        "color": str(data.get("color", "none")).lower().replace(" ", ""),
                        "mood": "none",
                        "gender": "none",
                    }
                except json.JSONDecodeError:
                    pass
        return self._empty_result()

    def _empty_result(self) -> Dict:
        return {"object_1": "none", "object_2": "none", "object_3": "none",
                "style": "none", "color": "none", "mood": "none", "gender": "none"}

    def _mock_analyze(self, existing_tags: str) -> Dict:
        return {
            "object_1": "mock_object1",
            "object_2": "mock_object2",
            "object_3": "mock_object3",
            "style": "mock_style",
            "color": "mock_color",
            "mood": "none",
            "gender": "none",
            "_mock": True
        }
