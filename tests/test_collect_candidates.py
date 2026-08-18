from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skill" / "track-legal-frontiers" / "scripts" / "collect_candidates.py"
SPEC = importlib.util.spec_from_file_location("collect_candidates", SCRIPT)
collector = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(collector)


class CollectCandidatesTests(unittest.TestCase):
    def test_no_network_mode_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "data").mkdir()
            (repo / "data" / "seen.json").write_text(
                json.dumps({"schema_version": 1, "updated_at": None, "entries": []}),
                encoding="utf-8",
            )
            result = collector.collect(repo, 14, date(2026, 8, 18), True, 0, 300)
        self.assertEqual(0, result["candidate_count"])
        self.assertIn("not suitable for a final digest", result["warnings"][0])

    def test_deduplicate_merges_discovery_and_abstract(self):
        first = {
            "title": "One Paper",
            "authors": ["A Author"],
            "doi": "10.1000/test",
            "primary_url": "https://doi.org/10.1000/test",
            "abstract": "",
            "full_text_url": "",
            "source_priority": 3,
            "source_registry_match": "Journal",
            "source_group": "law",
            "discovered_by": ["openalex:q"],
            "topic_hits": ["algorithm"],
        }
        second = dict(first)
        second.update(
            {
                "abstract": "Useful abstract",
                "discovered_by": ["crossref:1234"],
                "topic_hits": ["privacy"],
            }
        )
        merged = collector.deduplicate([first, second])
        self.assertEqual(1, len(merged))
        self.assertEqual("Useful abstract", merged[0]["abstract"])
        self.assertEqual(["crossref:1234", "openalex:q"], merged[0]["discovered_by"])

    def test_seen_registry_filters_candidate(self):
        candidate = {
            "title": "One Paper",
            "authors": ["A Author"],
            "doi": "10.1000/test",
            "primary_url": "https://doi.org/10.1000/test",
        }
        seen = {"entries": [{"keys": ["doi:10.1000/test"]}]}
        self.assertEqual([], collector.filter_seen([candidate], seen))

    def test_invalid_lookback_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 180"):
            collector.collect(Path("."), 181, date(2026, 8, 18), True, 0, 300)

    def test_sort_prefers_source_then_topic_then_recency(self):
        candidates = [
            {"title": "old", "source_priority": 4, "topic_hits": ["ai"], "publication_date": "2026-08-01"},
            {"title": "new", "source_priority": 4, "topic_hits": ["ai"], "publication_date": "2026-08-17"},
            {"title": "lower source", "source_priority": 3, "topic_hits": ["ai", "law"], "publication_date": "2026-08-18"},
        ]
        candidates.sort(key=collector.candidate_sort_key)
        self.assertEqual(["new", "old", "lower source"], [item["title"] for item in candidates])


if __name__ == "__main__":
    unittest.main()
