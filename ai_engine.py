import json
import httpx
from typing import Dict, List, Optional

from config import AI_API_URL, AI_API_KEY, VISION_SYSTEM_PROMPT, build_analysis_prompt


class AIVisionEngine:
    """Handles communication with OpenCode.ai Vision API for image analysis."""

    def __init__(self):
        self.api_url = AI_API_URL
        self.api_key = AI_API_KEY
        self.timeout = 60.0

    def analyze_image(self, image_bytes: bytes, existing_tags: str,
                      mime_type: str = "image/png") -> Optional[Dict]:
        """
        Send image to AI Vision API and get structured hashtag analysis.

        Returns:
            Dict with keys: exact_matches, proposed_objects, proposed_styles, proposed_colors
            or None on failure.
        """
        if not self.api_url or not self.api_key:
            return self._mock_analyze(existing_tags)

        user_prompt = build_analysis_prompt(existing_tags)

        try:
            import base64
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            data_url = f"data:{mime_type};base64,{image_b64}"

            payload = {
                "model": "vision-v1",
                "messages": [
                    {"role": "system", "content": VISION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {"url": data_url}}
                        ]
                    }
                ],
                "temperature": 0.3,
                "max_tokens": 2000,
                "response_format": {"type": "json_object"}
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "SmartHashtagGenerator/2.0"
            }

            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(self.api_url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()

            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return self._parse_response(content)

        except Exception as e:
            return {"error": str(e), "exact_matches": [], "proposed_objects": [],
                    "proposed_styles": [], "proposed_colors": []}

    def _parse_response(self, content: str) -> Optional[Dict]:
        """Parse AI response, handling various JSON formatting issues."""
        if not content:
            return None

        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

        try:
            data = json.loads(content)
            return {
                "exact_matches": self._ensure_list(data.get("exact_matches", [])),
                "proposed_objects": self._ensure_list(data.get("proposed_objects", [])),
                "proposed_styles": self._ensure_list(data.get("proposed_styles", [])),
                "proposed_colors": self._ensure_list(data.get("proposed_colors", [])),
            }
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                try:
                    data = json.loads(content[start:end + 1])
                    return {
                        "exact_matches": self._ensure_list(data.get("exact_matches", [])),
                        "proposed_objects": self._ensure_list(data.get("proposed_objects", [])),
                        "proposed_styles": self._ensure_list(data.get("proposed_styles", [])),
                        "proposed_colors": self._ensure_list(data.get("proposed_colors", [])),
                    }
                except json.JSONDecodeError:
                    pass
        return None

    def _ensure_list(self, value) -> List[str]:
        if isinstance(value, list):
            return [str(v).strip().lower().replace(" ", "") for v in value
                    if str(v).strip()]
        return []

    def _mock_analyze(self, existing_tags: str) -> Dict:
        """Fallback mock analysis when no API key is configured (for testing UI)."""
        return {
            "exact_matches": [],
            "proposed_objects": ["sampleobject1", "sampleobject2"],
            "proposed_styles": ["samplestyle1"],
            "proposed_colors": ["blue", "white", "gold"],
            "_mock": True
        }
