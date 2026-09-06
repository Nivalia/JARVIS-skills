# xlsx 列头解析器(导出 Excel 验证用)

RuoYi export 接口返回二进制 xlsx,curl 看到的是乱码。本脚本:

1. POST `/login` 拿 admin token
2. POST `/<module>/<entity>/export` 拿 xlsx 二进制
3. 解 xlsx 内部 zip,取 `xl/worksheets/sheet1.xml` 第一行 `<row r="1">`
4. 正则提所有 `<t>...</t>`,这就是 admin 看到的真实列头

## 完整脚本

```python
import zipfile, re, json, urllib.request

def get_admin_token(host="http://127.0.0.1:8080", user="admin", pwd="admin123"):
    req = urllib.request.Request(
        f"{host}/login",
        data=json.dumps({"username": user, "password": pwd}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req).read())["token"]

def export_headers(host, path, token):
    req = urllib.request.Request(
        f"{host}{path}",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
        data=b"",
    )
    body = urllib.request.urlopen(req).read()
    if len(body) < 200:
        return None  # 可能是错误响应
    with zipfile.ZipFile(__import__("io").BytesIO(body)) as z:
        with z.open("xl/worksheets/sheet1.xml") as f:
            raw = f.read().decode("utf-8")
    m = re.search(r'<row r="1">.*?</row>', raw, re.S)
    if not m:
        return None
    return re.findall(r'<t[^>]*>([^<]*)</t>', m.group(0))

def scan_all(host="http://127.0.0.1:8080"):
    token = get_admin_token(host)
    controllers = discover_export_controllers()  # 见下方
    results = []
    for path, name in controllers:
        try:
            headers = export_headers(host, path, token)
            if not headers:
                continue
            long_count = sum(1 for h in headers if len(h) > 5)
            max_len = max(len(h) for h in headers)
            long_items = [(i, h) for i, h in enumerate(headers) if len(h) > 5]
            results.append({
                "controller": name,
                "path": path,
                "columns": len(headers),
                "max_len": max_len,
                "long_count": long_count,
                "long_items": long_items,
            })
        except Exception as e:
            results.append({"controller": name, "path": path, "error": str(e)})
    return results

def discover_export_controllers(admin_root="/opt/<project>/jonlink-admin/src/main/java"):
    """Grep 所有 @RequestMapping + @PostMapping("/export") 组合."""
    import subprocess, os
    result = subprocess.run(
        ["grep", "-rln", '@PostMapping("/export")', admin_root, "--include=*.java"],
        capture_output=True, text=True,
    )
    controllers = []
    for fname in result.stdout.splitlines():
        with open(fname) as f:
            c = f.read()
        rm = re.search(r'@RequestMapping\(["\']([^"\']+)["\']\)', c)
        if rm:
            controllers.append((rm.group(1) + "/export", os.path.basename(fname).replace("Controller.java", "")))
    return controllers

# 运行
if __name__ == "__main__":
    results = scan_all()
    clean = sum(1 for r in results if r.get("long_count", 1) == 0)
    print(f"完全清干净: {clean}/{len(results)}")
    for r in results:
        if r.get("long_count", 0) > 0:
            print(f"  {r['controller']} ({r['path']}): {r['columns']} 列, max={r['max_len']}字, 长字段 {r['long_count']}")
            for i, h in r["long_items"]:
                print(f"    {chr(65+i)}: {len(h)} {h!r}")
```

## 输出解读

- **`controller`** + **`path`**: 哪个接口
- **`columns`**: 总列数
- **`max_len`**: 最长表头字数
- **`long_count`**: > 5 字的字段数(阈值可调)
- **`long_items`**: 详细列表

## 已知 PRESERVE 字段(出现是正常的,不要改)

| 字段 | 原因 |
|---|---|
| `openid` / `ticket` / `AppSecret` / `access_token` / `AppID` / `Token` | 微信 API 标准字段名 |
| `receiptNo` / `paymentNo` / `voucherNo` / `expenseNo` / `invoiceNo` / `partnerName` / `settleRecordNo` / `sourceNo` / `subjectCode` / `subjectName` | 数据库列名,也是 Java prop 字段名 |

任何不在上表的"长字段名"都应该人工审一下 — 要么保留业务语义,要么短化。

## 重跑间隔

- **每改完一轮 Domain `.java` → 重 build → 重启 → 重跑本脚本**
- **每改完一轮 Vue label → 重新 `vite build` → dist 落盘即可(nginx HTML 不缓存)**

## 常见异常

- `urllib.error.HTTPError: 401` → token 失效,重新 `get_admin_token()`
- `urllib.error.HTTPError: 500` → Controller URL 错,重新读 `@RequestMapping`
- `export_headers` 返回 `None` → xlsx 损坏或导出逻辑报错(检查 controller 日志)
