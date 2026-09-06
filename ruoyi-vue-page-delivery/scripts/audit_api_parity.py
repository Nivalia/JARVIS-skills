#!/usr/bin/env python3
"""RuoYi 前后端接口一致性对账(实测有效,2026-09-04 JonLink 全量跑通)。

用法:
    python3 audit_api_parity.py /opt/JonLink/JonLink-Vue /opt/JonLink/JonLink-Vue3-TS

输出:BE 路由数 / FE endpoint 数 / FE 调了但后端没有的清单。

关键点(第一版漏解析导致 34 条假阳性):
  1. `@GetMapping(value={"/a","/b"})` 一个注解可能挂多个路径 → 必须 findall 全部字符串,
     不能只取第一个。
  2. `@RequestMapping` 可能写成 `@RequestMapping({"/x"})` 或裸 `@RequestMapping`(无路径,
     方法上写全路径,WxMpBizController 就是这样)→ base 允许为空。
  3. 前端 url 里的 `${id}` 与后端 `{id}` 都要归一成 `{}`。
  4. 前端常写 `url: '/finance/x/audit/' + id` → 路径尾部带 `/`,必须双向前缀容错匹配,
     否则整片假阳性。
"""
import re
import sys
import glob
import os


def backend_routes(be_dir):
    routes = set()
    for p in glob.glob(os.path.join(be_dir, '**/*Controller.java'), recursive=True):
        if '/target/' in p:
            continue
        s = open(p, encoding='utf-8', errors='ignore').read()
        m = re.search(r'@RequestMapping\(\s*(?:value\s*=\s*)?\{?\s*"([^"]*)"', s)
        base = m.group(1) if m else ''
        for mm in re.finditer(r'@(?:Get|Post|Put|Delete|Patch|Request)Mapping\s*\(([^)]*)\)', s):
            subs = re.findall(r'"([^"]*)"', mm.group(1)) or ['']
            for sub in subs:
                full = (base.rstrip('/') + '/' + sub.lstrip('/')) if sub else base
                routes.add(re.sub(r'\{[^}]*\}', '{}', full or '/'))
        # 无参注解:@GetMapping 换行
        for _ in re.finditer(r'@(?:Get|Post|Put|Delete|Patch)Mapping\s*\n', s):
            routes.add(base or '/')
    return {r.rstrip('/') for r in routes}


def frontend_endpoints(fe_dir):
    eps = set()
    for p in glob.glob(os.path.join(fe_dir, 'src/api/**/*.ts'), recursive=True):
        s = open(p, encoding='utf-8', errors='ignore').read()
        for mm in re.finditer(r'url:\s*[\'"`]([^\'"`]+)', s):
            u = re.sub(r'\$\{[^}]*\}', '{}', mm.group(1))
            eps.add(u.rstrip('/'))
    return eps


def main():
    be_dir, fe_dir = sys.argv[1], sys.argv[2]
    be, fe = backend_routes(be_dir), frontend_endpoints(fe_dir)
    miss = [u for u in sorted(fe)
            if u not in be
            and not any(b == u or b.startswith(u + '/') or u.startswith(b + '/') for b in be)]
    print('BE routes:', len(be))
    print('FE endpoints:', len(fe))
    print('MISSING:', len(miss))
    for m in miss:
        print('  ', m)
    return 1 if miss else 0


if __name__ == '__main__':
    sys.exit(main())
