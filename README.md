# codex-remote-bridge

在钉钉里使用一个固定的 Codex 总助理：查询本机任务、了解结果、向指定任务安排工作，并接收完成通知。每位用户在自己的电脑、OS 账号和 Codex Home 下运行；不需要公网 IP、云中转或开发者的机器人凭据。

> **总助理验收版本，尚未正式发布。** Windows 已通过真实钉钉任务查询、总助理向旧任务派发指令及完成通知，用户确认收到了汇总和完成回复；Desktop 上下文续接及安全测试库写文件也已验证。Windows/macOS × Python 3.10/3.14 CI 已全部通过；macOS 和部分安全真机测试尚未完成。Desktop 仍持有 writer 的任务会被拒绝，即使上一轮已结束；不能承诺“所有任务随时接管”。[实际验证记录](docs/VALIDATION.md)列出了证据和限制。

```text
钉钉私聊 → Stream → Python Bridge → 本机 codex app-server（stdio）
        → 持久的“钉钉机器人”任务（理解、查询）
        → 明确授权后：已有任务 thread/resume → turn/start → 钉钉完成通知
```

## Windows 安装

需要 Python 3.10+、Git，以及已经登录且正常工作的本机 Codex。使用与 Desktop 相同的 Windows 账号，不能把原生 Windows 与 WSL 的 Codex 用户目录混为一谈。

```powershell
git clone https://github.com/xuqiang97/codex-remote-bridge.git
cd codex-remote-bridge
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

这些命令适用于实现提交发布之后；如果检出的版本只有设计文档，先确认实现已推送。

填写自己的值：

```dotenv
DINGTALK_CLIENT_ID=your-client-id
DINGTALK_CLIENT_SECRET=your-client-secret
DINGTALK_ALLOWED_USER_IDS=your-enterprise-userid
DINGTALK_ALLOWED_CONVERSATION_IDS=
CODEX_COMMAND=codex
CODEX_HOME=
CODEX_ALLOWED_ROOTS=["C:/work/project-a","D:/work/project-b"]
CODEX_REMOTE_SANDBOX=workspaceWrite
CODEX_REMOTE_APPROVAL_POLICY=never
BRIDGE_STATE_PATH=.data/bridge.db
BRIDGE_MAX_INPUT_CHARS=4000
BRIDGE_MAX_OUTPUT_CHARS=3000
```

- `.env` 固定从 `bridge.py` 所在目录读取，系统环境变量优先，不执行变量插值或文件中的命令。
- 用户/会话 ID 用英文逗号分隔，用户白名单不能为空，群聊始终拒绝。
- 根目录必须是 JSON 数组，Windows 推荐正斜杠。只开放需要远程工作的项目及其子目录，不要填整个用户目录或磁盘。
- `CODEX_HOME` 留空继承默认值，显式配置时必须与 Desktop 一致。
- `CODEX_COMMAND` 是原生可执行文件名或绝对路径，不是带参数的命令行。运行 `Get-Command codex` 查找；如果得到 `.cmd`/`.ps1`，请改填原生 `codex.exe` 路径，不使用 shell 绕过。
- 凭据、用户 ID 和个人路径只放本地配置，不放 Git 或发布包。限制 `.env`、`.data` 权限，仅让当前 OS 用户访问。

检查并启动：

```powershell
.\.venv\Scripts\python.exe bridge.py --check
.\.venv\Scripts\python.exe bridge.py
```

`--check` 不联网，不启动 Codex。看到 `DingTalk Stream connected.` 后开始私聊测试。电脑需保持开机联网，首次验收保持终端可见。Ctrl+C 停止：只请求中断本 Bridge 启动的活动 Turn，再关闭子进程。V1 不安装开机服务。

## macOS 安装

```sh
git clone https://github.com/xuqiang97/codex-remote-bridge.git
cd codex-remote-bridge
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`，例如 `CODEX_ALLOWED_ROOTS=["/Users/you/work/project-a"]`，再执行 `.venv/bin/python bridge.py --check` 和 `.venv/bin/python bridge.py`。使用当前用户，不使用 sudo。macOS 真机验收仍待完成。

## 钉钉配置

1. 在[开发者后台](https://open-dev.dingtalk.com/)创建企业内部应用，添加并启用机器人能力。
2. 选择 **Stream 模式**，填写机器人名称等必填信息，发布机器人与应用版本，确保应用可见范围包含测试账号。
3. 将 Client ID、Client Secret 填入本机 `.env`。一台 Bridge 使用一个独立机器人身份，不要在多台电脑同时使用同一机器人。
4. 由通讯录管理员在[企业管理后台](https://oa.dingtalk.com/)的通讯录 → 成员管理查看自己的员工 **UserID**，填入白名单。它不是手机号、工号、昵称或钉钉号。
5. 钉钉客户端顶部搜索机器人名称，切换“功能”结果，进入单聊。搜不到时检查所属组织、发布状态及可见范围。[官方指引](https://opensource.dingtalk.com/developerpedia/docs/explore/tutorials/stream/bot/go/test-bot/)
6. 启动 Bridge，先发送 `/help` 验证收发，再做安全仓库测试。无需公网回调地址或入站端口。

需要在钉钉应用权限中开通机器人发送单聊消息的权限并发布新版本。回复和长任务通知使用官方机器人主动单聊接口，仅发送给当前已授权发起人，不提供群发。接口失败或结果未知时，不自动重试可能已经执行的工作。

## 直接和总助理聊天

第一次普通消息会在第一个白名单项目中创建名为“钉钉机器人”的任务，之后一直复用，不需要先 `/use`。SQLite 保存会话对应关系，Codex 保存对话上下文。

例如：

- “今天主要有哪些任务？”
- “刚刚 XXX 任务的结果是什么？”
- “请在「完整任务名」任务中执行：检查测试并报告结果。”

总助理先读取允许项目的任务目录及近期最终回复。明确派发才会启动目标任务，并在其完成时返回带任务名的通知。任务名含糊、重名、用户只询问可行性时，会请你明确，不自动选择或执行。当前支持明确命名的自然语言派发；代词、多任务批量派发和复杂隐含意图尚不支持。

目录最多 200 个允许任务；默认取最近 12 个任务各 3 轮的有限最终结果，可额外读取指定任务。它不是完整的全天活动审计；未知状态会说明。总助理每次最多读取补充信息 3 轮，每轮等待 5 分钟。

## 辅助命令

```text
/help          命令说明
/threads       刷新允许目录中的任务列表，每页 10 条
/threads 2     翻页，全局序号保持一致
/use 3         保留旧版任务选择，不改变普通聊天的总助理入口
/current       查看固定总助理
/unbind        解除绑定，不中断、不删除任务
/stop          只停止本会话通过本 Bridge 启动并持有的活动 Turn
```

列表五分钟过期，重新 `/threads` 即可。普通文字始终进入总助理；回复开始状态与最终结果，不逐 token 刷屏。忙碌时拒绝，不排队、不自动 steer。最多扫描 10,000 条记录，超出会拒绝，避免产生不完整的可选择列表。

首次验收在安全仓库的 Desktop 任务里完成无风险对话，再让钉钉总助理查询它，并明确派发一个无风险跟进。确认正确后再发工作指令。云任务和未授权目录仍不支持；固定 SSH 主机可按下面的显式配置接入。

### Desktop writer 限制

`thread/read` 的 `notLoaded` 不证明 Desktop 已释放任务。Bridge 必须通过 `thread/resume` 获取服务端 writer；遇到 `already has an active writer` 拒绝执行。

上一轮完成不等于 writer 释放。释放时机受 Codex 版本和客户端生命周期影响，目前没有经过本项目验证、能立即释放其他客户端 writer 的公开接口。不要改锁、rollout 或数据库，不强杀 Desktop，不开启 Full Access 绕过。

Bridge 使用长生命周期 App Server，也可能持有恢复过的任务直到停止。若 Desktop 报占用，请先 Ctrl+C 停止 Bridge；`/unbind` 不释放 writer。[Decision 026](docs/DECISIONS.md)

## 安全和故障处理

- 默认拒绝未知用户及群聊；可进一步限制私聊会话 ID。
- 每次绑定和启动重新检查真实目录，拒绝相对路径和符号链接越界。
- 固定 `never`，总助理 read-only，目标任务 workspace-write、命令网络禁用；不提供 Full Access、通用 RPC、shell/exec、任意 cwd、远程审批或删除任务接口。
- 服务端审批全部拒绝。审批、动态工具或未知服务端请求会关闭本 Bridge 的 App Server，要求本机处理，可能同时中断本 Bridge 的其他 Turn。
- SQLite 存绑定、总助理对应关系、派发 IDs/状态及去重，不存正文。去重保留七天，最多 100,000 条；容量耗尽时拒绝新消息。窗口之外的历史重放不受保证。
- 同一 state 文件只允许一个实例，不要用不同 state 文件绕过单机器人单主机限制。
- 断连或超时后结果可能未知，不自动重试。请求超时关闭子进程；Turn 最多等待 15 分钟。
- 最终文字限制长度，遮盖已知凭据、常见 token 和绝对路径。脱敏不是任意敏感信息的 DLP 保证，高敏感项目不要开放。
- 不记录消息正文、助手正文、SDK 原始日志、审批载荷或 App Server stderr。凭据不进入 SQLite。

重启会保留总助理、绑定和去重；正在运行的派发标为结果未知，不重放、不自动接管，也不会补发停机期间的通知。启动后可以询问目标任务的最新结果。首次创建总助理请求结果未知时需本机核实，不自动创建第二个。

无任务列表：检查根目录、相同 OS 用户/Codex Home。机器人不回复：检查 UserID、私聊、可见范围、Stream 连接。Codex 连接失败：在本机验证登录和可执行文件。重启后无法 `/stop` 原 Turn：这是所有权安全边界。

## 测试与结构

```sh
python -m unittest discover -s tests -v
python -m compileall -q bridge.py codex_bridge channels tests
git diff --check
```

测试使用假的协议进程和通道，不调用真实 Codex/钉钉，不运行 shell 或修改真实任务存储。禁止外部网络，仅允许 Windows asyncio 内部 socketpair 所需的 loopback。Windows/macOS × Python 3.10/3.14 四组 CI 已实际运行通过，记录见 [CI 验证](docs/VALIDATION.md#gate-c--public-ci)。CI 不代替真实钉钉和 Desktop 验收。

`codex_bridge/app_server.py`：异步协议；`router.py`：指令与所有权；`coordinator.py`：持久总助理、任务查询与派发；`security.py`：目录与输出；`state.py`：SQLite；`config.py`：本地配置；`channels/dingtalk.py`：Stream。

参考：[官方 App Server](https://learn.chatgpt.com/docs/app-server)、[官方 DingTalk Python SDK](https://github.com/open-dingtalk/dingtalk-stream-sdk-python)、[安全模型](docs/SECURITY.md)、[验证记录](docs/VALIDATION.md)。

MIT License.

## 可选：访问固定 SSH 主机的任务

在本机 `.env` 配置 `CODEX_SSH_REMOTES`（JSON 数组），每项包含 `alias`、
`host`、`command`、`home`、`roots`。示例见 `.env.example`；每位用户填写自己的
SSH 配置别名、Codex 可执行路径、相同用户的 Codex Home 和项目目录。
需要本机 OpenSSH、远端 Python 3/Codex，以及已验证的 SSH 主机密钥和非交互登录。

仍只有本机一份钉钉 Stream 连接。Bridge 通过 SSH stdio 启动远端 app-server，
不公开端口，不复制钉钉凭据，不安装远端机器人服务。远端根目录在远端解析并检查。
`/threads` 显示主机标签；正常聊天可直接询问远端项目或用准确任务名派发。
同名任务不猜测，其他客户端占用时拒绝执行。远端断连时目录查询会明确失败，
不会把不完整结果说成“所有任务”。启用前请完成文档中的安全环境验证。
