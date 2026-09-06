#!/usr/bin/env python3
"""MyBatis mapper XML 里每条 <select> 直接丢给 MySQL 干跑,抓 SQL 语法/列名错。

用法:
    python3 mapper_sql_dryrun.py <mapper.xml> <db> [user] [password]

为什么需要:mvn package 不校验 SQL,接口只在被点到时才 500。JonLink 真实案例
`subjectBalanceTop10` 报 `Reference 'value' not supported (reference to group function)`
—— MySQL 不允许 HAVING/WHERE 引用聚合别名,必须包一层子查询再 `WHERE value != 0`。

必须做的三步清洗(不清洗会产生 gt/lt/HTML 实体假阳性):
  1. 去掉 <if>/<where>/<foreach>/注释 标签本身,保留内部 SQL 文本。
  2. `html.unescape` —— XML 里 `>=` 常写成 `&gt;=`,不还原会报 Unknown column 'gt'。
  3. `#{limit}` → 10,其余 `#{x}` → 字符串占位。含 `${}` 的动态拼接跳过。
"""
import re
import sys
import html
import subprocess


def main():
    xml_path, db = sys.argv[1], sys.argv[2]
    user = sys.argv[3] if len(sys.argv) > 3 else 'root'
    pwd = sys.argv[4] if len(sys.argv) > 4 else ''
    x = open(xml_path, encoding='utf-8').read()
    bad = 0
    for m in re.finditer(r'<select id="(\w+)"[^>]*>(.*?)</select>', x, re.S):
        sid, sql = m.group(1), m.group(2)
        sql = re.sub(r'<!--.*?-->', '', sql, flags=re.S)
        sql = re.sub(r'</?(?:if|where|foreach|trim|choose|when|otherwise|set)[^>]*>', '', sql)
        sql = html.unescape(sql)
        if '${' in sql:
            print('skip(dyn)', sid)
            continue
        sql = re.sub(r'#\{limit\}', '10', sql)
        sql = re.sub(r'#\{\w+[^}]*\}', "'2026-01-01'", sql)
        cmd = ['mysql', f'-u{user}']
        if pwd:
            cmd.append(f'-p{pwd}')
        cmd += [db, '-e', sql]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode:
            bad += 1
            print('FAIL', sid, '|', p.stderr.strip().splitlines()[-1][:200])
        else:
            print('ok  ', sid)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
