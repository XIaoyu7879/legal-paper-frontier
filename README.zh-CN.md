# legal-paper-frontier｜法学前沿论文雷达

legal-paper-frontier 是一个按需调用、公开归档的法学前沿论文 Skill。它检索近期中英文成果，优先关注法律与 AI、算法治理、计算法学、法律科技以及真正具有法律贡献的交叉学科研究，用普通人也能理解的中文解释，并将每次日报按日期保存到 GitHub。

[English README](README.md)

## 每次会得到什么

- 通常精选过去 1-2 周的 2-5 篇论文；不足时逐步回溯，但最多不超过半年。
- 达不到质量门槛时可以只推荐 1 篇，甚至明确“今日无推荐”，绝不凑数。
- 英文论文保留原标题，并给出忠实的中文译题。
- 每篇包含：原文或相关链接、AI 通俗摘要、论文解决的真问题、创新点和经校准的批评。
- 最值得精读的 1 篇采用“双向 Steelman”：强化作者论证、强化反方论证、找出决定性分歧，并给出明确判断。
- 无法取得全文时仍可推荐，但必须醒目标注“仅基于摘要评估（未取得全文）”。
- 同一论文永久只推荐一次。

排序有意排除引用量、下载量、社交热度和个人偏好历史。期刊或机构只负责提供准入信号，最终仍要判断具体论文的问题重要性、论证、证据和创新。

## 仓库结构

```text
data/seen.json                              永久去重记录
reports/YYYY/MM/YYYY-MM-DD[-NN].md          按日期保存的公开日报
skill/legal-paper-frontier/SKILL.md         平台中立的工作流
skill/legal-paper-frontier/references/      来源、筛选和报告规范
skill/legal-paper-frontier/scripts/         候选发现与归档脚本
tests/                                      标准库测试
```

## 安装 Skill

先克隆仓库。Codex 的 Windows PowerShell 安装方式：

```powershell
git clone https://github.com/XIaoyu7879/legal-paper-frontier.git
Set-Location legal-paper-frontier
New-Item -ItemType Junction `
  -Path "$env:USERPROFILE\.codex\skills\legal-paper-frontier" `
  -Target "$PWD\skill\legal-paper-frontier"
```

macOS 或 Linux：

```bash
git clone https://github.com/XIaoyu7879/legal-paper-frontier.git
cd legal-paper-frontier
ln -s "$(pwd)/skill/legal-paper-frontier" ~/.codex/skills/legal-paper-frontier
```

其他支持通用 `SKILL.md` 约定的 Agent，可以直接加载 `skill/legal-paper-frontier/SKILL.md`。

调用示例：

```text
请使用 $legal-paper-frontier 生成并归档今天的法学前沿论文日报。
```

本项目刻意采用“需要时调用”，不会安装定时任务。若要自动推送，Git 需要提前完成 GitHub 认证。

## 运行脚本

只需要 Python 3.10+，没有第三方运行依赖。

```powershell
# 初步发现候选；最终筛选仍必须实时核验并阅读。
py skill/legal-paper-frontier/scripts/collect_candidates.py `
  --repo-root . --days 14 --output tmp/candidates.json

# 校验 JSON 草稿、渲染日报、永久去重、提交并推送。
py skill/legal-paper-frontier/scripts/archive_report.py `
  tmp/digest.json --repo-root . --push

# 本地测试。
py -m unittest discover -s tests -v
```

可选环境变量：`OPENALEX_API_KEY` 用于提高 OpenAlex API 容量；`LEGAL_PAPER_FRONTIER_MAILTO` 会在 Crossref 请求中加入联系邮箱。

## 质量与访问边界

来源清单是可维护的起始集合，不是封闭正典。中文期刊从当前 CSSCI 周期开始筛选；英文来源覆盖领先综合性法学评论、成熟同行评审法学期刊，以及高质量专业或交叉学科刊物。SSRN 只用于发现前沿工作论文，不等于质量认证。

付费墙不当然排除论文。如果摘要本身足以支持谨慎评价，可以推荐，但报告必须显示 `仅基于摘要评估（未取得全文）`，并且不得推断摘要没有披露的方法、数据或结论。

## 许可证

[MIT](LICENSE)
