#!/usr/bin/env python3
"""Collect recent legal-research candidates from OpenAlex and Crossref."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


USER_AGENT = "LexFrontier/1.0 (public research discovery tool)"
TOPIC_TERMS = (
    "artificial intelligence",
    "generative ai",
    "large language model",
    "algorithm",
    "automated decision",
    "machine learning",
    "data protection",
    "privacy",
    "platform governance",
    "digital regulation",
    "legal technology",
    "computational law",
    "人工智能",
    "生成式",
    "大模型",
    "算法",
    "自动化决策",
    "数据法",
    "平台治理",
    "数字法治",
)


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_doi(value: str | None) -> str:
    if not value:
        return ""
    doi = value.strip().lower()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:\s*", "", doi)
    return doi.rstrip(" .;,)")


def canonical_url(value: str | None) -> str:
    if not value:
        return ""
    parts = urlsplit(value.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return ""
    host = parts.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), host, path, "", ""))


def normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in normalized if char.isalnum())


def candidate_keys(candidate: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    doi = normalize_doi(candidate.get("doi"))
    if doi:
        keys.append(f"doi:{doi}")
    url = canonical_url(candidate.get("primary_url"))
    if url:
        keys.append(f"url:{hashlib.sha256(url.encode('utf-8')).hexdigest()[:20]}")
    authors = candidate.get("authors") or []
    first_author = authors[0] if authors else ""
    fingerprint = normalized_text((candidate.get("title") or "") + first_author)
    if fingerprint:
        keys.append(f"title:{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:20]}")
    return keys


def request_json(url: str, timeout: int = 25, retries: int = 1) -> dict[str, Any]:
    mailto = os.environ.get("LEXFRONTIER_MAILTO", "").strip()
    user_agent = USER_AGENT + (f"; mailto:{mailto}" if mailto else "")
    request = Request(url, headers={"Accept": "application/json", "User-Agent": user_agent})
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 429 and attempt < retries:
                wait_seconds = min(int(exc.headers.get("Retry-After", "2") or 2), 5)
                time.sleep(wait_seconds)
                continue
            raise
    raise RuntimeError("unreachable")


def inverted_abstract(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    positioned: list[tuple[int, str]] = []
    for word, positions in value.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                positioned.append((position, word))
    return " ".join(word for _, word in sorted(positioned))


def openalex_authors(work: dict[str, Any]) -> list[str]:
    authors: list[str] = []
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") if isinstance(authorship, dict) else None
        name = author.get("display_name") if isinstance(author, dict) else None
        if isinstance(name, str) and name.strip():
            authors.append(name.strip())
    return authors


def primary_source_from_openalex(work: dict[str, Any]) -> tuple[str, list[str], str]:
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    source_name = source.get("display_name") or ""
    issns = source.get("issn") or []
    landing = location.get("landing_page_url") or ""
    return source_name, [value for value in issns if isinstance(value, str)], landing


def date_parts(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    parts = value.get("date-parts")
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
        return ""
    numbers = parts[0]
    if not numbers:
        return ""
    year = numbers[0]
    month = numbers[1] if len(numbers) > 1 else 1
    day = numbers[2] if len(numbers) > 2 else 1
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except (TypeError, ValueError):
        return ""


def crossref_date(item: dict[str, Any]) -> str:
    for field in ("published-online", "published-print", "published", "issued"):
        parsed = date_parts(item.get(field))
        if parsed:
            return parsed
    return ""


def crossref_authors(item: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for author in item.get("author") or []:
        if not isinstance(author, dict):
            continue
        name = " ".join(part for part in (author.get("given", ""), author.get("family", "")) if part).strip()
        if name:
            result.append(name)
    return result


def normalize_work_type(value: str | None) -> str:
    mapping = {
        "article": "journal-article",
        "journal-article": "journal-article",
        "preprint": "preprint",
        "report": "report",
        "proceedings-article": "conference-paper",
    }
    return mapping.get(value or "", value or "")


def strip_jats(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def source_lookup(registry: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_issn: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for source in registry["sources"]:
        by_name[normalized_text(source["name"])] = source
        for issn in source.get("issns", []):
            by_issn[issn.upper()] = source
    return by_issn, by_name


def match_source(
    source_name: str, issns: list[str], by_issn: dict[str, dict[str, Any]], by_name: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    for issn in issns:
        if issn.upper() in by_issn:
            return by_issn[issn.upper()]
    normalized_name = normalized_text(source_name)
    if normalized_name in by_name:
        return by_name[normalized_name]
    for name_key, source in by_name.items():
        if normalized_name and (normalized_name in name_key or name_key in normalized_name):
            return source
    return None


def topic_hits(candidate: dict[str, Any]) -> list[str]:
    haystack = " ".join(
        str(candidate.get(field) or "") for field in ("title", "abstract", "source")
    ).casefold()
    return [term for term in TOPIC_TERMS if term.casefold() in haystack]


def openalex_candidates(
    query: dict[str, Any], start: date, end: date, api_key: str, by_issn: dict[str, Any], by_name: dict[str, Any]
) -> list[dict[str, Any]]:
    params = {
        "search": query["query"],
        "filter": f"from_publication_date:{start.isoformat()},to_publication_date:{end.isoformat()}",
        "per-page": "50",
    }
    if api_key:
        params["api_key"] = api_key
    url = "https://api.openalex.org/works?" + urlencode(params)
    payload = request_json(url)
    candidates: list[dict[str, Any]] = []
    for work in payload.get("results") or []:
        if not isinstance(work, dict):
            continue
        source_name, issns, landing = primary_source_from_openalex(work)
        source = match_source(source_name, issns, by_issn, by_name)
        doi = normalize_doi(work.get("doi"))
        primary_url = f"https://doi.org/{doi}" if doi else (landing or work.get("id") or "")
        candidate = {
            "title": work.get("display_name") or "",
            "authors": openalex_authors(work),
            "source": source_name,
            "publication_date": work.get("publication_date") or "",
            "work_type": normalize_work_type(work.get("type")),
            "doi": doi,
            "primary_url": primary_url,
            "full_text_url": (work.get("open_access") or {}).get("oa_url") or "",
            "abstract": inverted_abstract(work.get("abstract_inverted_index")),
            "language": work.get("language") or query.get("language") or "",
            "source_registry_match": source["name"] if source else "",
            "source_priority": source.get("priority", 0) if source else 0,
            "source_group": source.get("group", "unregistered") if source else "unregistered",
            "discovered_by": [f"openalex:{query['label']}"],
        }
        if candidate["title"] and candidate["publication_date"] and candidate["primary_url"]:
            candidate["topic_hits"] = topic_hits(candidate)
            candidates.append(candidate)
    return candidates


def crossref_candidates(
    source: dict[str, Any], start: date, end: date
) -> list[dict[str, Any]]:
    issn = source["issns"][0]
    params = {
        "filter": f"from-pub-date:{start.isoformat()},until-pub-date:{end.isoformat()}",
        "rows": "100",
        "sort": "published",
        "order": "desc",
    }
    url = f"https://api.crossref.org/journals/{quote(issn)}/works?" + urlencode(params)
    payload = request_json(url)
    candidates: list[dict[str, Any]] = []
    for item in (payload.get("message") or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        title_values = item.get("title") or []
        title = title_values[0] if title_values and isinstance(title_values[0], str) else ""
        doi = normalize_doi(item.get("DOI"))
        primary_url = f"https://doi.org/{doi}" if doi else item.get("URL") or ""
        link_values = item.get("link") or []
        full_text_url = ""
        for link in link_values:
            if isinstance(link, dict) and isinstance(link.get("URL"), str):
                full_text_url = link["URL"]
                break
        candidate = {
            "title": title,
            "authors": crossref_authors(item),
            "source": (item.get("container-title") or [source["name"]])[0],
            "publication_date": crossref_date(item),
            "work_type": normalize_work_type(item.get("type")),
            "doi": doi,
            "primary_url": primary_url,
            "full_text_url": full_text_url,
            "abstract": strip_jats(item.get("abstract")),
            "language": item.get("language") or source["language"],
            "source_registry_match": source["name"],
            "source_priority": source["priority"],
            "source_group": source["group"],
            "discovered_by": [f"crossref:{issn}"],
        }
        if candidate["title"] and candidate["publication_date"] and candidate["primary_url"]:
            candidate["topic_hits"] = topic_hits(candidate)
            candidates.append(candidate)
    return candidates


def deduplicate(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    key_to_index: dict[str, int] = {}
    for candidate in candidates:
        keys = candidate_keys(candidate)
        existing_indexes = {key_to_index[key] for key in keys if key in key_to_index}
        if existing_indexes:
            target_index = min(existing_indexes)
            target = merged[target_index]
            target["discovered_by"] = sorted(set(target["discovered_by"] + candidate["discovered_by"]))
            target["topic_hits"] = sorted(set(target["topic_hits"] + candidate["topic_hits"]))
            if not target.get("abstract") and candidate.get("abstract"):
                target["abstract"] = candidate["abstract"]
            if not target.get("full_text_url") and candidate.get("full_text_url"):
                target["full_text_url"] = candidate["full_text_url"]
            if candidate.get("source_priority", 0) > target.get("source_priority", 0):
                for field in ("source_registry_match", "source_priority", "source_group"):
                    target[field] = candidate[field]
            for key in keys:
                key_to_index[key] = target_index
            continue
        new_index = len(merged)
        merged.append(candidate)
        for key in keys:
            key_to_index[key] = new_index
    return merged


def filter_seen(candidates: list[dict[str, Any]], seen: dict[str, Any]) -> list[dict[str, Any]]:
    seen_keys: set[str] = set()
    for entry in seen.get("entries") or []:
        if isinstance(entry, dict):
            seen_keys.update(key for key in entry.get("keys") or [] if isinstance(key, str))
    return [candidate for candidate in candidates if not (set(candidate_keys(candidate)) & seen_keys)]


def candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, int, str]:
    try:
        publication_ordinal = date.fromisoformat(candidate.get("publication_date") or "").toordinal()
    except ValueError:
        publication_ordinal = 0
    return (
        -int(candidate.get("source_priority", 0)),
        -len(candidate.get("topic_hits") or []),
        -publication_ordinal,
        (candidate.get("title") or "").casefold(),
    )


def collect(
    repo_root: Path,
    days: int,
    as_of: date,
    no_network: bool,
    max_sources: int,
    limit: int,
) -> dict[str, Any]:
    if days < 1 or days > 180:
        raise ValueError("days must be between 1 and 180")
    start = as_of - timedelta(days=days - 1)
    references = Path(__file__).resolve().parents[1] / "references"
    registry = load_json(references / "sources.json")
    queries = load_json(references / "queries.json")["queries"]
    seen_path = repo_root / "data" / "seen.json"
    seen = load_json(seen_path) if seen_path.exists() else {"entries": []}
    by_issn, by_name = source_lookup(registry)
    warnings: list[str] = []
    candidates: list[dict[str, Any]] = []

    if not no_network:
        api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
        for query in queries:
            try:
                candidates.extend(openalex_candidates(query, start, as_of, api_key, by_issn, by_name))
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                warnings.append(f"OpenAlex query '{query['label']}' failed: {exc}")

        automated_sources = [source for source in registry["sources"] if source.get("automated") and source.get("issns")]
        automated_sources.sort(key=lambda source: (-source.get("priority", 0), source["name"]))
        if max_sources:
            automated_sources = automated_sources[:max_sources]
        for source in automated_sources:
            try:
                candidates.extend(crossref_candidates(source, start, as_of))
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                warnings.append(f"Crossref source '{source['name']}' failed: {exc}")
    else:
        warnings.append("Network collection was disabled; this output is not suitable for a final digest.")

    candidates = filter_seen(deduplicate(candidates), seen)
    candidates.sort(key=candidate_sort_key)
    candidates = candidates[:limit]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "window": {"start": start.isoformat(), "end": as_of.isoformat(), "days": days},
        "notice": "Candidate discovery only. Verify primary metadata and apply the selection policy manually.",
        "warnings": warnings,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=default_repo_root())
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-sources", type=int, default=0, help="0 means all automated sources")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--no-network", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = collect(
            args.repo_root.resolve(),
            args.days,
            args.as_of,
            args.no_network,
            args.max_sources,
            args.limit,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"output": str(args.output), "candidate_count": result["candidate_count"], "warnings": len(result["warnings"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
