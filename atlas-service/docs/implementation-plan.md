# 开源星图 Top 2000 Implementation Plan

> 执行：按领域隔离的子任务实现，父任务负责数据中文整理、集成和实际部署。

**Goal:** 本机持续服务 Top 2000 + GitHub 日/周/月趋势，每三小时更新，同源静态发布 GitHub Pages。
**Architecture:** Python 标准库采集、后台服务和构建，原生前端；公开数据存放 data/latest.json 和历史快照。
**Spec:** [服务设计](2026-11-03-service-design.md)

## Global Constraints
- 沿用已有浅色深蓝紫色界面；保留旧交付和旧日报。
- 本地仅 127.0.0.1:4173；更新周期 10800 秒；不在前端保存凭据。
- 完整唯一 2000 条才能覆盖全榜；趋势来源失败保留旧数据并标记。
- 趋势使用 GitHub Trending 官方各周期原始顺序，不能冒充全站增长排名。
- 历史增量必须来自真实采集时刻；没有历史返回 null。

## Review Focus
- 搜索 API 1000 条上限与相同 Star 边界：分片无重叠，ID 去重与数量检查。
- 网络失败：完整榜单/静态页面不得被半成品覆盖；过期来源应明确。
- 未信任远程描述：转义 HTML 和内联 JSON，拒绝可执行链接。
- 重启/睡眠/并发触发：判断是否到期，唤醒补采，互斥更新，保留日志。
- Pages 子路径、缺 token 和历史保留：相对资源路径，使用内置 token，不发布凭据。

## Tasks
- [x] collector：tests/test_collect.py 先失败再实现 scripts/collect.py，实测原始分页与 Trending。
- [x] frontend：web/ 三文件与纯函数测试，遵守数据 schema，分类/总榜/三周期/筛选/分页/CSV/来源状态。
- [x] deployment：tests/test_build.py/test_server.py 先失败再实现构建/只读 HTTP/后台调度/manage/Pages workflow/README。
- [x] integration：补充编辑描述，实际采集2000+趋势、浏览器与单文件检查、安装launchd并验证。
- [x] review：独立最终评审，修复阻断项后重测。

## 执行记录
2026-11-03：原仓库18项测试通过。新增服务隔离于atlas-service/，避免更改旧日报。没有Git远端；仅准备Pages发布能力，不创建或公开用户仓库。


## 完成证据
- 实际完整网络采集：2000个唯一仓库，Star降序，全2000条中文编辑简介；官方趋势每日15、每周16、每月18条。
- 测试：27项Python服务测试、7项前端测试、18项原项目测试通过；独立评审发现问题已修复。
- 浏览器：通过真实127.0.0.1:4173验证搜索、分类、语言、分页、CSV2000条、三周期切换、390px无横向溢出、无JS错误。
- 本机部署：已安装用户launchd服务local.github-star-atlas，运行副本在~/Library/Application Support/GitHubStarAtlas，healthz ready=true。
- Pages：工作流和公开部署包已准备，YAML可解析、ZIP校验通过；尚未创建或发布远程仓库。
- macOS实际限制：Documents中的源码无法由launchd读取，因此安装白名单独立副本；安装路径和重装更新方式已记录README。
