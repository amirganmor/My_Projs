"""MongoDB helpers using pymongo."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from jobs.common.config import get_config


def get_client() -> MongoClient:
    cfg = get_config().mongo
    return MongoClient(cfg.uri)


def get_database() -> Database:
    cfg = get_config().mongo
    client = get_client()
    return client[cfg.database]


def get_collection(name: str) -> Collection:
    return get_database()[name]


def load_json_to_collection(
    json_path: str | Path,
    collection_name: str,
    drop_first: bool = True,
) -> int:
    """Load a JSON array file into a MongoDB collection. Returns doc count."""
    with open(json_path) as f:
        docs = json.load(f)

    if not isinstance(docs, list):
        docs = [docs]

    coll = get_collection(collection_name)
    if drop_first:
        coll.drop()

    if docs:
        coll.insert_many(docs)
    return len(docs)


def read_collection(collection_name: str, query: dict | None = None) -> list[dict[str, Any]]:
    coll = get_collection(collection_name)
    cursor = coll.find(query or {})
    return [{k: v for k, v in doc.items() if k != "_id"} for doc in cursor]


def get_doc_count(collection_name: str) -> int:
    return get_collection(collection_name).count_documents({})
