import os
import sys
from pathlib import Path

import pytest

# Unit tests must never write into a running local stack.
os.environ.setdefault("SMIP_CLICKHOUSE_PORT", "1")
os.environ.setdefault("SMIP_KAFKA_BOOTSTRAP", "127.0.0.1:1")
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("smip-data")
    os.environ["SMIP_DATA_DIR"] = str(d)
    return d


@pytest.fixture(scope="session")
def synthetic_match(data_dir):
    import synthetic

    return synthetic.build(data_dir)


class FakeProducer:
    """Captures produced records in memory (replaces Kafka in unit tests)."""

    def __init__(self):
        self.records = []

    def produce(self, topic, key=None, value=None):
        self.records.append((topic, key, value))

    def poll(self, *_):
        return 0

    def flush(self, *_):
        return 0


@pytest.fixture
def fake_producer():
    return FakeProducer()
