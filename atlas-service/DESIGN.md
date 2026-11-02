# GitHub 开源星图 — design context

## Product and audience
Chinese-speaking developers exploring Top 2000 cumulative Star repositories and independent official GitHub Trending daily/weekly/monthly snapshots. A read-only discovery dashboard, not a marketing page. Primary job: find a project and understand its ranking source. Evidence: `docs/2026-11-03-service-design.md`; visual reference: `../deliverables/GitHub-Star-Top1000.html`.

## Visual direction
Retain the existing pale blue atlas identity. A quiet navy workspace, purple active navigation, editorial cards, tabular ranking numbers and a schematic orbital star map form a coherent discovery instrument. The star map is explicitly labelled 示意星图; it does not encode measured repository relationships. It is the single signature visual, with no decorative motion. Avoid introducing gradient statistic tiles or a promotional hero that crowds the discovery controls.

Desktop: 236px sidebar / flexible main; hero copy and star-map; four snapshot facts; source status; search and controls; 36 project cards; pagination. Below 780px, sidebar becomes two horizontal, scrollable native button navigation rows; map is hidden, facts become two columns; below 480px cards become one column. Ranking view becomes a compact responsive list. Outer document owns vertical scrolling.

## Canonical tokens and runtime ownership
`web/styles.css` `:root` is the single runtime source. These existing values are preserved and normative:

| Token | Value | Role |
|---|---|---|
| --bg | #f5f7fb | pale blue application canvas |
| --paper | #ffffff | cards and inputs |
| --ink | #172744 | navy typography |
| --muted | #63718a | secondary information |
| --line | #e2e7f0 | borders |
| --accent | #6152ce | purple focus and action |
| --wash | #eeecfc | active navigation and snapshot info |
| --gold | #986722 | star symbol |
| --radius | 16px | large panel radius |

CSS consumes these variables directly; there is no parallel theme adapter. Warning surface is #fbf3e4 with #705320 text. Scrollbars inherit the document-wide standards baseline (#aeb8cc / --bg); WebKit hover #8e9bb4 and active #63718a; forced colors defer to system colors. No hidden scrollbars.

Body uses system sans (-apple-system, BlinkMacSystemFont, Segoe UI, PingFang SC, Microsoft YaHei); data and small captions use SFMono-Regular / Consolas / monospace. No external fonts, image downloads or icon library. Display title 30–44px; project titles 17px; utility text 10–12px retains existing density. Line height 1.65, project copy 1.85.

## Canonical UI map
Navigation owner: shared `render()` and `data-view` handlers in `web/app.js`; layout owner: `data-layout`; category owner: `#categories`; search owner: `#search` with explicit clear; selection owner: native `select` (OS popup intentionally accepted); feedback owner: persistent `#status` and `#notice`; pagination owner: `paginate()` plus common previous/next controls; exports owner: `csv()`; description/link safety owner: `esc()` and `safeURL()`. No existing app component system exists to duplicate. No forms, mutation, dialog, permissions or payments apply.

## Verification record
2026-11-03: pure function test suite 7/7 passes, covering filtering/search, ranking, bounded pagination, source scope, escaping/link safety, CSV and freshness. Parent integrator owns built-site browser QA at desktop/390px, keyboard, native select popup, missing/stale/error state and standalone delivery. Static skill audit is supporting evidence, not runtime verification. No Japanese locale or Japan-market flows are in scope.

Static premium audit: `/tmp/atlas-frontend-audit.json` contains 12 findings: native select ownership is explicitly documented above but the audit requires separate manifest metadata; 11 literal buttons are flagged because the static detector recognizes only inline onclick syntax, while this app registers real handlers in app.js. All 11 have concrete handlers (4 view, 2 layout, export, clear, reset, previous, next). No inline no-op handlers were introduced to satisfy the detector. The genuine empty-anchor and missing scrollbar-width issues were corrected. Syntax check `node --check web/app.js` passes.
