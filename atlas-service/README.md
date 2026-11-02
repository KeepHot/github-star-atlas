# GitHub 开源星图

Python 3.9+ 标准库服务，无第三方依赖。目录路径含空格时请保留引号。从项目根目录运行：

```sh
cd "atlas-service"
python3 -m unittest discover -s tests
python3 scripts/manage.py update
python3 scripts/manage.py start
python3 scripts/manage.py status
```

浏览器打开 http://127.0.0.1:4173 。`/healthz` 返回就绪状态、榜单采集时间和更新结果，不返回凭据。服务仅绑定回环地址，只允许 GET/HEAD。首次无完整榜单时显示 404 提示；完整构建后自动可用。

```sh
python3 scripts/manage.py stop
python3 scripts/manage.py start
python3 scripts/manage.py install
python3 scripts/manage.py uninstall
```

`install` 仅限 macOS：先将白名单运行文件独立复制到 `~/Library/Application Support/GitHubStarAtlas/`，避免后台进程访问 Documents 时受 macOS 隐私限制；没有指回工作区的符号链接。复制范围仅为四个 Python 脚本、前端三文件、公开最新数据、历史及人工简介，不复制 token 或其他工作区文件。随后写入 `~/Library/LaunchAgents/local.github-star-atlas.plist` 并立即启动，之后每次登录自动运行、崩溃后重启。使用安装时 Python 的绝对路径，移动源项目不影响已安装服务；删除该 Python 后应重新安装。安装后更新的数据、日志和构建均位于独立安装目录，工作区数据不会同步变化。升级源码后再次执行 `install` 可更新运行文件：保留时间较新的完整榜单，并只补入缺少的历史文件，不覆盖安装目录已存在的同名快照。通过源项目或安装目录执行 `manage.py update`，只要存在已安装服务配置，就更新安装目录。`stop` 停止当前服务，已安装配置下次登录仍会启动；`uninstall` 删除登录服务。手动启动日志和进程标识保存在 `.runtime/`，忽略入库。安装后重启可执行 `stop`、`start`。

服务按已发布 `topUpdatedAt` 判断三小时是否到期，每五分钟检查一次。手动 `update` 强制采集；手动与定时工作共享文件锁，采集器也有独立锁。更新期间继续提供旧页面；失败保留旧版并约五分钟后重试。电脑睡眠、关机、离线期间不能采集，恢复运行后补采；并非精确定时保证。

`data/latest.json` 是公开最新数据，`data/history/` 保存至少 35 天 Star 快照；初次运行没有过去增长。`data/editorial.json` 为人工中文覆盖。只有完整 Top 2000 才能发布。构建仅复制公开 latest.json 和前端三文件，不复制历史、人工编辑源或凭据。`dist` 原子切换到 `.builds/` 中的新构建代际，保留最新三代以及一小时以内的代际，避免正在读取的请求受影响。源项目离线单文件输出到根目录 `deliverables/GitHub-Star-Top2000.html`；安装服务的输出位于 `~/Library/Application Support/deliverables/GitHub-Star-Top2000.html`。卸载保留安装目录数据，需要彻底删除时先卸载再手动移除安装目录。

## GitHub Pages

公开仓库已部署至 https://github.com/KeepHot/github-star-atlas ，Pages 使用 GitHub Actions 构建发布。免费 Pages 通常要求公开仓库，上传前检查仓库其他文件是否适合公开。

`.github/workflows/atlas-pages.yml` 每三小时的第 17 分钟执行，也可 Actions → GitHub Star Atlas Pages → Run workflow 手动运行。GitHub 定时可能延迟。工作流先测试，再用内置 `GITHUB_TOKEN` 采集和构建；成功后只提交公开最新数据和历史，再部署静态产物。并发组串行执行，避免多个定时/手动部署交错；任何采集、验证或推送失败均不部署，现有 Pages 保持可用。工作流按需声明 contents: write、pages: write、id-token: write；不需要修改仓库默认工作流权限，也无需个人 token。Pages 是静态托管，更新依赖 Actions，不会运行本机 Python 服务。

本机采集可使用现有系统认证或匿名访问；不把个人 token 写入前端、仓库或 launchd 配置。只有公开数据进入 Pages 产物。

## 发布包与操作步骤

根目录 `deliverables/GitHub-Star-Atlas-Pages.zip` 仅包含本服务的源码、测试、公开数据和工作流，解压后直接作为新仓库的根目录使用。它不包含个人凭据、本机运行状态或旧日报项目。

1. 新建 GitHub 公开仓库，把解压后的全部文件（包括 `.github/`）提交到默认分支。
2. 保留仓库默认工作流权限；发布工作流已声明保存历史与部署所需权限。
3. Settings → Pages → Build and deployment → Source 选择 **GitHub Actions**。
4. Actions → **GitHub Star Atlas Pages** → **Run workflow**；部署完成后打开 Deploy 步骤给出的 `https://用户名.github.io/仓库名/`。

以后由工作流每三小时刷新。Actions 请求使用 `--force`，避免调度延迟触发本机三小时节流而跳过本次采集。无需启用本机服务，也不需要提供个人 Token。

来源说明：[GitHub Pages 免费公开仓库与静态托管说明](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)、[Actions 定时触发及延迟限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)、[GitHub 仓库搜索规则](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories)、[每日官方趋势](https://github.com/trending?since=daily)。
