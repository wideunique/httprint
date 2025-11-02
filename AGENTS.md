# Repository Guidelines

## Project Structure & Module Organization
`httprint.py` 是核心 Tornado 应用，负责 HTTP 接口、任务队列和打印命令执行。公共常量与 helper 位于同一文件，修改前先确认是否已有相同行为，避免重复造轮子。运行时配置集中在仓库根目录的 `config.yaml`；复制 `config.example.yaml` 作为起点，通过 `HTTPRINT_CONFIG` 环境变量指向自定义路径以便本地与生产隔离。上传文件默认进入 `queue/`，归档副本写入 `archive/`，两者都会被 pytest fixture 清理，请不要手动混入测试数据或杂物。静态资源在 `dist/`（由历史构建产出），除非更新前端，否则不要动它；系统部署脚本位于 `systemd/`，证书样本放在 `ssl/`。所有自动化测试都在 `tests/` 下的 `test_*.py` 中，fixture 与辅助函数集中在同目录；若需要额外实验文件，请统一放入临时目录 `tmp/`，该目录默认被 `.gitignore` 覆盖，发布前务必清空。

## Build, Test, and Development Commands
推荐做法：`python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`，这样基础依赖和 pytest 一次装齐。只想拉起服务时，可执行 `pip install -r requirements.txt`。开发态启动命令为 `HTTPRINT_CONFIG=config.yaml ./httprint.py`，若要监听其他端口或者启用 HTTPS，可在配置文件中调整 `port`、`ssl_dir` 等字段；调试时将 `debug` 设为 true 获取更详细日志。快速自测使用 `pytest -q`；定位单个文件或测试时用 `pytest tests/test_auth.py -k token`，回归问题时建议加上 `--maxfail=1 --ff` 加速反馈。打印流程依赖 `lp` 和 `pdfinfo`，在缺失这些本地依赖时，HTTP 层仍可启动但会在打印阶段失败；想要模拟打印，可在配置里把 `print_cmd` 指向自定义脚本并断言参数。结束开发流程前，用 `find queue -type f -delete` 或自写脚本清扫遗留任务，保持工作目录干净。

## Coding Style & Naming Conventions
代码使用 Python 3，遵循 PEP 8，四空格缩进，逻辑分支保持显式。模块级常量用全大写下划线，函数和变量一律小写加下划线。新增 Tornado handler 时，类名采用驼峰，文件命名保持蛇形（例如 `upload_handler.py`）。导入顺序参考 `httprint.py`：标准库、第三方库、项目内模块，每组之间留一空行。日志统一走内置 `logging` 模块，不要 `print()`；异常要带上执行上下文，便于排查。仓库未绑定自动格式化工具，提交前请至少运行 `python -m py_compile httprint.py` 或对新文件执行 `python -m compileall <path>` 确认语法无误；有空可借助 `ruff` 或 `black --check` 自行校验，但不要把额外依赖写进 requirements。

## Testing Guidelines
测试框架为 `pytest`，遵循 `tests/test_<feature>.py` 的命名模式。新增功能先补测试，再写实现；测试案例描述要指明行为和期望，例如 `test_print_job_requires_code_when_enabled`。断言时优先验证外部行为（HTTP 状态、文件生成、命令参数），避免钉死内部实现细节。涉及文件系统的测试应使用 `tmp_path` 或 `monkeypatch` fixture 来隔离目录、伪造环境变量，确保不会污染真实 `queue/` 与 `archive/`。需要调用子进程时请用 `subprocess.run` 的 fake 或 monkeypatch，别让测试实际调用 `lp`。提交前务必执行一次完整的 `pytest -q`，并在 PR 描述中贴上结果；回归缺陷必须附带再现测试，确保未来不会重蹈覆辙。保持覆盖率不下降，新模块至少写一条集成测试验证 happy path。

## Commit & Pull Request Guidelines
历史提交消息略显随意，从现在开始统一使用祈使句的一行摘要（例如 `Tighten page limit validation`），第二段描述动机与风险。单个提交应保持可编译且测试通过；遇到跨模块修改，拆成逻辑独立的小步，方便回滚。Pull Request 至少包含：概述（做了什么、为什么）、测试结果（粘贴 `pytest -q` 或更细颗粒命令输出）、关联的问题编号、配置或部署变更的注意事项。如果改动影响打印命令、权限或网络入口，请额外写出回滚策略与手工验证步骤。涉及 UI 的改动必须附上截图或 GIF，证明流程可用。禁止提交本地构建产物、真实证书、队列残留文件，一旦误提交立刻用新提交修正，别想靠 `force-push` 隐瞒。

## Security & Configuration Tips
`config.yaml` 包含认证凭据与打印命令模板，部署时请复制到不受版本控制的路径并将权限设置为 600。HTTPS 证书存放于 `ssl/httprint_cert.pem` 与 `ssl/httprint_key.pem`，仓库仅允许占位或自签名样本，真实密钥务必放在外部秘密存储。若修改打印命令字符串，请在代码与 PR 中解释如何避免 shell 注入（例如使用参数列表或白名单校验）。启用 `ip_whitelist` 时记得覆盖本地网段，否则测试环境可能被意外拒绝。部署脚本应通过环境变量写入敏感配置，不要把密码硬编码进 YAML。最后，别忘了为所有敏感配置提供 sane 默认值；一旦引入新项，立即更新 `config.example.yaml` 和文档，避免部署时炸锅。
