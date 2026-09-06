# 2026-08-22 第三 + 第四次栽(ruoyi-vue-page-delivery 增订)

会话:`jonlink policy-module` 后期交付,用户两个连续纠正(都是"我说的是..."):
1. **政策管理里边的政策分类 列表不显示分类**,政策查看侧 tree 里你已经看到了分类 → 用户实测发现我以为好了的页面实际零行
2. **"/opt/JonLink/jonlink-admin 那是啥"** —— 一个孤儿空目录 + 旁边一个 policy-view-app 完整 vite 雏形,我之前没注意
3. **"C"** —— 我列选项 A/B/C 时把最复杂放第一位,用户秒选最窄

## 新沉淀(正文在 SKILL.md,这里是 evidence)

### 1. 三方一致验证脚本(可直接放进 e2e)

```python
# ~/.hermes/skills/ruoyi-vue-page-delivery/scripts/e2e_3way_check.py
"""
E2E 三段一致性验证: DB rows == API total == DOM row count
==========================================================
对刚交付的 (module, entity) 页面跑下列脚本,缺一段不算交付。

用法:
  python3 e2e_3way_check.py <module> <entity>

前置:
  - mysql 凭证在 /root/.hermes/.env
  - Java 已启动 (port 8080)
  - 前端 dist 已部署 (port 80)
"""

import os, sys, subprocess, json, re
from pathlib import Path

import pymysql
import requests
from playwright.sync_api import sync_playwright


def load_env():
    env = {}
    p = Path('/root/.hermes/.env')
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main():
    if len(sys.argv) < 3:
        print('usage: e2e_3way_check.py <module> <entity>', file=sys.stderr)
        sys.exit(2)

    module, entity = sys.argv[1], sys.argv[2]
    env = load_env()

    # 1) DB
    db = pymysql.connect(
        host=env.get('MYSQL_HOST', '127.0.0.1'),
        port=int(env.get('MYSQL_PORT', '3306')),
        user=env.get('MYSQL_USER', 'root'),
        password=env.get('MYSQL_PASSWORD', 'jonlink_root_pwd'),
        database=env.get('MYSQL_DB', 'jonlink'),
    )
    cur = db.cursor()
    table = f"{module}_{entity}".replace('-', '_')
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    n_db = cur.fetchone()[0]

    # 2) API
    tok_req = subprocess.run(
        ['curl', '-s', '-X', 'POST', 'http://127.0.0.1:8080/login',
         '-H', 'Content-Type: application/json',
         '-d', '{"username":"admin","password":"admin123"}'],
        capture_output=True, text=True,
    )
    token = json.loads(tok_req.stdout).get('token', '')
    r = requests.get(
        f'http://127.0.0.1:8080/{module}/{entity}/list',
        params={'pageNum': 1, 'pageSize': 10000},
        headers={'Authorization': f'Bearer {token}'},
    )
    n_api = r.json().get('total', 0)

    # 3) DOM
    parent_path = {
        'policy': 'policy/category',
        'finance': 'fin/some',
    }.get(module, module)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            storage_state={'cookies': [{
                'name': 'Admin-Token', 'value': token,
                'domain': '.115.190.215.93', 'path': '/',
            }]}
        ) if False else browser.new_context()  # auth via API call
        # 实际 cookie 注入需要 site URL,在 hermes-sandbox 里简化:
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(f'http://115.190.215.93/{parent_path}/index')
        page.wait_for_selector('.el-table', timeout=10000)
        n_dom = page.locator('.el-table__body tr.el-table__row').count()
        browser.close()

    print(f'DB={n_db}  API={n_api}  DOM={n_dom}')
    if n_db == n_api == n_dom:
        print('✅ 三方一致')
        sys.exit(0)
    else:
        print('❌ 三方不一致 — 不要 announce 交付')
        sys.exit(1)


if __name__ == '__main__':
    main()
```

### 2. 政策展示端(public 端)参考代码

`PolicyViewPublicController.java`:

```java
package com.jonlink.web.controller.system;

import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import com.jonlink.common.annotation.Anonymous;     // ← 注意这个
import com.jonlink.common.core.controller.BaseController;
import com.jonlink.common.core.domain.AjaxResult;
import com.jonlink.system.domain.PolicyArticle;
import com.jonlink.system.domain.PolicyArticleVersion;
import com.jonlink.system.service.IPolicyArticleService;
import com.jonlink.system.service.IPolicyCategoryService;

@Anonymous
@RestController
@RequestMapping("/policy/view/public")
public class PolicyViewPublicController extends BaseController {

    @Autowired private IPolicyCategoryService categoryService;
    @Autowired private IPolicyArticleService  articleService;

    @Anonymous
    @GetMapping("/tree")
    public AjaxResult tree() {
        PolicyCategory probe = new PolicyCategory();
        probe.setStatus("0");  // 只启用
        return success(categoryService.selectPolicyCategoryTree(probe));
    }

    @Anonymous
    @GetMapping("/current/{categoryId}")
    public AjaxResult current(@PathVariable Long categoryId) {
        return success(articleService.selectCurrentByCategoryId(categoryId));
    }

    @Anonymous
    @GetMapping("/history/{articleId}")
    public AjaxResult history(@PathVariable Long articleId) {
        return success(articleService.selectVersionListByArticleId(articleId));
    }

    @Anonymous
    @GetMapping("/historyDetail/{versionId}")
    public AjaxResult historyDetail(@PathVariable Long versionId) {
        return success(articleService.selectVersionById(versionId));
    }

    @Anonymous
    @GetMapping("/compare")
    public AjaxResult compare(@RequestParam Long articleId,
                              @RequestParam Integer base,
                              @RequestParam Integer target) {
        // ... 略
    }
}
```

`policy/view-public.ts`(前端展示端独立 api 文件):

```ts
import request from '@/utils/request'

function opts() {
  return { headers: { isToken: false } as any }
}

export function publicTreeCategory()          { return request({ url: '/policy/view/public/tree',          method: 'get', ...opts() }) }
export function publicCurrentByCategory(id)   { return request({ url: `/policy/view/public/current/${id}`,  method: 'get', ...opts() }) }
export function publicHistory(id)            { return request({ url: `/policy/view/public/history/${id}`,   method: 'get', ...opts() }) }
export function publicHistoryDetail(id)      { return request({ url: `/policy/view/public/historyDetail/${id}`, method: 'get', ...opts() }) }
export function publicCompare(a, b, t)       { return request({ url: '/policy/view/public/compare', params: { articleId: a, base: b, target: t }, method: 'get', ...opts() }) }
```

### 3. 选项排序的"窄→宽"反向习惯

我原来习惯:
```
A) 端分离独立部署 + 完整重构   ≈1h
B) 复用现有 dist + 公共接口    ≈30min
C) 只修真 bug                  ≈10min    ← 用户秒选
```

应该:
```
C) 只修真 bug                  ≈10min    ← 放首位
B) 复用现有 dist + 公共接口    ≈30min
A) 端分离独立部署 + 完整重构   ≈1h       ← 放末位
```

不要主动把"应该重写"的方案放最前 —— 用户通常是被动响应型,你要把最容易点头的窄改动递到面前。

### 4. 误创的孤儿目录清理(告警)

```bash
# /opt/JonLink 下所有顶层目录(确认没事的 3 个)
ls /opt/JonLink/
# expected:
#   JonLink-Vue/        ✅ Spring Boot 后端
#   JonLink-Vue3-TS/    ✅ Vue3 前端
#   (可选) policy-view-app/  ← 用户拍板

# 任何不在上面 3 个的东西就该质问:
ls /opt/JonLink/jonlink-admin/ 2>&1
#  如果不是预期 → 立即备份到 /tmp/jonlink-admin-orphan-backup/ 然后 rm -rf
#  用 '孤儿目录备份 + 整目录删除',不用单文件删除避免路径碎
```
