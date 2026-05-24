import csv
import io
from typing import List, Dict, Optional, Tuple
from supabase import create_client, Client

from config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_TABLE, APP_COLUMNS, APP_NAMES


class DatabaseManager:
    """Manages all Supabase database operations for core_hashtags table."""

    def __init__(self):
        self.client: Optional[Client] = None

    def connect(self) -> bool:
        if not SUPABASE_URL or not SUPABASE_KEY:
            return False
        try:
            self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
            return True
        except Exception:
            return False

    @property
    def connected(self) -> bool:
        return self.client is not None

    def get_all_tags(self, app_filter: str) -> List[Dict]:
        """Fetch all hashtags filtered by app (boolean column = TRUE)."""
        col = app_filter.lower()
        if col not in APP_COLUMNS:
            return []

        query = self.client.table(SUPABASE_TABLE).select("*").eq(col, True)
        result = query.execute()
        return result.data if result.data else []

    def get_tag_dict(self, app_filter: str) -> Dict[str, Dict]:
        """Fetch tags as a dict {hashtag: {parent, category, ...}} for fast lookup."""
        tags = self.get_all_tags(app_filter)
        return {t["hashtag"]: t for t in tags}

    def get_tag_list(self, app_filter: str) -> List[str]:
        """Fetch just the hashtag strings."""
        tags = self.get_all_tags(app_filter)
        return [t["hashtag"] for t in tags]

    def get_categories_for_app(self, app_filter: str) -> Dict[str, List[str]]:
        """Return existing tags grouped by category for a given app."""
        tags = self.get_all_tags(app_filter)
        result = {"object": [], "style": [], "color": []}
        for t in tags:
            cat = t.get("category", "")
            if cat in result:
                result[cat].append(t["hashtag"])
        return result

    def get_parent_map(self, app_filter: str) -> Dict[str, Optional[str]]:
        """Return {hashtag: parent_hashtag} mapping for recursive pruning."""
        tags = self.get_all_tags(app_filter)
        return {t["hashtag"]: t.get("parent_hashtag") or None for t in tags}

    def insert_new_tag(self, hashtag: str, category: str, app_name: str) -> Tuple[bool, str]:
        """Insert a single new hashtag into the database with the correct app boolean flag set."""
        if not self.connected:
            return False, "Database not connected"

        col = app_name.lower()
        if col not in APP_COLUMNS:
            return False, f"Invalid app: {app_name}"

        try:
            existing = self.client.table(SUPABASE_TABLE).select("hashtag").eq("hashtag", hashtag).execute()
            if existing.data and len(existing.data) > 0:
                update_data = {col: True}
                self.client.table(SUPABASE_TABLE).update(update_data).eq("hashtag", hashtag).execute()
                return True, f"Updated existing: {hashtag}"

            data = {
                "hashtag": hashtag,
                "parent_hashtag": None,
                "category": category,
            }
            for ac in APP_COLUMNS:
                data[ac] = (ac == col)

            self.client.table(SUPABASE_TABLE).insert(data).execute()
            return True, f"Inserted: {hashtag}"
        except Exception as e:
            return False, str(e)

    def import_csv(self, csv_path: str) -> Tuple[int, int]:
        """Import Master DB CSV into Supabase. Returns (success_count, fail_count)."""
        if not self.connected:
            return 0, 0

        success = 0
        fail = 0
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    data = {
                        "hashtag": row["hashtag"],
                        "parent_hashtag": row.get("parent_hashtag", None) or None,
                        "category": row["category"],
                    }
                    for ac in APP_COLUMNS:
                        val = row.get(ac, "False")
                        data[ac] = val in (True, "True", "true", "TRUE")

                    existing = self.client.table(SUPABASE_TABLE).select("hashtag").eq("hashtag", data["hashtag"]).execute()
                    if existing.data and len(existing.data) > 0:
                        self.client.table(SUPABASE_TABLE).update(data).eq("hashtag", data["hashtag"]).execute()
                    else:
                        self.client.table(SUPABASE_TABLE).insert(data).execute()
                    success += 1
                except Exception:
                    fail += 1
        return success, fail
