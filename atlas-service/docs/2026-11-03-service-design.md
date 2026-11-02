# GitHub 开源星图服务设计与实现计划

目标：将已有 Top 1000 单文件目录扩展为 Top 2000，可在 macOS 本机持续运行，每 10800 秒更新一次，并可由 GitHub Actions 构建成 GitHub Pages 静态站。

## 方案
采用标准库 Python 采集/服务 + 无依赖 HTML/CSS/JavaScript 前端。相比只做 HTML，它能自动更新；相比托管数据库与服务端，它更容易免费发布到 Pages。本机服务只绑定 127.0.0.1:4173。沿用现有浅色深蓝紫色星图风格，不更改旧日报和旧交付文件。

## 数据口径
- Top 2000：GitHub 官方搜索 API 的公开非 fork 仓库，按累计 Star 排序，保留归档项目。递归拆分不重叠 Star 范围规避单查询最多 1000 条；遇到重复、缺失或不完整结果需重试/拒绝覆盖已有完整榜单。
- 每日/每周/每月趋势：从 GitHub Trending 的 daily/weekly/monthly 页面读取，保留官方顺序与页面给出的周期增长。其范围独立于 Top 2000，不声称全站 Star 增长绝对排名。
- 历史：每次完整采集存储时刻与仓库 Star，保留至少 35 天；初次启动不能捏造过去的增长。以后在最新数据中给出有足够历史的 1/7/30 天增长统计。
- 已有 1000 条中文简介作为按 fullName 匹配的人工覆盖表。新项目保留官方原始描述，人工补充中文；未来新入榜提供诚实的原始简介和类别，不能编造翻译。
- 单独趋势请求失败保留该周期旧数据和采集时间、错误状态；总体更新失败保留上一版静态站。错误无凭据内容。

## 文件与契约
所有工作位于 atlas-service/；根 .github/workflows/atlas-pages.yml 用于云构建。
- scripts/collect.py：Python 标准库，CLI --output data/latest.json，负责搜索分片、Trending HTML 解析、原子写入、历史、3 小时节流/锁。
- scripts/build.py：从 web/ 与 data/latest.json 生成 dist/ 静态站，注入 window.ATLAS_DATA，不拷贝历史或凭据。额外交付 deliverables/GitHub-Star-Top2000.html 可内嵌 CSS/JS。
- scripts/server.py：本机只读 HTTP 服务，/healthz 状态与更新状态；后台每 10800 秒调用采集+构建，启动后按最新采集时间判断是否到期；并发安全；优雅停止。启动时有 dist 就立即可用，首次无数据明确提示。
- scripts/manage.py：start/stop/status/install/uninstall/update CLI；macOS launchd 登录后常驻；可复用 Node/Python 现有安装；不保存个人 GitHub token 到前端或仓库。
- web/index.html, app.js, styles.css：Top 2000 及 category/rank/daily/weekly/monthly 导航、搜索、分类/语言、CSV、分页、来源和新鲜度；未知/陈旧/空/错误状态。
- data/editorial.json：{fullName: {category,summary}}；data/latest.json 发布数据；data/history/*.json 历史。

最新数据 schema（唯一共享契约）：
```json
{"schemaVersion":1,"generatedAt":"ISO UTC","topUpdatedAt":"ISO UTC","targetCount":2000,"source":"https://api.github.com/search/repositories","repositories":[{"rank":1,"name":"owner/repo","url":"https://github.com/owner/repo","stars":123,"language":"Python","archived":false,"category":"learn","summary":"中文或原始描述","original":"官方描述","summarySource":"editorial|original","growth":{"daily":null,"weekly":null,"monthly":null}}],"trending":{"daily":{"updatedAt":"ISO UTC","source":"https://github.com/trending?since=daily","status":"ok|stale|error","error":null,"repositories":[{"rank":1,"name":"owner/repo","url":"https://github.com/owner/repo","stars":1000,"periodStars":200,"language":"Python","category":"ai","summary":"描述","original":"原始描述","summarySource":"editorial|original"}]},"weekly":{},"monthly":{}},"status":{"state":"ok|partial|error","lastAttemptAt":"ISO UTC","lastSuccessAt":"ISO UTC or null","errors":[]},"history":{"oldestSnapshotAt":null,"snapshotCount":0}}
```
category ID 固定为 learn/lists/agent/ai/web/backend/dev/ops/apps/media/security/data。总数由数据推导，Top 2000 完整时才能发布更新。纯函数测试可用小型 fixture。

## 任务与验证
1. 采集：先写解析、分片边界、重复/不完整拒绝、增长缺历史、过期失败保留测试，再实现；实采完整 2000，趋势三个周期非空。
2. 界面：独立基于契约构建，测试恶意文本转义、筛选、分页、缺数据状态；浏览器验证桌面/390px/键盘和筛选导出。
3. 部署：先测试路径遍历防护、健康接口、任务互斥与节流，再实现本地服务和 launchd 管理；准备 Pages workflow（每 3 小时，避开整点）；不推送或创建公共仓库，用户仅要求可部署能力。
4. 集成：补齐新项目简介、构建、自测、实际安装并启动本地服务，确认 HTTP 与 launchd 状态；保留一份可离线打开的 HTML。

## 风险和运行条件
电脑睡眠/关机期间本机无法采集，唤醒后补采一次，不能保证实际整点执行。GitHub Actions 定时也可能延迟，免费 Pages 要使用公开仓库。无个人 token 时通过系统 gh 已有登录或匿名 API，云端使用工作流内置 token。GitHub Trending 页面结构变化要显示错误并保留旧快照，不能伪造空榜。
