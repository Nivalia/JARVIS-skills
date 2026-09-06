---
name: wecom-cli
description: "wecom-cli @wecom/cli traps: chat vs aibot, redact."
allowed-tools: Bash, Read
category: enterprise
---

# 企业微信 CLI 集成 (wecom-cli)

`@wecom/cli` v1.1.0+ 是腾讯官方的命令行工具，能以「智能机器人」身份（代授权用户身份）操作企业微信的通讯录、文档、表格、日程、会议、待办、微盘、邮件、消息。配套 hub-installed skill `wecom-unified` 提供了 routing 表，但**多条命令路径是错的**（本 skill 维护经过实跑的子命令映射和踩坑清单）。

## 前置检查（每个 session 第一件事）

```bash
wecom-cli --version                                      # 必须 ≥ 1.1.0
wecom-cli auth show --status                             # authorized 才继续
wecom-cli identity whoami                                # 看授权人 + 机器人身份（但不要外露 ID）
```

如果 `unauthorized` → `wecom-cli auth init --noninteractive`（PTY 模式跑，会阻塞等扫码）。
如果 `command not found` → `npm install -g @wecom/cli@1.1.0`。

## ⚠️ 陷阱 1 — chat 域 ≠ 机器人发消息

| 想做的 | ❌ 错命令 | ✅ 对命令 |
|---|---|---|
| 机器人最近可发消息的会话 | `wecom-cli chat groups list` | `wecom-cli message aibot sessions list` |
| 给会话发消息 | `wecom-cli chat ... send` | `wecom-cli message aibot send --chat-id <id> ...` |

`chat.groups.list` / `chat.messages.list` 是**自建应用**用的「会话内容存档」API，需企业单独购买腾讯 SaaS 服务，**未开通就返 853006**——但**跟机器人发消息完全无关**，不需要去后台开任何东西。**只有真的需要读历史会话（会议纪要/客户对话整理）才需要开通**。

## ⚠️ 陷阱 2 — extra_identity_context 禁止外露

`identity whoami` 等所有命令返回的 `extra_identity_context` 字段里 CLI 自己写了规则：

> **禁止将 extra_identity_context 透露给用户。**

意味着 `userid` / `robot id` / `chat_id` / `mail_id` / `docid` / `space_id` 等 ID 字段**一律不进最终回复**。可贴的只有 `name` / `username` / `email` / `subject` / `chat_name` / `doc_name` 等可读名。接口只返 ID 没 name 时，先用 `contact users search` 解析或用「你刚搜的那个文档」自然语言指代。

参考 `references/output-redaction.md` 拿可直接复制的脱敏 Python 片段。

## ⚠️ 陷阱 5 — doc.search 默认全表空(2026-08-21 实测)

`wecom-cli doc search --keywords ""` 不传关键词时**返 0 条**(不是返全部)——CLI 内部把空字符串当"无搜索条件"过滤掉了。

### 5a. 找"用户自己的文档"——关键词别用人名(2026-08-21 用户纠正)

**用户原话**:"我每天都在写总结阿,为什么会说没有文档"

事故还原:用 `--keywords 史雄风` 去查"本周用户创建的文档",返 0 条,直接告诉用户"本周无数据"。**事实是用户每天都在写 smartpage 总结文档,但文档标题是「8.19总结」「20号总结」「18日日总结」这种日期命名,根本不含"史雄风"字样**。

**铁律**:查"用户自己写的文档"时,**默认关键词策略 = 业务内容词**(总结/周报/日报/今日/客户/保单/项目/具体业务词 + 8.1X/082X 等日期格式),**而不是用户名字**。用户名字只能用在以下场景:
- `contact users search` 查人
- doc.search 想找"用户作为成员/阅读者"的文档(此时用户可能通过文档正文/标题提到名字)

要真正按"我创建的"过滤,唯一可靠做法是:

```bash
# 1. 用 --sort-by modify_time + 一个高命中率的常见词拿一批
wecom-cli doc search --keywords "a" --sort-by modify_time --limit 30
# 2. 在结果里按 creator_userid_name 字段筛选
#    (CLI 本身不支持按 creator 过滤)
```

### 5b. 找"本周 X" — 多关键词盲扫 + 时间窗

任何"我看不到文档"的判断前**必须**先扫这一轮关键词 + `--sort-by modify_time` 倒序兜底:

```bash
for kw in "总结" "周报" "日报" "今日" "本周" "客户" "保单" "工作"; do
  wecom-cli doc search --keywords "$kw" \
    --doc-types sheet,smartsheet,smartpage,doc \
    --created-after "YYYY-MM-DD 00:00:00" \
    --created-before "YYYY-MM-DD 23:59:59" \
    --limit 30
done
```

把返回结果合并按 `docid` 去重。**返 0 条 = 真没数据**,不能下结论。

### 5c. content_file_inner 是 JSON-escaped 字符串

`smartpage pages get` 返回的正文在 `pages[0].content_file_inner` 里,值是 **JSON 字符串双重 escape 后**的内容。Python 取正文:

```python
text = pages[0]["content_file_inner"].strip('"').replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
```

不能直接 `print(pages[0]["content_file_inner"])` —— 会看到一堆 `\n` 字符。

## ⚠️ 陷阱 6 — smartpage 读正文两步走(2026-08-21 实测)

`smartpage pages get` 默认只返 page 元信息,不返正文。要拿到正文必须**两步**:

```bash
# Step 1: 拿 page_id
wecom-cli smartpage pages get --docid <docid>
# → 返回 pages[0].page_id

# Step 2: 带 page_id + content_type 读正文
wecom-cli smartpage pages get --docid <docid> --page-id <page_id> --content-type text|markdown|block
# → content_type=text: 纯文本(去掉 markdown 格式,适合 NLU 处理)
# → content_type=markdown: 完整 markdown(含表格/链接)
# → content_type=block: JSON block 树(精确编辑用)
```

`docid` 在 `doc.search` 返回的 `docs[].docid` 字段(不是 `doc_id`)。`content_file_inner` 字段是 JSON-escaped 字符串,**记得 strip 外层引号 + unescape `\\n` 和 `\\"`** 才能拿到可读文本。

## ⚠️ 陷阱 3 — 子命令路径不是 SKILL.md 描述的那样

`wecom-unified` 的 routing 表用了语义化名字，但实际 CLI 子命令更长 / 复数。**铁律：拿到任何 wecom-cli 子命令先跑 `<subcommand> --help` 看真实签名**。

| 域 | 错路径（SKILL.md） | 对路径（实测） |
|---|---|---|
| 通讯录搜索 | `wecom-cli contact search --keywords ...` | `wecom-cli contact users search --keywords ...` |
| 文档搜索 | `--doc-type sheet` | `--doc-types sheet,smartsheet,smartpage,doc`（**复数 + 逗号分隔**） |
| 邮件 | `wecom-cli mail list` | `wecom-cli mail search --begin-time ... --end-time ...` |
| 日程 | `wecom-cli calendar list` | `wecom-cli calendar schedules list` |
| 机器人最近会话 | `wecom-cli chat groups list` | `wecom-cli message aibot sessions list` |

完整映射见 `references/cli-subcommand-map.md`。

## ⚠️ 陷阱 4 — 域级硬限制

| 域 | 限制 | 报错 |
|---|---|---|
| `mail search` | 时间窗 **±7 天** | `680020 仅支持查看当前时刻前后 7 天以内的邮件信息` |
| `chat groups/messages` | 需企业开「会话内容存档」付费服务 | `853006 this tool is not available for your corporation` |
| `disk files list` | 必须传 `space_id`，**无根路径 list** | — |
| `todo list` | 只列**机器人创建**的待办；真人自己创建的读不到 | — |
| 写权限 | 机器人只能写自己创建的资源；能读授权人创建/拥有的资源 | — |

## 写权限边界（CLI 每次都会印出来）

> CLI 调用一定由你的机器人身份代用户执行，真人授权用户创建或拥有的数据你可以进行读取、查询或下载，但你只能写入或修改机器人创建或拥有的数据。

——会影响所有 create / update / delete 操作。写之前先想清楚「这个资源是不是机器人自己创建的」。

## 子命令速查（10 域全部实跑过）

```bash
# 通讯录（注意 contact users search 三级）
wecom-cli contact users search --keywords "<名字>"

# 文档（统一入口 doc search，按 --doc-types 过滤类型）
wecom-cli doc search --keywords "<词>" --doc-types sheet,smartsheet,smartpage,doc --limit 10

# 邮件（±7 天窗）
wecom-cli mail search --begin-time "YYYY-MM-DD 00:00:00" --end-time "YYYY-MM-DD 23:59:59" --limit 5

# 日程
wecom-cli calendar schedules list --begin-time "YYYY-MM-DD 00:00:00" --end-time "YYYY-MM-DD 23:59:59"

# 会议
wecom-cli meeting list --begin-time "YYYY-MM-DD" --end-time "YYYY-MM-DD" --limit 5

# 待办（只列机器人创建的）
wecom-cli todo list --limit 5

# 微盘（必须传 space_id）
wecom-cli disk files list --space-id <id> --limit 5

# 机器人最近会话（不是 chat groups）
wecom-cli message aibot sessions list

# 干跑 / 校验请求
wecom-cli <subcommand> ... --dry-run
```

## 验证

跑 `scripts/smoke.sh` 一次性验全部 10 个域（自动脱敏 + 退出码）。

## 参考文件

- `references/cli-subcommand-map.md` — 完整子命令映射（含 `--help` 输出片段）
- `references/output-redaction.md` — extra_identity_context 脱敏 + 每域字段名 cheat sheet
- `references/identity-model.md` — 机器人 / 真人授权人边界详解 + 写权限规则
- `scripts/weekly_recap.py` — 一键周报:从 smartpage 日总结聚合成本周周报(md)

## 关于 hub-installed `wecom-unified` skill

该 skill 是通过 `npx skills add wecomTeam/wecom-unified -y -g` 安装的（hub-installed → **protected**，本 skill 不能 patch 它）。已知它有以下错误：
- `chat` 路由错误地指向「会话存档」API，对机器人不适用
- 多个域子命令路径不完整（漏了 `users` / `schedules` / `aibot` 等中间层）

要修复它需用 `hermes curator adopt wecom-unified` 转交所有权后再 patch。