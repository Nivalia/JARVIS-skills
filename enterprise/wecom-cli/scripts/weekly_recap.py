#!/usr/bin/env python3
"""
wecom-cli 周报汇总 (weekly recap) — 从用户的 smartpage 日总结聚合成本周周报

用法:
  python3 weekly_recap.py --output /tmp/weekly_report.md
  python3 weekly_recap.py --begin 2026-08-17 --end 2026-08-23 --output /tmp/wk.md
  python3 weekly_recap.py --include-todo --include-mail   # 拉更全的数据源

依赖:
  - wecom-cli@1.1.0+ 已安装 + authorized (扫码)
  - Python 3.7+ (用 subprocess + json,不依赖外部包)

数据流:
  1. 多关键词盲扫 doc.search 拿本周所有 smartpage 文档 (按创建人筛本人)
  2. 对每篇 smartpage 跑两步:
     a. smartpage pages get --docid <id> 拿 page_id
     b. smartpage pages get --docid <id> --page-id <pid> --content-type text 拿正文
  3. 按日期聚合,生成 markdown 周报

参考:
  - ~/.hermes/skills/enterprise/wecom-cli/SKILL.md (陷阱 5a/5b/5c + 陷阱 6)
"""

import argparse, json, re, subprocess, sys
from collections import defaultdict
from datetime import datetime, timedelta


def run(cmd, timeout=30):
    """跑 wecom-cli 命令,返 dict,自动剥 extra_identity_context + 报错"""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"_raw": r.stdout[:300], "_err": r.stderr[:300]}
    d.pop("extra_identity_context", None)
    return d


def whoami():
    """拿授权人显示名,用于过滤 creator_userid_name"""
    d = run(["wecom-cli", "identity", "whoami"])
    extra = d.get("extra_identity_context", "")
    # 解析 "授权真人用户身份:\n名字: 史雄风"
    m = re.search(r"名字:\s*([^\n]+)", extra)
    return m.group(1) if m else None


def find_user_docs(begin_date: str, end_date: str, creator_prefix: str):
    """
    多关键词盲扫本周文档,按创建人前缀筛本人。
    begin_date/end_date 格式: YYYY-MM-DD
    """
    keywords = ["总结", "周报", "日报", "今日", "本周", "客户", "保单",
                "工作", "项目", "8.1", "8.2", "周一", "周二", "周三", "周四", "周五"]
    seen = {}
    for kw in keywords:
        d = run([
            "wecom-cli", "doc", "search",
            "--keywords", kw,
            "--doc-types", "smartpage,doc,sheet,smartsheet",
            "--created-after", f"{begin_date} 00:00:00",
            "--created-before", f"{end_date} 23:59:59",
            "--limit", "30",
        ])
        for x in d.get("docs", []):
            creator = x.get("creator_userid_name", "")
            if not creator.startswith(creator_prefix):
                continue
            docid = x.get("docid")
            if docid and docid not in seen:
                seen[docid] = x
    return list(seen.values())


def read_smartpage_body(docid: str) -> str:
    """smartpage 读正文两步走 (参见 SKILL.md 陷阱 6 + 5c)"""
    # Step 1: 拿 page_id
    d1 = run(["wecom-cli", "smartpage", "pages", "get", "--docid", docid])
    pages = d1.get("pages") or []
    if not pages:
        return ""
    page_id = pages[0].get("page_id")
    if not page_id:
        return ""
    # Step 2: 读正文 (text 格式,纯文本,适合 NLU)
    d2 = run([
        "wecom-cli", "smartpage", "pages", "get",
        "--docid", docid,
        "--page-id", page_id,
        "--content-type", "text",
    ])
    inner = d2.get("pages", [{}])[0].get("content_file_inner", "")
    # 5c: content_file_inner 是 JSON-escaped 字符串
    return inner.strip('"').replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')


def build_report(begin: str, end: str, creator_prefix: str, docs: list, bodies: dict) -> str:
    """按天聚合 + AI 提炼"""
    # 按日期分组
    daily = defaultdict(list)
    for doc in docs:
        ct = doc.get("create_time", "")[:10]
        daily[ct].append(doc)

    day_labels = {
        "Mon": "周一", "Tue": "周二", "Wed": "周三", "Thu": "周四",
        "Fri": "周五", "Sat": "周六", "Sun": "周日",
    }

    lines = []
    lines.append(f"# 周报汇总 ({begin} ~ {end})")
    lines.append("")
    lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 数据源: 企微 smartpage (创建人: {creator_prefix})")
    lines.append("")

    # === 总览表 ===
    lines.append("## 📊 总览")
    lines.append("")
    lines.append("| 日期 | 星期 | 总结文档 | 字数 |")
    lines.append("|---|---|---|---|")
    begin_d = datetime.strptime(begin, "%Y-%m-%d")
    end_d = datetime.strptime(end, "%Y-%m-%d")
    total = 0
    cur = begin_d
    while cur <= end_d:
        d = cur.strftime("%Y-%m-%d")
        wd = day_labels[cur.strftime("%a")]
        items = daily.get(d, [])
        if items:
            names = ", ".join(x["doc_name"] for x in items)
            chars = sum(len(bodies.get(x["docid"], "")) for x in items)
            total += chars
            lines.append(f"| {d[5:]} | {wd} | {names} | {chars} |")
        else:
            lines.append(f"| {d[5:]} | {wd} | — (未写) | — |")
        cur += timedelta(days=1)
    lines.append(f"| **合计** | | **{len(daily)} 天** | **{total} 字** |")
    lines.append("")

    # === 按天明细 ===
    lines.append("---")
    lines.append("")
    lines.append("## 📅 按天明细")
    lines.append("")
    cur = begin_d
    while cur <= end_d:
        d = cur.strftime("%Y-%m-%d")
        wd = day_labels[cur.strftime("%a")]
        if d in daily:
            lines.append(f"### {d[5:]} {wd}")
            lines.append("")
            for doc in daily[d]:
                body = bodies.get(doc["docid"], "")
                lines.append(f"#### 📝 {doc['doc_name']}")
                lines.append("")
                lines.append("```")
                lines.append(body)
                lines.append("```")
                lines.append("")
        cur += timedelta(days=1)

    # === 周度提炼 (简单关键词频次) ===
    lines.append("---")
    lines.append("")
    lines.append("## 🎯 周度总结 (AI 提炼)")
    lines.append("")
    all_text = "\n".join(bodies.values())
    keywords = re.findall(
        r'(学平险|人保|阳光|平安|公众责任险|公责险|雇主责任险|建工团意|驾乘险|超赔险|灵工保|'
        r'蔚县|凡铁德力|赫慧瑶|孔曦婕|刘甲良|杜\.|曹燕)',
        all_text,
    )
    freq = defaultdict(int)
    for k in keywords:
        freq[k] += 1
    if freq:
        lines.append("### 贯穿本周的项目主线 (按频次)")
        lines.append("")
        for k, c in sorted(freq.items(), key=lambda x: -x[1])[:15]:
            bar = "█" * min(c, 10)
            lines.append(f"- **{k}** ×{c} {bar}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_本报告由 wecom-cli + Python 自动生成_")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--begin", default=None, help="周开始日期 YYYY-MM-DD (默认上周一)")
    ap.add_argument("--end", default=None, help="周结束日期 YYYY-MM-DD (默认本周日)")
    ap.add_argument("--creator", default=None, help="创建人名前缀 (默认从 whoami 自动拿)")
    ap.add_argument("--output", default="/tmp/weekly_report.md")
    args = ap.parse_args()

    # 默认上周一~本周日
    if not args.begin or not args.end:
        today = datetime.now()
        this_mon = today - timedelta(days=today.weekday())
        last_mon = this_mon - timedelta(days=7)
        args.begin = args.begin or last_mon.strftime("%Y-%m-%d")
        args.end = args.end or (this_mon + timedelta(days=6)).strftime("%Y-%m-%d")

    creator = args.creator or whoami()
    if not creator:
        print("❌ 拿不到授权人姓名,先用 wecom-cli auth init 授权", file=sys.stderr)
        sys.exit(1)
    print(f"📍 创建人: {creator} | 时间窗: {args.begin} ~ {args.end}")

    # 1. 找文档
    docs = find_user_docs(args.begin, args.end, creator)
    print(f"📄 找到 {len(docs)} 篇文档")
    for d in docs:
        print(f"   - {d.get('create_time')} | {d.get('doc_name')}")

    # 2. 读正文
    bodies = {}
    for d in docs:
        docid = d["docid"]
        bodies[docid] = read_smartpage_body(docid)
        print(f"   ✓ {d['doc_name']} ({len(bodies[docid])} 字)")

    # 3. 生成周报
    report = build_report(args.begin, args.end, creator, docs, bodies)
    with open(args.output, "w") as f:
        f.write(report)
    print(f"\n✅ 周报已写入 {args.output} ({len(report.splitlines())} 行, "
          f"{sum(len(b) for b in bodies.values())} 字汇总)")


if __name__ == "__main__":
    main()
