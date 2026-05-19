# tests/conftest.py
import pytest


class FakeClient:
    """In-memory stand-in for GristClient. Records all writes."""

    def __init__(self, tables=None, records=None, columns=None):
        self.doc_id = "fake-doc"
        self._tables = set(tables or [])
        self._records = {t: list(rs) for t, rs in (records or {}).items()}
        self._columns = {t: list(cs) for t, cs in (columns or {}).items()}
        self.created = []
        self.added = {}
        self.added_columns = {}

    def list_tables(self):
        return set(self._tables)

    def create_table(self, table, columns):
        self._tables.add(table)
        self._columns[table] = list(columns)
        self.created.append((table, tuple(columns)))

    def ensure_table(self, table, columns):
        if table not in self._tables:
            self.create_table(table, columns)

    def list_columns(self, table):
        return set(self._columns.get(table, []))

    def add_columns(self, table, columns):
        self._columns.setdefault(table, []).extend(columns)
        self.added_columns.setdefault(table, []).extend(columns)

    def fetch_records(self, table):
        return [dict(r) for r in self._records.get(table, [])]

    def add_records(self, table, rows):
        self.added.setdefault(table, []).extend(rows)
        self._records.setdefault(table, []).extend(rows)


@pytest.fixture
def fake_client():
    return FakeClient
