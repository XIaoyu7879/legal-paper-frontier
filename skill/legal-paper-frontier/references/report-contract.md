# Report Contract

`archive_report.py` consumes UTF-8 JSON and renders the public Markdown report. The report shows conclusions, not internal scores or a search diary.

## JSON Shape

```json
{
  "report_date": "2026-08-18",
  "window_start": "2026-08-05",
  "window_end": "2026-08-18",
  "editor_note": "Optional one-sentence note; use an empty string when unnecessary.",
  "papers": [
    {
      "title_original": "Original title",
      "title_zh": "忠实的中文译题",
      "authors": ["Author One", "Author Two"],
      "source": "Journal or institution",
      "publication_date": "2026-08-12",
      "work_type": "journal-article",
      "language": "en",
      "access": "full_text",
      "primary_url": "https://doi.org/10.xxxx/example",
      "full_text_url": "https://example.org/paper.pdf",
      "doi": "10.xxxx/example",
      "deep_read": true,
      "why_recommended": "One compact judgment explaining why this belongs today.",
      "plain_summary": "A plain-Chinese explanation for an intelligent outsider.",
      "real_problem": "The concrete institutional, legal, or social problem the work tackles.",
      "innovation": "The contribution relative to the strongest prior framing.",
      "critique": "The most important limitation or uncertainty.",
      "steelman": {
        "author_case": "Strongest version of the author's case.",
        "opposition_case": "Strongest fair-minded objection.",
        "crux": "The fact, value, mechanism, or interpretation that decides between them.",
        "verdict": "A reasoned bottom line."
      }
    }
  ]
}
```

## Required Values

- `papers`: zero to five items. Two to five is the target; zero or one is allowed under the quality floor.
- `work_type`: `journal-article`, `working-paper`, `preprint`, `conference-paper`, or `report`.
- `language`: ISO-like short code such as `en` or `zh`.
- `access`: `full_text` or `abstract_only`.
- `deep_read`: exactly one `true` when papers are present; none when empty.
- `steelman`: required and nonempty for the deep read; omit it for brief entries.
- `full_text_url`: optional and may be an empty string.
- `doi`: optional and may be an empty string.

For English works, preserve `title_original` exactly and provide `title_zh`. For Chinese works, set both fields to the original Chinese title; the renderer avoids displaying it twice.

## Evidence Calibration

For `abstract_only`, the renderer inserts this exact warning:

> 评估依据：仅基于摘要评估（未取得全文）

All prose must respect that limitation. Use phrases such as “摘要主张” or “作者在摘要中报告”; do not assert unobserved methods or results.

## Public Structure

The renderer produces:

1. Date, coverage window, and a concise quality-floor note.
2. A one-line recommendation list.
3. One deep-read section with bilateral steelman and explicit verdict.
4. Brief evaluations for the remaining works.
5. A short methodology disclosure stating that citation counts and personal preference history were not used.

Keep the complete report readable in about ten minutes. Prefer dense, concrete prose over long background explanations.
