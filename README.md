# trending-spike-check

Answers one question about a GitHub Trending entry: **is this a one-day burst or a sustained trend?** — and says *abstain* instead of guessing when the snapshot cannot support the claim.

Why now: a repo at #1 on the daily list with 2,776 stars in one day looks identical to a repo that has been compounding for a week. The daily, weekly and monthly lists are three independent measurements of the same population, and nothing in the dataset compares them.

Upstream: https://github.com/linmoxi33/github-trending-dataset

## What the upstream is, and what is missing

`linmoxi33/github-trending-dataset` is a daily snapshot of the three GitHub Trending lists. Each row carries `stars_period` (stars gained *within that list's window*: 1 day, 7 days, 30 days). It is a faithful capture and makes no claim about which entries are spikes.

The gap is that the three windows are never reconciled: a repo can appear on `daily` with a number that is impossible to sustain, and the dataset cannot tell you whether that is a burst, a data artefact, or a genuine week-long run. Cross-window reconciliation is also fragile — on the 2026-11-12 snapshot only **1 of 10** daily repos also appears on the weekly list, so a naive `daily / weekly` ratio is undefined for 90% of entries. That is the fact this tool is built around: it must fall back or abstain, never fill the gap with a guess.

## What this tool does

For every repo that appeared on any daily list in the given snapshots, it computes a **concentration ratio** and a **persistence count**:

- `ratio = daily_stars / (weekly_stars / 7)` — how concentrated this repo's gain is in one day, relative to its own seven-day average.
- If the repo is not on the latest weekly list, it falls back to a **self-baseline**: `daily_stars / median(previous daily values)`.
- If neither is available, it returns **ABSTAIN** — no ratio, no verdict.

Verdicts: `SPIKE` (ratio ≥ 2.0), `CONSISTENT` (0.5 ≤ ratio < 2.0), `UNDERWEIGHT` (ratio < 0.5), `ABSTAIN`.

Every row also reports `days_on_daily` / `snapshots` (how many of the supplied snapshots the repo was on the daily list), `first_seen`, `last_seen` and `on_daily_today`, so persistence is a count you can check, not a probability.

## What it does not do

- It is not a star-growth forecast, and it does not rank repos by "potential". It compares two numbers the dataset already recorded.
- With fewer than two snapshots, the self-baseline is unavailable and those rows abstain by construction.
- It does not deduplicate renamed repos or forks; it matches on the exact `repo` string.

## Install

Python 3.9+, no third-party packages.

```bash
git clone git@github-linmoxi33:linmoxi33/trending-spike-check.git
cd trending-spike-check
python3 --version   # 3.9+
```

## Usage

```bash
python3 bin/trending-spike-check examples/in/2026-11-10.json examples/in/2026-11-11.json
```

```
snapshots: 2 (2026-11-10 .. 2026-11-11)
latest: 2026-11-11 | repos on daily: 5
verdicts: 1 SPIKE, 1 CONSISTENT, 1 UNDERWEIGHT, 2 ABSTAIN

repo                                            daily   weekly   ratio verdict      days  basis
acme/spike                                        700     2100    2.33 SPIKE        2/2   weekly
acme/steady                                       300     2100    1.00 CONSISTENT   2/2   weekly
acme/fade                                         400     9000    0.31 UNDERWEIGHT  2/2   weekly
acme/onehit                                        50        -       - ABSTAIN      1/2   -
...
```

`--json` emits the same report; `examples/out/report.json` is the committed expected output and a test asserts equality.

```bash
python3 bin/trending-spike-check examples/in/*.json --json | python3 -m json.tool | head
```

### Options and exit codes

| Flag | Meaning |
| --- | --- |
| `--json` | emit the report as JSON |
| `--fail-on-spike` | exit 1 when at least one `SPIKE` is found |

| Code | Meaning |
| --- | --- |
| `0` | analysis ran (and, with `--fail-on-spike`, no spike) |
| `1` | `--fail-on-spike` was given and at least one spike was found |
| `2` | usage error, unreadable file, invalid JSON, or a malformed snapshot |

## Real-data run (measured, not estimated)

Command, against the five live snapshots `data/2026-11-08.json … 2026-11-12.json`:

```bash
python3 bin/trending-spike-check 2026-11-08.json 2026-11-09.json 2026-11-10.json 2026-11-11.json 2026-11-12.json
```

Observed output:

```
snapshots: 5 (2026-11-08 .. 2026-11-12)
latest: 2026-11-12 | repos on daily: 28
verdicts: 5 SPIKE, 12 CONSISTENT, 0 UNDERWEIGHT, 11 ABSTAIN
```

| repo | daily | weekly | ratio | verdict | days |
| --- | --- | --- | --- | --- | --- |
| we-promise/sure | 1078 | — | 6.78 | SPIKE (self-baseline) | 2/5 |
| zed-industries/zed | 1114 | 2310 | 3.38 | SPIKE | 1/5 |
| dsx-ai-factory/nvke | 345 | — | 2.80 | SPIKE (self-baseline) | 2/5 |
| google-deepmind/mujoco | 456 | 1535 | 2.08 | SPIKE | 3/5 |
| anthropics/skills | 1679 | 5738 | 2.05 | SPIKE | 4/5 |
| vercel-labs/agent-browser | 708 | 4183 | 1.18 | CONSISTENT | 5/5 |

The 11 abstentions are entries seen on exactly one day with no weekly row — the snapshot cannot say whether they are a spike, so the tool does not.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

18 stdlib tests: ratio math and both boundaries, weekly-vs-self-baseline precedence, abstention, persistence counting, sorting, duplicate-date rejection, CLI exit codes 0/1/2, and equality with the committed expected report.

## Limits

- Five snapshots is a small sample. `self-baseline(1 prior days)` is a single prior observation — enough to flag a burst, not enough to call it a trend.
- `stars_period` is the dataset's own field; if the upstream capture is wrong, this tool inherits the error.
- The weekly list contains ~13–19 repos and the daily list ~9–15, so cross-window coverage is structurally low; the reported abstention rate is a property of the dataset, not a bug.
- Nothing here is a forecast. A SPIKE today can be a sustained trend next week.

## 本轮创新

把「日榜数字」与「周榜数字」当成同一个量的两个独立测量，**只在两个窗口都覆盖时**才给比值，否则显式 abstain 并给出 abstain 原因（single-day / no weekly row）。用 5 天真快照量化出一个可复核的事实：2026-11-12 的 10 个日榜项目里只有 1 个同时出现在周榜，所以跨窗口比值对 90% 条目不可定义——这是「先证明指标不可用，再决定用哪个基线」的顺序，台账里没有同类先例。

## 与同类项目的差异

`gh search repos "github trending"` 命中若干成熟项目：`vitalets/github-trending-repos`（3042★，按语言把榜单
发成 GitHub issue 供订阅）、`bonfy/github-trending`（1267★，每日抓取入库）、`huchenme/github-trending-api`（839★，
提供榜单 API）。它们的共同点是**采集/分发**榜单；本项目的输入就是采集结果，只做**跨窗口对账**：

1. 它们回答“今天谁上榜”，本项目回答“这个上榜数字是不是一天爆发”，并给出比值与基线来源。
2. 本项目在无法判定时**显式 abstain**，不把缺失的周榜数据当成 0 或 1。
3. 零依赖、离线、可复现：同一组快照永远得到同一份报告（有回归测试逐字段比对 `examples/out/report.json`）。

## License

MIT. See `LICENSE`.
