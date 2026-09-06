#!/usr/bin/env python3
"""
scan_vue_handlers.py — 扫描 1 个 vue 文件的 template 里调用的 handler 是否在 setup 里定义。

用途:RuoYi-Vue (Plus) / 任何 Vue3 project 写完新页面后必须跑一次。
本文件之前缺失场景(2026-08-22):policy/category/index.vue 写了 @click="handleQuery"
但 setup 没 function handleQuery → vite build pass + curl 200 + 浏览器一打开 form 不显示
+ 表格无数据。一旦扫描到 MISSING=handleQuery 必修,免去真浏览器 e2e 才能发现。

用法:
    python3 scan_vue_handlers.py FILE.vue [FILE2.vue ...]
或对一个目录递归:
    python3 scan_vue_handlers.py src/views/finance/

退出码:0 = 全部 handler 定义 / 1 = 有 MISSING / 2 = 报告无文件
"""

import re
import sys
from pathlib import Path


# 哪些算 handler 引用
TEMPLATE_HANDLER_PATTERNS = [
    # @click="X"  /  @click="X()"  /  @click="X(arg)"
    re.compile(r'@(?:click|change|input|keyup|keydown|blur|focus|submit|node-click|node-expand|move|current-change|on-change|on-input|on-clear|on-remove|on-success|on-error|on-select|on-update|on-change|on-cascader-change|on-upload|on-success|on-progress|on-change|on-input)\s*=\s*["\']?(\w+)(?=\s*[($\"\'])'),
    # v-on:click="X"
    re.compile(r'v-on:[a-z-]+=["\']?(\w+)'),
    # :active-method / :default-expand-all 这类 prop 不要误识别(已经排除)
]


# setup 内函数/变量的定义位置
SETUP_DEFINITION_PATTERNS = [
    re.compile(r'function\s+(\w+)\s*\('),                  # function X() {...}
    re.compile(r'const\s+(\w+)\s*=\s*(?:function|async|\\(|\()'),  # const X = function / (...) => {}
    re.compile(r'(\w+)\s*\([^)]*\)\s*:\s*(?:void|number|boolean|string)',  # X(arg: void): number → 内部方法
    re.compile(r'const\s+\{\s*([^}]+)\s*\}\s*=\s*proxy'),         # const { X, Y } = proxy  ← 用 store/dict 数据
    re.compile(r'const\s+\{\s*([^}]+)\s*\}\s*=\s*toRefs'),         # const { X, Y } = toRefs(data)
    re.compile(r'const\s+\{\s*([^}]+)\s*\}\s*=\s*useRoute'),       # const { X } = useRoute
    re.compile(r'const\s+\{\s*([^}]+)\s*\}\s*=\s*useRouter'),      # const { X } = useRouter
    re.compile(r'const\s+\{\s*([^}]+)\s*\}\s*=\s*useDict'),         # const { X } = useDict(...)
    re.compile(r'const\s+\{\s*([^}]+)\s*\}\s*=\s*useStore'),       # const { X } = useStore()
    re.compile(r'\$\w+\.useDict\(["\']([^"\']+)["\']\)'),           # proxy.useDict('sys_x').then(sys_x => ...)
    re.compile(r'\$\w+\.useDict\(["\']([^"\']+)["\']\)\)\.(\w+)'),  # proxy.useDict('sys_normal_disable').sys_normal_disable
    re.compile(r'\bref<(\w+)>\s*\('),                              # const X = ref<Y>(...)
    re.compile(r'\bcomputed<(\w+)>\s*\('),                          # computed<X>(...)
    re.compile(r'reactive\(\s*\{'),                                # reactive({...}) 内字段也算定义
    re.compile(r'ref<[^>]*>\(\s*([\w, ]+)\)'),                     # ref<X>(default) 内 default 字段
]


# template 引用变量(非 handler)常见白名单 — 这类不引用 handler,就算 setup 中没声明也合理:
WATCHLIST = ['handleQuery', 'handleAdd', 'handleUpdate', 'handleDelete', 'handleExport',
            'handleSelectionChange', 'handleToggleStatus', 'handleVersions',
            'resetQuery', 'submitForm', 'loadCategories', 'getList', 'getTree',
            'onCascaderChange', 'onFormCascaderChange', 'onNodeClick', 'onProgress',
            'filterNode', 'loadCurrent', 'loadHistory', 'loadVersionDetail',
            'parsePics', 'restoreVersion', 'cancel', 'reset']


def extract_template_handlers(template_text: str) -> set:
    handlers = set()
    for pat in TEMPLATE_HANDLER_PATTERNS:
        for m in pat.finditer(template_text):
            handlers.add(m.group(1))
    return handlers


def extract_setup_definitions(script_text: str) -> set:
    defined = set()
    for pat in SETUP_DEFINITION_PATTERNS:
        for m in pat.finditer(script_text):
            # 多键拆解
            matches = re.findall(r'\b(\w+)\b', m.group(1))
            for x in matches:
                # 跳过 type keyword
                if x not in ('default', 'null', 'true', 'false', 'void', 'number', 'boolean', 'string',
                              'Proxy', 'Array', 'Object', 'Function', 'any', 'never', 'unknown', 'Function'):
                    defined.add(x)
    return defined


def scan_one_file(path: Path):
    content = path.read_text(encoding='utf-8')
    template_m = re.search(r'<template>.*?</template>', content, re.DOTALL)
    script_m = re.search(r'<script[^>]*>.*?</script>', content, re.DOTALL)

    template_text = template_m.group() if template_m else ''
    script_text = script_m.group() if script_m else ''

    handlers = extract_template_handlers(template_text)
    defined = extract_setup_definitions(script_text)

    missing = handlers - defined

    # 下列几种忽略(WATCHLIST 内没定义的可能来自 dict/store,先 flag 让用户审)
    unused_filters = {
        #  template 内 @click="sidebarMenu" 等 vue 内置 dispatch ref
        '__id', '_uid', 'val',
    }
    missing -= unused_filters

    return handlers, defined, missing


def main(args):
    if not args:
        print('usage: scan_vue_handlers.py <file1.vue ... | dir/>', file=sys.stderr)
        return 2

    paths = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            paths.extend(p.rglob('*.vue'))
        else:
            paths.append(p)

    if not paths:
        print(f'no vue files found in {args}', file=sys.stderr)
        return 2

    fail = 0
    for path in sorted(paths):
        handlers, defined, missing = scan_one_file(path)
        marker = '✅' if not missing else '⚠️'
        print(f'\n=== {path} ===')
        print(f'  handlers referenced: {sorted(handlers)}')
        print(f'  defined: {sorted(defined)}')
        if missing:
            print(f'  {marker} MISSING in setup: {sorted(missing)}')
            fail += 1
        else:
            print(f'  {marker} all handlers defined')

    if fail:
        print(f'\n💥 {fail} file(s) have undefined handlers. Add them to <script setup> before claiming the page works.', file=sys.stderr)
        return 1

    print('\n✅ all handlers defined in all checked files')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
