# LexFrontier

An on-demand, public archive of carefully selected frontier legal scholarship. LexFrontier searches recent Chinese and English work, prioritizes AI-law and genuinely interdisciplinary research, explains it in plain Chinese, and archives each digest to GitHub.

[中文说明](README.zh-CN.md)

## What it produces

- Usually 2-5 recommendations from the previous 1-2 weeks; the window may expand to 180 days, never beyond it.
- Zero or one recommendation when the quality floor requires it—no quota padding.
- Original English titles plus faithful Chinese translations.
- A plain-language AI summary, the real problem, innovation, and a calibrated criticism for every work.
- One deep read using bilateral steelmanning: strongest author case, strongest objection, decisive crux, and an explicit verdict.
- Exact disclosure when only an abstract was available.
- Permanent duplicate prevention: the same work is recommended only once.

Citation counts, download counts, social popularity, and personal preference history are deliberately excluded from ranking. Venue quality is an admission signal; paper-level reasoning and evidence determine the final recommendation.

## Repository layout

```text
data/seen.json                              Permanent recommendation registry
reports/YYYY/MM/YYYY-MM-DD[-NN].md          Public digest archive
skill/track-legal-frontiers/SKILL.md        Agent-neutral workflow
skill/track-legal-frontiers/references/     Source, selection, and report contracts
skill/track-legal-frontiers/scripts/        Discovery and archive utilities
tests/                                      Standard-library test suite
```

## Install the Skill

Clone this repository, then expose the nested skill folder to your agent. For Codex on Windows PowerShell:

```powershell
git clone https://github.com/XIaoyu7879/lex-frontier.git
Set-Location lex-frontier
New-Item -ItemType Junction `
  -Path "$env:USERPROFILE\.codex\skills\track-legal-frontiers" `
  -Target "$PWD\skill\track-legal-frontiers"
```

On macOS or Linux:

```bash
git clone https://github.com/XIaoyu7879/lex-frontier.git
cd lex-frontier
ln -s "$(pwd)/skill/track-legal-frontiers" ~/.codex/skills/track-legal-frontiers
```

Other agents that support the open `SKILL.md` convention can load `skill/track-legal-frontiers/SKILL.md` directly.

Invoke it with a prompt such as:

```text
Use $track-legal-frontiers to curate and archive today's legal-frontier digest.
```

The Skill is intentionally on-demand; it does not install a scheduler. Git must already be authenticated for automatic push.

## Run the utilities

Python 3.10+ is sufficient; there are no third-party runtime dependencies.

```powershell
# Candidate discovery only—final selection still requires live verification and reading.
py skill/track-legal-frontiers/scripts/collect_candidates.py `
  --repo-root . --days 14 --output tmp/candidates.json

# Validate, render, deduplicate, commit, and push a completed JSON draft.
py skill/track-legal-frontiers/scripts/archive_report.py `
  tmp/digest.json --repo-root . --push

# Test locally.
py -m unittest discover -s tests -v
```

The optional `OPENALEX_API_KEY` raises OpenAlex API capacity. `LEXFRONTIER_MAILTO` adds a contact address to the Crossref user agent.

## Quality and access

The source registry is a maintained seed list, not a closed canon. Chinese journal screening starts from the current CSSCI cycle; English screening uses leading general law reviews, established peer-reviewed law journals, and strong specialist or interdisciplinary venues. SSRN is treated as a discovery channel, never as automatic quality certification.

Paywalled work may be recommended when its abstract is genuinely informative, but the report must display `仅基于摘要评估（未取得全文）` and must not invent details beyond that abstract.

## License

[MIT](LICENSE)
