from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skill" / "track-legal-frontiers" / "scripts" / "archive_report.py"
SPEC = importlib.util.spec_from_file_location("archive_report", SCRIPT)
archive_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(archive_report)


def sample_paper(**overrides):
    paper = {
        "title_original": "Governing Frontier Models",
        "title_zh": "治理前沿模型",
        "authors": ["Ada Example"],
        "source": "Artificial Intelligence and Law",
        "publication_date": "2026-08-12",
        "work_type": "journal-article",
        "language": "en",
        "access": "full_text",
        "primary_url": "https://doi.org/10.1234/example.1",
        "full_text_url": "https://example.org/paper.pdf",
        "doi": "10.1234/example.1",
        "deep_read": True,
        "why_recommended": "它把抽象治理原则转化为可检验的制度选择。",
        "plain_summary": "文章比较了监管前沿模型的几种制度工具。",
        "real_problem": "监管者如何在证据不足时控制高影响模型风险。",
        "innovation": "把触发监管的条件拆成可观测变量。",
        "critique": "关键风险阈值仍依赖有限证据。",
        "steelman": {
            "author_case": "只要触发条件可验证，分级义务比全面许可更稳健。",
            "opposition_case": "企业掌握关键证据，触发条件可能系统性失灵。",
            "crux": "外部审计能否获得足以识别风险的模型信息。",
            "verdict": "框架值得采用，但其有效性取决于强制信息访问权。"
        }
    }
    paper.update(overrides)
    return paper


def sample_report(papers=None):
    return {
        "report_date": "2026-08-18",
        "window_start": "2026-08-05",
        "window_end": "2026-08-18",
        "editor_note": "",
        "papers": [sample_paper()] if papers is None else papers,
    }


class ArchiveReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        (self.repo / "data").mkdir()
        (self.repo / "data" / "seen.json").write_text(
            json.dumps({"schema_version": 1, "updated_at": None, "entries": []}),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_archive_renders_and_registers(self):
        result = archive_report.archive(sample_report(), self.repo, False, "origin")
        report_path = Path(result["report_path"])
        self.assertTrue(report_path.exists())
        rendered = report_path.read_text(encoding="utf-8")
        self.assertIn("Governing Frontier Models", rendered)
        self.assertIn("双向 Steelman", rendered)
        seen = json.loads((self.repo / "data" / "seen.json").read_text(encoding="utf-8"))
        self.assertEqual(1, len(seen["entries"]))
        self.assertIn("doi:10.1234/example.1", seen["entries"][0]["keys"])

    def test_duplicate_is_rejected(self):
        archive_report.archive(sample_report(), self.repo, False, "origin")
        with self.assertRaisesRegex(archive_report.ContractError, "already been recommended"):
            archive_report.archive(sample_report(), self.repo, False, "origin")

    def test_abstract_only_warning_is_exact(self):
        paper = sample_paper(access="abstract_only", full_text_url="")
        report = archive_report.validate_report(sample_report([paper]))
        rendered = archive_report.render_report(report)
        self.assertIn("> 评估依据：仅基于摘要评估（未取得全文）", rendered)

    def test_empty_report_is_allowed(self):
        result = archive_report.archive(sample_report([]), self.repo, False, "origin")
        rendered = Path(result["report_path"]).read_text(encoding="utf-8")
        self.assertIn("没有发现达到推荐门槛", rendered)

    def test_paper_outside_window_is_rejected(self):
        paper = sample_paper(publication_date="2026-07-01")
        with self.assertRaisesRegex(archive_report.ContractError, "outside the declared search window"):
            archive_report.validate_report(sample_report([paper]))

    def test_non_deep_item_cannot_contain_steelman(self):
        second = sample_paper(
            title_original="A Second Paper",
            title_zh="第二篇论文",
            primary_url="https://doi.org/10.1234/example.2",
            doi="10.1234/example.2",
            deep_read=False,
        )
        with self.assertRaisesRegex(archive_report.ContractError, "only allowed for the deep read"):
            archive_report.validate_report(sample_report([sample_paper(), second]))


if __name__ == "__main__":
    unittest.main()
