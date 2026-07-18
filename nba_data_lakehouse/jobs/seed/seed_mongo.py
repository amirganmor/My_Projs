"""Load JSON seed files into MongoDB collections."""
from __future__ import annotations

from jobs.common.config import get_config
from jobs.common.logging_utils import get_logger
from jobs.common.mongo_utils import load_json_to_collection, get_doc_count

log = get_logger("seed.mongo")


def seed_mongo() -> dict[str, int]:
    """Load player profiles and scouting reports into MongoDB. Returns doc counts."""
    cfg = get_config()
    seed_path = cfg.mongo_seed_path
    counts: dict[str, int] = {}

    for collection, filename in [
        ("player_profiles", "player_profiles.json"),
        ("scouting_reports", "scouting_reports.json"),
    ]:
        json_path = seed_path / filename
        if not json_path.exists():
            log.warning(f"  Seed file not found: {json_path}")
            counts[collection] = 0
            continue

        log.info(f"  Loading {filename} → {collection}")
        n = load_json_to_collection(json_path, collection, drop_first=True)
        counts[collection] = get_doc_count(collection)
        log.info(f"  {collection}: {counts[collection]:,} documents loaded")

    return counts


if __name__ == "__main__":
    seed_mongo()
