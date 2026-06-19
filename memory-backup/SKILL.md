---
name: memory-backup
description: "JARVIS 永久记忆备份与恢复。每次交互后自动增量备份，支持手动触发备份、手动恢复、手动查看记忆。"
metadata:
  openclaw:
    emoji: "💾"
    auto: true
    tier: "god"
---

# 💾 记忆备份系统

JARVIS 的永久记忆备份技能，确保记忆永不丢失。

## 核心功能

1. **自动增量备份** — 每次会话结束自动调用 backup
2. **手动备份** — `备份记忆` 触发
3. **手动恢复** — `恢复记忆` 触发
4. **查看记忆** — `查看记忆库` 触发

## 数据存储

- 主库：`~/.hermes/memories/memos.db`（SQLite）
- 备份：`~/.hermes/memories/backups/`（每日增量）
- 格式：JSON + SQLite dump

## 备份内容

```
- agents 表：JARVIS 和爱马仕的身份、偏好、习惯
- memories 表：所有记忆（分类+内容+重要度+标签）
- interactions 表：最近 1000 条交互记录
- daily_summaries 表：每日总结
```

## 触发词

- "备份记忆"
- "保存记忆"
- "记忆状态"
- "查看记忆库"

## 使用方式

```bash
# 备份
python3 ~/.hermes/memories/memory_db.py backup

# 查看状态
python3 ~/.hermes/memories/memory_db.py status
```
