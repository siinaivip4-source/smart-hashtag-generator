from typing import Dict, List, Optional, Set


def recursive_prune(matched_tags: List[str], parent_map: Dict[str, Optional[str]]) -> List[str]:
    """
    Remove parent hashtags from results when their children are also present.

    Algorithm:
    1. Build a set of hashtags to potentially remove (ancestors).
    2. For each tag, traverse UP the parent chain.
    3. If an ancestor is also in the result set, mark the ancestor for removal.
    4. Iterate until no more ancestors can be removed (recursive effect).

    Example:
        parent_map = {"goku": "anime", "anime": "art", "messi": "football", "football": "sport"}
        matched = ["anime", "goku", "messi", "football"]
        Result: ["goku", "messi"]  (anime removed because goku exists, football removed because messi exists)
    """
    if not matched_tags or not parent_map:
        return matched_tags

    matched_set = set(matched_tags)
    to_remove: Set[str] = set()

    def get_all_ancestors(tag: str) -> Set[str]:
        ancestors = set()
        current = parent_map.get(tag)
        visited = set()
        while current and current not in visited:
            visited.add(current)
            if current in matched_set:
                ancestors.add(current)
            current = parent_map.get(current)
        return ancestors

    changed = True
    while changed:
        changed = False
        for tag in list(matched_set - to_remove):
            ancestors = get_all_ancestors(tag)
            for ancestor in ancestors:
                if ancestor in matched_set and ancestor not in to_remove:
                    to_remove.add(ancestor)
                    changed = True

    result = [t for t in matched_tags if t not in to_remove]
    return result


def filter_by_app(hashtags_with_apps: List[Dict], app_name: str) -> List[str]:
    """
    Filter hashtags that belong to a specific app.
    hashtags_with_apps: list of dicts with keys matching app column names.

    Returns list of matching hashtag strings.
    """
    col = app_name.lower()
    return [h["hashtag"] for h in hashtags_with_apps if h.get(col) is True]
