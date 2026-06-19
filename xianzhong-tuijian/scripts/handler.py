"""
险种推荐 handler.py v8
- 模板驱动：读取模板 C-H 列，按列继承
- 每行独立多维度过滤，独立统计保险公司
- 禁止任何形式的行间结果复用
- v6 (2026-06-08)：修正列索引偏移（原 v5 比实际表头 +1，原因是新数据表少 1 列"序号"前缀列）；同时修复 1 车多行重复计入 bug，改 first-match-wins
- v7 (2026-06-08)：去掉 load_data 里的 `if not row[0]: continue` 过滤（原误判批单号列为必要字段，导致 99% 数据被丢弃——实际批单号列几乎全空，正确的是只要 plate+vin 有值就保留）；同时删除模板中「营运+多用途」2 行（R25/R26），总行数 28 → 26
- v8 (2026-06-15)：恢复 v5 的「每行独立」模式。理由：first-match-wins 让一辆行唐地址+25 岁车主的新能源客车新车只被 R3 计入，R6/R7-R13 全为 0；R3/R5/R6 通用维度 vs R7-R26 细分维度在业务上正交，强行互斥会丢失细分维度的真实推荐。v8 删掉 `assigned` 全局集合。
"""
import os, re, shutil, zipfile
from datetime import datetime, date
import openpyxl
from openpyxl.utils import get_column_letter
from collections import defaultdict, Counter

# ── 数据列 iloc 索引 (0-based, 2026-06-15 实测对齐) ──────
# 实际表头 (数据报表0): 数据来源|出单端|保单号|批单号|保险公司|渠道层级|...
# 2026-06-15 修正: 数据源新增 3 列前缀 (数据来源/出单端/保单号), 全部索引 +3
# 2026-06-08 上次修正: 当时表比 v5 少 1 列"序号" → 全部 -1; 现累计偏移 = +2
I_SN    = 4     # 保险公司
I_PLATE = 10    # 车牌号
I_VIN   = 28    # 车架号/VIN
I_CHEX  = 32    # 车辆种类 (客车/货车)
I_MODEL = 29    # 车辆型号 (货车细分关键词)
I_LOAD  = 34    # 核载质量 (吨)
I_SHIYO = 27    # 车辆使用性质
I_NENG  = 42    # 能源种类
I_ZHONG = 38    # 险种
I_GUO   = 23    # 过户车辆标志
I_NEW   = 25    # 新旧车标志
I_REGD  = 24    # 车辆初始登记日期
I_CERT  = 26    # 发证日期
I_AGE_I = 13    # 投保人年龄
I_AGE_H = 18    # 被保人年龄
I_AGE_O = 21    # 车主年龄
I_ADDR_I= 15    # 投保人地址
I_ADDR_H= 19    # 被保人地址
I_ADDR_O= 22    # 车主地址
I_ID_I  = 14    # 投保人证件号
I_ID_H  = 17    # 被保人证件号
I_ID_O  = 20    # 车主证件号

# ── 工具 ─────────────────────────────────────────────────
def short_name(s):
    s = str(s).strip()
    for suf in ('财险', '保险', '在线', '联合'):
        s = re.sub(rf'{suf}$', '', s)
    return s

def parse_age(val):
    if not val: return None
    m = re.search(r'(\d+)岁', str(val))
    return int(m.group(1)) if m else None

def min_age(row):
    ages = [parse_age(row[i]) for i in (I_AGE_I, I_AGE_H, I_AGE_O)]
    ages = [a for a in ages if a is not None]
    return min(ages) if ages else None

def is_new_car(row):
    flag = str(row[I_NEW]).strip() if row[I_NEW] else ''
    if flag in ('新车', '是'): return True
    if flag in ('旧车', '否'): return False
    reg = str(row[I_REGD]).strip() if row[I_REGD] else ''
    if not reg: return True
    try:
        r = datetime.strptime(reg[:10], '%Y-%m-%d').date()
        return (date.today() - r).days < 274  # 9个月
    except: return True

def is_guo_car(row):
    flag = str(row[I_GUO]).strip() if row[I_GUO] else ''
    if flag == '是': return True
    if flag == '否': return False
    reg = str(row[I_REGD]).strip() if row[I_REGD] else ''
    cert = str(row[I_CERT]).strip() if row[I_CERT] else ''
    if not reg or not cert: return False
    if reg == cert: return False
    try:
        r = datetime.strptime(reg[:10], '%Y-%m-%d').date()
        c = datetime.strptime(cert[:10], '%Y-%m-%d').date()
        return (c - r).days < 365
    except: return False

def is_xin(neng):
    """新能源判断: 燃油/燃气/空 → False (空值保守判为燃油, 不命中 D=新能源 行)"""
    s = str(neng).strip() if neng else ''
    if s == '': return False
    return s not in ('燃油', '燃气')

def truck_sub(model):
    s = str(model) if model else ''
    if '厢式' in s or '封闭式' in s: return '厢货'
    if '仓栅' in s: return '仓栅'
    if '自卸' in s: return '自卸'
    if '多用途' in s: return '多用途'
    return '普货'

def load_lt_2(row):
    v = row[I_LOAD]
    if v is None: return True
    try:
        t = float(v)
        if t > 40: t = t / 1000
        return t < 2
    except: return True

# ── 占位行：保留行号但不计算/不填充（数据源无对应采集维度）
# v7 调整：删 R25/R26（营运+多用途）后，原 R26 占位行不再存在
PLACEHOLDER_ROWS = {4, 16, 19, 23}

# ── 模板驱动：解析每行 C-H 条件，按列继承 ─────────────
def parse_template(tmpl_path):
    """
    继承规则 (left-to-right, "right-of-set-resets" )：
    - 顺序 C(冀A)→D(能源)→E(车辆种类)→F(使用)→G(新旧/车型)→H(过户)
    - 从左到右扫描本行：
      * 该列有值 → 使用并更新 last
      * 该列为空 且 左侧没出现过显式设置 → 继承 last
      * 该列为空 且 左侧已有显式设置 → 重置为 None (右侧不再受前一段影响)
    - 特例：E=货车 时 D 必须重置为 None (货车维度无燃油/新能源区分)
    """
    wb = openpyxl.load_workbook(tmpl_path, data_only=True)
    ws = wb.active
    cols = [('C', 3), ('D', 4), ('E', 5), ('F', 6), ('G', 7), ('H', 8)]
    last = {c: None for c, _ in cols}
    rows = []
    for r in range(3, 27):  # v7 调整：删除模板中「营运+多用途」2 行后，总行数 28 → 26
        raw = {}
        for letter, idx in cols:
            v = ws.cell(r, idx).value
            raw[letter] = str(v).strip() if v is not None and str(v).strip() != '' else None

        cond = {}
        in_reset = False
        for letter, _ in cols:
            if raw[letter] is not None:
                last[letter] = raw[letter]
                cond[letter] = raw[letter]
                in_reset = True
            else:
                cond[letter] = None if in_reset else last[letter]

        rows.append({'r': r, 'cond': cond})
    return rows

# ── 单车过滤器：把行条件转成 bool 函数 ──────────────────
def make_filter(cond):
    """根据一行条件生成 filter(rec) -> bool"""
    c, d, e, f_, g, h = cond['C'], cond['D'], cond['E'], cond['F'], cond['G'], cond['H']

    def filt(rec):
        plate = str(rec[I_PLATE]).strip() if rec[I_PLATE] else ''
        neng  = str(rec[I_NENG]).strip() if rec[I_NENG] else ''
        chex  = str(rec[I_CHEX]).strip() if rec[I_CHEX] else ''
        shiyo = str(rec[I_SHIYO]).strip() if rec[I_SHIYO] else ''
        model = str(rec[I_MODEL]).strip() if rec[I_MODEL] else ''
        newc  = is_new_car(rec)
        guo   = is_guo_car(rec)
        ids   = [rec[I_ID_I], rec[I_ID_H], rec[I_ID_O]]
        addrs = [rec[I_ADDR_I], rec[I_ADDR_H], rec[I_ADDR_O]]

        # C: 冀A
        if c == '冀A':
            if not plate.startswith('冀A'): return False

        # D: 能源
        if d == '新能源':
            if is_xin(neng) is False: return False
        elif d == '燃油':
            if is_xin(neng) is True: return False
        # d='通用' 或 None → 不限

        # E: 车辆种类 / 特殊维度
        if e == '客车':
            if chex != '客车': return False
        elif e == '货车':
            if chex != '货车': return False
            if not load_lt_2(rec): return False
        elif e == '行唐地址':
            xt = any('行唐' in str(a) for a in addrs) or \
                 any(str(i)[:6] == '130125' for i in ids if i)
            if not xt: return False
        elif e == '异地身份证':
            id_i = str(rec[I_ID_I]).strip() if rec[I_ID_I] else ''
            if len(id_i) < 4 or not id_i.startswith('1301'): return False
        elif e == '25岁以下':
            age = min_age(rec)
            if age is None or age >= 25: return False
        # e=None → 不限

        # F: 使用性质
        if f_ == '家用':
            if '家庭自用' not in shiyo: return False
        elif f_ == '非营业':
            if '非营业' not in shiyo: return False   # '非营业货运'/'非营业企业' 命中，排除'营业货运'/'家庭自用'
        elif f_ == '营运':
            if shiyo != '营业货运': return False
        elif f_ == '企业':
            if '非营业企业' not in shiyo: return False
        # f_=None → 不限

        # G: 新旧车 (客车) / 车型细分 (货车)
        if g == '新车':
            if not newc: return False
        elif g == '旧车':
            if newc: return False
        elif g in ('厢货', '仓栅', '多用途', '自卸', '普货'):
            if truck_sub(model) != g: return False
        # g=None → 不限

        # H: 过户
        if h == '过户':
            if not guo: return False
        elif h == '非过户':
            if guo: return False
        # h=None → 不限

        return True

    return filt

# ── 数据加载 & 险种分类 ─────────────────────────────────
def load_data(src):
    wb = openpyxl.load_workbook(src, data_only=True)
    ws = wb.active
    by_key = defaultdict(list)
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row: continue  # v7 修复：去掉 "or not row[0]" 过滤（原误判批单号列为必要字段，导致 99% 数据被丢）
        plate = str(row[I_PLATE]).strip() if row[I_PLATE] else ''
        vin   = str(row[I_VIN]).strip()   if row[I_VIN]   else ''
        if not plate or not vin: continue
        by_key[(plate, vin)].append({
            'row': row,
            'zhong': str(row[I_ZHONG]).strip() if row[I_ZHONG] else '',
        })
    return by_key

def classify(by_key):
    single, san = set(), set()
    for key, recs in by_key.items():
        zhongs = [r['zhong'] for r in recs]
        has_jq = any('交强' in z for z in zhongs)
        has_sy = any('商业' in z for z in zhongs)
        if has_jq and not has_sy: single.add(key)
        if has_jq and has_sy:     san.add(key)
    return single, san

# ── 核心：对每行独立统计保险公司出现次数 ──────────────────
def compute_buckets(keys, by_key, template_rows):
    """
    对每个模板行 (r3-r26)：
      1) 解析条件
      2) 过滤 (plate, vin) key 集合 (v8: 每行独立, 一车可计入多个匹配行)
      3) 取该 key 的首条 rec
      4) 拿保险公司简称 → counter

    v8 变更：删除 v6 引入的 `assigned` 全局集合, 恢复 v5 风格 (每行独立).
    业务语义: R3/R5/R6 通用维度 与 R7-R26 细分维度 正交, 一辆车在多个维度分别 +1.
    """
    out = {}  # row_num -> Counter(short_name)
    for spec in template_rows:
        r = spec['r']
        cond = spec['cond']
        if r in PLACEHOLDER_ROWS:
            out[r] = Counter()  # 占位行：空桶，触发 fill_via_zip 不写入
            continue
        filt = make_filter(cond)
        c = Counter()
        for key in keys:
            recs = by_key.get(key, [])
            if not recs: continue
            rec = recs[0]['row']
            if filt(rec):
                sn = short_name(str(rec[I_SN]).strip() if rec[I_SN] else '')
                if sn:
                    c[sn] += 1
        out[r] = c
    return out

# ── top8 排序 ────────────────────────────────────────────
def top8(counter):
    """按出现次数降序，相同次数按原顺序"""
    return [sn for sn, _ in counter.most_common(8)]

# ── 填充模板（zip 方式，保留样式） ────────────────────────
def fill_via_zip(tmpl_path, out_path, row_buckets):
    shutil.copy(tmpl_path, out_path)
    with zipfile.ZipFile(out_path, 'r') as zin:
        names = zin.namelist()
        files = {n: zin.read(n) for n in names}
    sheet = files['xl/worksheets/sheet1.xml'].decode('utf-8')

    for r, counter in sorted(row_buckets.items()):
        if r in PLACEHOLDER_ROWS:
            continue  # 占位行：模板上的 I-P 保持空白
        vals = top8(counter)
        for col_offset, val in enumerate(vals):
            sheet = _set_cell(sheet, r, 9 + col_offset, val)
        for col in range(9 + len(vals), 17):
            sheet = _set_cell(sheet, r, col, '')

    files['xl/worksheets/sheet1.xml'] = sheet.encode('utf-8')
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, files[name])

def _set_cell(sheet, row, col, value):
    ref = f'{get_column_letter(col)}{row}'
    m = re.search(rf'<c r="{re.escape(ref)}"([^>]*)/>', sheet)
    if m:
        sm = re.search(r'\bs="(\d+)"', m.group(1))
        sa = f' s="{sm.group(1)}"' if sm else ''
        return sheet[:m.start()] + \
            f'<c r="{ref}"{sa} t="inlineStr"><is><t>{value}</t></is></c>' + \
            sheet[m.end():]
    m = re.search(rf'<c r="{re.escape(ref)}"([^>]*)>(.*?)</c>', sheet, re.DOTALL)
    if m:
        sm = re.search(r'\bs="(\d+)"', m.group(1))
        sa = f' s="{sm.group(1)}"' if sm else ''
        return sheet[:m.start()] + \
            f'<c r="{ref}"{sa} t="inlineStr"><is><t>{value}</t></is></c>' + \
            sheet[m.end():]
    return sheet

# ── 主流程 ──────────────────────────────────────────────
def main():
    ib  = '/root/.openclaw/media/inbound'
    ws2 = '/root/.openclaw/workspace'
    sk  = '/root/.openclaw/workspace/skills/xianzhong-tuijian/assets'

    files = [f for f in os.listdir(ib) if f.endswith(('.xlsx', '.xls'))]
    if not files:
        print('数据文件不存在'); return
    files.sort(key=lambda f: os.path.getmtime(os.path.join(ib, f)))
    src = os.path.join(ib, files[-1])
    print(f'数据文件: {src}')

    by_key = load_data(src)
    single_keys, san_keys = classify(by_key)
    print(f'单交强: {len(single_keys)}辆 | 交三: {len(san_keys)}辆')

    # 读两份模板
    tpl_dj = os.path.join(sk, '单交保司推荐.xlsx')
    tpl_s3 = os.path.join(sk, '交三保司推荐.xlsx')
    tpl_rows_dj = parse_template(tpl_dj)
    tpl_rows_s3 = parse_template(tpl_s3)

    # 独立计算
    buckets_dj = compute_buckets(single_keys, by_key, tpl_rows_dj)
    buckets_s3 = compute_buckets(san_keys,    by_key, tpl_rows_s3)

    today = datetime.now().strftime('%Y-%m-%d')
    out1 = os.path.join(ws2, f'单交保司推荐_{today}.xlsx')
    out2 = os.path.join(ws2, f'交三保司推荐_{today}.xlsx')
    fill_via_zip(tpl_dj, out1, buckets_dj)
    fill_via_zip(tpl_s3, out2, buckets_s3)
    print(f'-> {out1}')
    print(f'-> {out2}')

    # 调试：打印每行命中数
    print('\n=== 调试：每行命中数 ===')
    for r in sorted(buckets_dj):
        total = sum(buckets_dj[r].values())
        top3 = top8(buckets_dj[r])[:3]
        print(f'  R{r:>2} (单交): {total:>4}辆 | top3: {top3}')
    print('---')
    for r in sorted(buckets_s3):
        total = sum(buckets_s3[r].values())
        top3 = top8(buckets_s3[r])[:3]
        print(f'  R{r:>2} (交三): {total:>4}辆 | top3: {top3}')

if __name__ == '__main__':
    main()
