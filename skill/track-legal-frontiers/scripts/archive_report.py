#!/usr/bin/env python3
"""Validate, render, archive, and optionally publish a LexFrontier digest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


MAX_PAPERS = 5
MAX_LOOKBACK_DAYS = 180
WORK_TYPES = {
    "journal-article",
    "working-paper",
    "preprint",
    "conference-paper",
    "report",
}
ACCESS_LEVELS = {"full_text", "abstract_only"}
PAPER_TEXT_FIELDS = {
    "title_original",
    "title_zh",
    "source",
    "publication_date",
    "work_type",
    "language",
    "access",
    "primary_url",
    "why_recommended",
    "plain_summary",
    "real_problem",
    "innovation",
    "critique",
}
STEELMAN_FIELDS = {"author_case", "opposition_case", "crux", "verdict"}
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}


class ContractError(ValueError):
    """Raised when a draft violates the public report contract."""


def parse_iso_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field} must be an ISO date (YYYY-MM-DD)") from exc


def clean_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value.strip()


def normalize_doi(value: str) -> str:
    doi = value.strip().lower()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:\s*", "", doi)
    return doi.rstrip(" .;,)")


def canonicalize_url(value: str, field: str = "URL") -> str:
    raw = clean_text(value, field)
    parts = urlsplit(raw)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ContractError(f"{field} must be an absolute HTTP(S) URL")
    if parts.username or parts.password:
        raise ContractError(f"{field} must not contain credentials")

    host = parts.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    port = f":{parts.port}" if parts.port else ""
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")

    kept_query = []
    for key, query_value in parse_qsl(parts.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower.startswith("utm_") or key_lower in TRACKING_QUERY_KEYS:
            continue
        kept_query.append((key, query_value))
    query = urlencode(sorted(kept_query))
    return urlunsplit((parts.scheme.lower(), host + port, path, query, ""))


def normalized_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in normalized if char.isalnum())


def work_keys(paper: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    doi = normalize_doi(paper.get("doi", ""))
    if doi:
        keys.append(f"doi:{doi}")

    canonical_url = canonicalize_url(paper["primary_url"], "primary_url")
    if "doi.org/" in canonical_url:
        url_doi = normalize_doi(canonical_url.split("doi.org/", 1)[1])
        if url_doi and f"doi:{url_doi}" not in keys:
            keys.append(f"doi:{url_doi}")
    url_digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:20]
    keys.append(f"url:{url_digest}")

    first_author = paper["authors"][0] if paper["authors"] else ""
    title_author = normalized_title(paper["title_original"] + first_author)
    title_digest = hashlib.sha256(title_author.encode("utf-8")).hexdigest()[:20]
    keys.append(f"title:{title_digest}")
    return keys


def validate_report(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractError("report root must be a JSON object")

    report_date = parse_iso_date(clean_text(payload.get("report_date"), "report_date"), "report_date")
    window_start = parse_iso_date(clean_text(payload.get("window_start"), "window_start"), "window_start")
    window_end = parse_iso_date(clean_text(payload.get("window_end"), "window_end"), "window_end")
    if window_start > window_end:
        raise ContractError("window_start must not be after window_end")
    if window_end > report_date:
        raise ContractError("window_end must not be after report_date")
    if (window_end - window_start).days > MAX_LOOKBACK_DAYS:
        raise ContractError(f"search window must not exceed {MAX_LOOKBACK_DAYS} days")

    editor_note = payload.get("editor_note", "")
    if not isinstance(editor_note, str):
        raise ContractError("editor_note must be a string")

    papers = payload.get("papers")
    if not isinstance(papers, list):
        raise ContractError("papers must be a JSON array")
    if len(papers) > MAX_PAPERS:
        raise ContractError(f"papers must contain at most {MAX_PAPERS} items")

    deep_count = 0
    for index, paper in enumerate(papers, start=1):
        prefix = f"papers[{index - 1}]"
        if not isinstance(paper, dict):
            raise ContractError(f"{prefix} must be an object")
        for field in PAPER_TEXT_FIELDS:
            paper[field] = clean_text(paper.get(field), f"{prefix}.{field}")

        authors = paper.get("authors")
        if not isinstance(authors, list) or not authors:
            raise ContractError(f"{prefix}.authors must be a non-empty array")
        paper["authors"] = [clean_text(author, f"{prefix}.authors") for author in authors]

        publication_date = parse_iso_date(paper["publication_date"], f"{prefix}.publication_date")
        if publication_date < window_start or publication_date > window_end:
            raise ContractError(f"{prefix}.publication_date falls outside the declared search window")
        if (report_date - publication_date).days > MAX_LOOKBACK_DAYS:
            raise ContractError(f"{prefix} is older than {MAX_LOOKBACK_DAYS} days")

        if paper["work_type"] not in WORK_TYPES:
            raise ContractError(f"{prefix}.work_type must be one of {sorted(WORK_TYPES)}")
        if paper["access"] not in ACCESS_LEVELS:
            raise ContractError(f"{prefix}.access must be one of {sorted(ACCESS_LEVELS)}")
        if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", paper["language"]):
            raise ContractError(f"{prefix}.language is not a supported language code")

        paper["primary_url"] = canonicalize_url(paper["primary_url"], f"{prefix}.primary_url")
        full_text_url = paper.get("full_text_url", "")
        if not isinstance(full_text_url, str):
            raise ContractError(f"{prefix}.full_text_url must be a string")
        paper["full_text_url"] = (
            canonicalize_url(full_text_url, f"{prefix}.full_text_url") if full_text_url.strip() else ""
        )

        doi = paper.get("doi", "")
        if not isinstance(doi, str):
            raise ContractError(f"{prefix}.doi must be a string")
        paper["doi"] = normalize_doi(doi)
        if paper["doi"] and not re.fullmatch(r"10\.\d{4,9}/\S+", paper["doi"]):
            raise ContractError(f"{prefix}.doi is not a valid DOI")

        deep_read = paper.get("deep_read")
        if not isinstance(deep_read, bool):
            raise ContractError(f"{prefix}.deep_read must be boolean")
        if deep_read:
            deep_count += 1
            steelman = paper.get("steelman")
            if not isinstance(steelman, dict):
                raise ContractError(f"{prefix}.steelman is required for the deep read")
            for field in STEELMAN_FIELDS:
                steelman[field] = clean_text(steelman.get(field), f"{prefix}.steelman.{field}")
        elif paper.get("steelman") not in (None, {}):
            raise ContractError(f"{prefix}.steelman is only allowed for the deep read")

    expected_deep_count = 1 if papers else 0
    if deep_count != expected_deep_count:
        raise ContractError(f"expected {expected_deep_count} deep-read item, found {deep_count}")

    payload["editor_note"] = editor_note.strip()
    return payload


def load_seen(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "updated_at": None, "entries": []}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("entries"), list):
        raise ContractError("data/seen.json has an unsupported shape")
    return data


def reject_duplicates(report: dict[str, Any], seen: dict[str, Any]) -> list[list[str]]:
    existing_keys: set[str] = set()
    for entry in seen["entries"]:
        if isinstance(entry, dict) and isinstance(entry.get("keys"), list):
            existing_keys.update(key for key in entry["keys"] if isinstance(key, str))

    report_keys: list[list[str]] = []
    current_keys: set[str] = set()
    for index, paper in enumerate(report["papers"], start=1):
        keys = work_keys(paper)
        collision = (set(keys) & existing_keys) or (set(keys) & current_keys)
        if collision:
            raise ContractError(
                f"paper {index} has already been recommended (duplicate key: {sorted(collision)[0]})"
            )
        current_keys.update(keys)
        report_keys.append(keys)
    return report_keys


def markdown_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def render_links(paper: dict[str, Any]) -> str:
    links = [f"[原文或相关页面]({paper['primary_url']})"]
    if paper["full_text_url"] and paper["full_text_url"] != paper["primary_url"]:
        links.append(f"[全文]({paper['full_text_url']})")
    doi_url = f"https://doi.org/{paper['doi']}" if paper["doi"] else ""
    if doi_url and canonicalize_url(doi_url) != paper["primary_url"]:
        links.append(f"[DOI]({doi_url})")
    return " · ".join(links)


def render_paper(index: int, paper: dict[str, Any]) -> list[str]:
    lines = [f"## {index}. {markdown_escape(paper['title_zh'])}", ""]
    if normalized_title(paper["title_original"]) != normalized_title(paper["title_zh"]):
        lines.extend([f"**原标题：** {paper['title_original']}", ""])
    lines.extend(
        [
            f"**作者：** {', '.join(paper['authors'])}",
            "",
            f"**来源：** {paper['source']} · {paper['publication_date']} · `{paper['work_type']}`",
            "",
            f"**链接：** {render_links(paper)}",
            "",
        ]
    )
    if paper["access"] == "abstract_only":
        lines.extend(["> 评估依据：仅基于摘要评估（未取得全文）", ""])

    if paper["deep_read"]:
        lines.extend(
            [
                "### 精读判断",
                "",
                f"**推荐结论：** {paper['why_recommended']}",
                "",
                f"**AI 通俗摘要：** {paper['plain_summary']}",
                "",
                f"**它解决的真问题：** {paper['real_problem']}",
                "",
                f"**创新点：** {paper['innovation']}",
                "",
                f"**最重要的疑问：** {paper['critique']}",
                "",
                "### 双向 Steelman",
                "",
                f"**把作者论证强化到最好：** {paper['steelman']['author_case']}",
                "",
                f"**把反方论证强化到最好：** {paper['steelman']['opposition_case']}",
                "",
                f"**真正的分歧／关键变量：** {paper['steelman']['crux']}",
                "",
                f"**我的判断：** {paper['steelman']['verdict']}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "### 简版评估",
                "",
                f"**推荐结论：** {paper['why_recommended']}",
                "",
                f"**AI 通俗摘要：** {paper['plain_summary']}",
                "",
                f"**真问题：** {paper['real_problem']}",
                "",
                f"**创新点：** {paper['innovation']}",
                "",
                f"**保留意见：** {paper['critique']}",
                "",
            ]
        )
    return lines


def render_report(report: dict[str, Any]) -> str:
    papers = report["papers"]
    lines = [
        f"# 法学前沿论文日报｜{report['report_date']}",
        "",
        f"> - 覆盖窗口：{report['window_start']} 至 {report['window_end']}",
        f"> - 入选：{len(papers)} 篇（宁缺毋滥）",
        f"> - 预计阅读：{'约 10 分钟' if papers else '不到 1 分钟'}",
        "",
    ]
    if report["editor_note"]:
        lines.extend([report["editor_note"], ""])

    lines.extend(["## 今日结论", ""])
    if not papers:
        lines.extend(
            [
                "本次检索没有发现达到推荐门槛且未曾推荐的论文。没有用较弱材料填满篇数。",
                "",
            ]
        )
    else:
        for index, paper in enumerate(papers, start=1):
            lines.append(
                f"{index}. [{markdown_escape(paper['title_zh'])}]({paper['primary_url']}) — {paper['why_recommended']}"
            )
        lines.append("")
        for index, paper in enumerate(papers, start=1):
            lines.extend(render_paper(index, paper))

    lines.extend(
        [
            "---",
            "",
            "## 方法说明",
            "",
            "本日报以来源质量作为准入门槛，再判断具体论文的问题重要性、前沿性、严谨性与创新；不采用引用量、下载量或个人偏好历史排序。已推荐论文不会再次推荐。AI 摘要与评价不能替代原文核验。",
            "",
        ]
    )
    return "\n".join(lines)


def next_report_path(repo_root: Path, report_date: str) -> Path:
    year, month, _ = report_date.split("-")
    folder = repo_root / "reports" / year / month
    first = folder / f"{report_date}.md"
    if not first.exists():
        return first
    for sequence in range(2, 100):
        candidate = folder / f"{report_date}-{sequence:02d}.md"
        if not candidate.exists():
            return candidate
    raise ContractError("too many reports already exist for this date")


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def append_seen(
    seen: dict[str, Any], report: dict[str, Any], report_path: Path, report_keys: list[list[str]], repo_root: Path
) -> None:
    relative_report = report_path.relative_to(repo_root).as_posix()
    for paper, keys in zip(report["papers"], report_keys, strict=True):
        seen["entries"].append(
            {
                "keys": keys,
                "title_original": paper["title_original"],
                "authors": paper["authors"],
                "recommended_on": report["report_date"],
                "first_report": relative_report,
            }
        )
    seen["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_git(repo_root: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def publish(repo_root: Path, paths: list[Path], report_date: str, remote: str) -> str:
    try:
        top_level = Path(run_git(repo_root, ["rev-parse", "--show-toplevel"]).stdout.strip()).resolve()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise ContractError("--push requires repo_root to be inside a Git repository") from exc
    if top_level != repo_root.resolve():
        raise ContractError("repo_root must be the Git repository root when using --push")

    targets = {path.relative_to(repo_root).as_posix() for path in paths}
    staged_before = {
        line.strip()
        for line in run_git(repo_root, ["diff", "--cached", "--name-only"]).stdout.splitlines()
        if line.strip()
    }
    unrelated = staged_before - targets
    if unrelated:
        raise ContractError(
            "refusing to commit because unrelated paths are already staged: " + ", ".join(sorted(unrelated))
        )

    run_git(repo_root, ["add", "--", *sorted(targets)])
    staged_after = {
        line.strip()
        for line in run_git(repo_root, ["diff", "--cached", "--name-only"]).stdout.splitlines()
        if line.strip()
    }
    if not staged_after:
        raise ContractError("nothing changed; no Git commit was created")
    unrelated_after = staged_after - targets
    if unrelated_after:
        raise ContractError("refusing to commit unrelated staged paths")

    try:
        run_git(repo_root, ["commit", "-m", f"docs: archive legal frontier digest {report_date}"])
        run_git(repo_root, ["push", remote, "HEAD"])
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise ContractError(f"Git publication failed: {detail}") from exc
    return run_git(repo_root, ["rev-parse", "HEAD"]).stdout.strip()


def archive(report: dict[str, Any], repo_root: Path, should_push: bool, remote: str) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    seen_path = repo_root / "data" / "seen.json"
    if not seen_path.exists():
        raise ContractError(f"missing seen registry: {seen_path}")

    validated = validate_report(report)
    seen = load_seen(seen_path)
    keys = reject_duplicates(validated, seen)
    report_path = next_report_path(repo_root, validated["report_date"])
    append_seen(seen, validated, report_path, keys, repo_root)

    atomic_write_text(report_path, render_report(validated))
    atomic_write_json(seen_path, seen)

    commit = ""
    if should_push:
        commit = publish(repo_root, [report_path, seen_path], validated["report_date"], remote)
    return {
        "report_path": str(report_path),
        "report_relative_path": report_path.relative_to(repo_root).as_posix(),
        "recommended": len(validated["papers"]),
        "commit": commit,
        "pushed": bool(commit),
    }


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path, help="UTF-8 JSON report draft")
    parser.add_argument("--repo-root", type=Path, default=default_repo_root())
    parser.add_argument("--push", action="store_true", help="commit the report and registry, then push")
    parser.add_argument("--remote", default="origin", help="Git remote used with --push (default: origin)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        with args.draft.open("r", encoding="utf-8") as handle:
            report = json.load(handle)
        result = archive(report, args.repo_root, args.push, args.remote)
    except (OSError, json.JSONDecodeError, ContractError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
