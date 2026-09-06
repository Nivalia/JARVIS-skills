"""
handler.py v2.2 - 适配 16 列 × 37 行 保司推荐表 (2026-07-09 推荐 10→12)

业务变化 (相对 v10):
  - 模板从 16 列 28 行 (单交/交三 两张表) 改为 16 列 38 行 (一张合并表)
  - 险种细分到 4 类 (客车) + 2 类 (货车):
      客车: 单交 / 交三 / 交商 / 单商业
      货车: 单交 / 联合单
  - 车辆使用性质 (非营业/营业) 显式维度 (货车)
  - 货车 2吨以下 显式过滤 (C24:C37 全段)
  - 险种分类需查 险别 列 (42) 判车损

v2.1 (2026-07-09 指挥官确认):
  - 推荐 Top8 → Top10, 表头新增"推荐9 / 推荐10"
  - 模板列数 12 → 14 (推荐区 E-N)
  - 标题合并 A1:L1 → A1:N1

v2.2 (2026-07-09 指挥官确认):
  - 推荐 Top10 → Top12, 表头新增"推荐11 / 推荐12"
  - 模板列数 14 → 16 (推荐区 E-P)
  - 标题合并 A1:N1 → A1:P1

数据列 (自动探测, 0-based):
  I_SN=6 保险公司 | I_PLATE=12 车牌号 | I_VIN=30 车架号
  I_CHEX=34 车辆种类 | I_MODEL=31 车辆型号 | I_LOAD=36 核载质量(吨)
  I_SHIYO=29 车辆使用性质 | I_NENG=44 能源种类 | I_CHUAN=38 车船税
  I_ZHONG=40 险种 | I_GUO=25 过户 | I_NEW=27 新旧车 | I_REGD=26 初始登记
  I_CERT=28 发证日期
  I_AGE_I=15 投保人年龄 | I_AGE_H=20 被保人年龄 | I_AGE_O=23 车主年龄
  I_ADDR_I=17 投保人地址 | I_ADDR_H=21 被保人地址 | I_ADDR_O=24 车主地址
  I_ID_I=16 投保人证件号 | I_ID_H=19 被保人证件号 | I_ID_O=22 车主证件号
  I_XIANBIE=42 险别 (含车损判定)
"""
import os, re, shutil, zipfile
from datetime import datetime, date
import openpyxl
from openpyxl.utils import get_column_letter
from collections import defaultdict, Counter

# ── 列索引 (运行时由 detect_columns 覆盖) ────────
I_SN, I_PLATE, I_VIN, I_CHEX, I_MODEL, I_LOAD = 6, 12, 30, 34, 31, 36
I_SHIYO, I_NENG, I_CHUAN, I_ZHONG, I_GUO, I_NEW = 29, 44, 38, 40, 25, 27
I_REGD, I_CERT, I_XIANBIE = 26, 28, 42
I_AGE_I, I_AGE_H, I_AGE_O = 15, 20, 23
I_ADDR_I, I_ADDR_H, I_ADDR_O = 17, 21, 24
I_ID_I, I_ID_H, I_ID_O = 16, 19, 22

# ── v10 列自动探测 ──────────────────────────────
COLUMN_MAP = {
    '保险公司':           'I_SN',
    '车牌号':             'I_PLATE',
    '车架号':             'I_VIN',
    '车辆种类':           'I_CHEX',
    '车辆型号':           'I_MODEL',
    '核载质量':           'I_LOAD',
    '车辆使用性质':       'I_SHIYO',
    '能源种类':           'I_NENG',
    '车船税':             'I_CHUAN',
    '险种':               'I_ZHONG',
    '过户车辆标志':       'I_GUO',
    '新旧车标志':         'I_NEW',
    '车辆初始登记日期':   'I_REGD',
    '发证日期':           'I_CERT',
    '投保人年龄':         'I_AGE_I',
    '被保人年龄':         'I_AGE_H',
    '车主年龄':           'I_AGE_O',
    '投保人地址':         'I_ADDR_I',
    '被保人地址':         'I_ADDR_H',
    '车主地址':           'I_ADDR_O',
    '投保人证件号':       'I_ID_I',
    '被保人证件号':       'I_ID_H',
    '车主证件号':         'I_ID_O',
    '险别':               'I_XIANBIE',
}


def detect_columns(src):
    wb = openpyxl.load_workbook(src, data_only=True)
    ws = wb.active
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    wb.close()
    norm = [str(h).strip() if h is not None else '' for h in headers]
    result = {}
    missing = []
    for key, name in COLUMN_MAP.items():
        idx = None
        for i, h in enumerate(norm):
            if h.startswith(key):
                idx = i
                break
        if idx is None:
            missing.append(key)
        else:
            result[name] = idx
    if missing:
        raise ValueError(f'表头缺少关键列: {", ".join(missing)} | 实际表头: {norm}')
    return result, norm


# ── 工具 ────────────────────────────────────────
def short_name(s):
    s = str(s).strip()
    for suf in ('财险', '保险', '在线', '联合'):
        s = re.sub(rf'{suf}$', '', s)
    return s


def parse_age(val):
    if not val: return None
    m = re.search(r'(\d+)岁', str(val))
    return int(m.group(1)) if m else None


def min_age(rec):
    ages = [parse_age(rec[i]) for i in (I_AGE_I, I_AGE_H, I_AGE_O)]
    ages = [a for a in ages if a is not None]
    return min(ages) if ages else None


def is_new_car(rec):
    flag = str(rec[I_NEW]).strip() if rec[I_NEW] else ''
    if flag in ('新车', '是'): return True
    if flag in ('旧车', '否'): return False
    reg = str(rec[I_REGD]).strip() if rec[I_REGD] else ''
    if not reg: return True
    try:
        r = datetime.strptime(reg[:10], '%Y-%m-%d').date()
        return (date.today() - r).days < 274
    except: return True


def is_guo_car(rec):
    flag = str(rec[I_GUO]).strip() if rec[I_GUO] else ''
    if flag == '是': return True
    if flag == '否': return False
    reg = str(rec[I_REGD]).strip() if rec[I_REGD] else ''
    cert = str(rec[I_CERT]).strip() if rec[I_CERT] else ''
    if not reg or not cert: return False
    if reg == cert: return False
    try:
        r = datetime.strptime(reg[:10], '%Y-%m-%d').date()
        c = datetime.strptime(cert[:10], '%Y-%m-%d').date()
        return (c - r).days < 365
    except: return False


def is_xin(rec):
    """新能源: 能源种类非 燃油/燃气; 兑底 险种含交强 + 车船税=0"""
    neng = str(rec[I_NENG]).strip() if rec[I_NENG] is not None else ''
    if neng != '':
        return neng not in ('燃油', '燃气')
    zhong = str(rec[I_ZHONG]).strip() if rec[I_ZHONG] is not None else ''
    if '交强' in zhong:
        chuanshui = rec[I_CHUAN] if I_CHUAN < len(rec) else None
        try:
            v = float(chuanshui) if chuanshui not in (None, '') else None
            if v == 0: return True
            elif v is not None and v > 0: return False
        except (ValueError, TypeError): pass
    return False


def truck_sub(model):
    s = str(model) if model else ''
    if '厢式' in s or '封闭式' in s: return '箱货'
    if '仓栅' in s or '仓栏' in s: return '仓栏'
    if '自卸' in s: return '自卸'
    if '多用途' in s: return '多用途'
    return '普货'


def load_lt_2(rec):
    v = rec[I_LOAD]
    if v is None: return True
    try:
        t = float(v)
        if t > 40: t = t / 1000
        return t < 2
    except: return True


# ── 车辆分类 (per vehicle, 合并该车所有 险种/险别 记录) ──
def classify_vehicle(recs):
    """
    返回 dict {
        'xianzhong_kc': '单交'|'交三'|'交商'|'单商业'|None,
        'xianzhong_hc': '单交'|'联合单'|None,
        'is_xin': bool, 'is_xingyong': bool, 'is_qiye': bool,
        'truck_sub': str|None,
        'is_guo': bool, 'is_new': bool,
        'min_age': int|None, 'is_xt': bool, 'is_yd_id': bool,
        'first_sn': str,  # 短公司名
    }
    """
    zhon_set = set()
    has_chs = False
    for r in recs:
        if I_ZHONG < len(r) and r[I_ZHONG] is not None:
            zhon_set.add(str(r[I_ZHONG]).strip())
        if I_XIANBIE < len(r) and r[I_XIANBIE] is not None:
            xb = str(r[I_XIANBIE])
            if '车损' in xb or '机动车损失保险' in xb:
                has_chs = True

    has_jq = '交强险' in zhon_set
    has_sy = '商业险' in zhon_set

    # 客车 险种
    if has_jq and not has_sy:           xianzhong_kc = '单交'
    elif has_jq and has_sy and not has_chs: xianzhong_kc = '交三'
    elif has_jq and has_sy and has_chs: xianzhong_kc = '交商'
    elif has_sy and not has_jq:         xianzhong_kc = '单商业'
    else:                               xianzhong_kc = None

    # 货车 险种
    if has_jq and not has_sy:           xianzhong_hc = '单交'
    elif has_jq and has_sy and has_chs: xianzhong_hc = '联合单'
    else:                               xianzhong_hc = None

    r0 = recs[0]
    shiyo = str(r0[I_SHIYO]).strip() if r0[I_SHIYO] else ''
    is_xingyong = ('营业' in shiyo) and ('家庭' not in shiyo) and ('非营业' not in shiyo)
    is_qiye = '非营业企业' in shiyo
    is_xin_flag = is_xin(r0)
    is_guo_flag = is_guo_car(r0)
    is_new_flag = is_new_car(r0)
    min_age_val = min_age(r0)
    is_xt_flag = any('行唐' in str(r0[i]) for i in (I_ADDR_I, I_ADDR_H, I_ADDR_O) if r0[i] is not None) or \
                  any(str(r0[i])[:6] == '130125' for i in (I_ID_I, I_ID_H, I_ID_O) if r0[i] is not None)
    id_i = str(r0[I_ID_I]).strip() if r0[I_ID_I] else ''
    is_yd_id_flag = len(id_i) >= 4 and not id_i.startswith('1301')
    chex = str(r0[I_CHEX]).strip() if r0[I_CHEX] else ''
    model = str(r0[I_MODEL]).strip() if r0[I_MODEL] else ''
    truck_sub_val = truck_sub(model) if chex == '货车' else None
    load_lt_2_val = load_lt_2(r0)

    return {
        'xianzhong_kc': xianzhong_kc,
        'xianzhong_hc': xianzhong_hc,
        'has_jq': has_jq,
        'has_sy': has_sy,
        'is_xin': is_xin_flag,
        'is_xingyong': is_xingyong,
        'is_qiye': is_qiye,
        'truck_sub': truck_sub_val,
        'is_guo': is_guo_flag,
        'is_new': is_new_flag,
        'min_age': min_age_val,
        'is_xt': is_xt_flag,
        'is_yd_id': is_yd_id_flag,
        'load_lt_2': load_lt_2_val,
        'first_sn': short_name(str(r0[I_SN]).strip() if r0[I_SN] else ''),
    }


# ── 行 → 过滤 映射 (35 行, 客车 21 + 货车 14) ─────
def is_kc(v):
    return True  # 客车/货车 过滤在外层 classify 时区分

def is_fuel(v):
    return not v['is_xin']  # 燃油/燃气 = 非新能源

def ROW_FILTERS():
    """
    返回 dict {row_num: filter_func(vehicle_dict) -> bool}

    行号是模板的绝对行号 (v3 起 含 1 行标题在 R1, 原数据行 +1):
      客车:  R3-R23 (原 R2-R22)
      货车:  R25-R38 (原 R24-R37)
    """
    f = {}
    # ── 客车 R3-R23 ─────────────────────
    f[3]  = lambda v: v['is_xt']
    f[4]  = lambda v: v['is_yd_id']
    f[5]  = lambda v: v['min_age'] is not None and v['min_age'] < 25
    # 新能源 (无过户/无新旧细分, 单纯 险种)
    f[6]  = lambda v: v['is_xin'] and v['xianzhong_kc'] == '单交'
    f[7]  = lambda v: v['is_xin'] and v['xianzhong_kc'] == '交三'
    f[8]  = lambda v: v['is_xin'] and v['xianzhong_kc'] == '交商'
    # 燃油/燃气 旧车 非过户 (R9-R12)
    f[9]  = lambda v: is_fuel(v) and not v['is_new'] and not v['is_guo'] and v['xianzhong_kc'] == '单交'
    f[10] = lambda v: is_fuel(v) and not v['is_new'] and not v['is_guo'] and v['xianzhong_kc'] == '交三'
    f[11] = lambda v: is_fuel(v) and not v['is_new'] and not v['is_guo'] and v['xianzhong_kc'] == '交商'
    f[12] = lambda v: is_fuel(v) and not v['is_new'] and not v['is_guo'] and v['xianzhong_kc'] == '单商业'
    # 燃油/燃气 旧车 过户 (R13-R16)
    f[13] = lambda v: is_fuel(v) and not v['is_new'] and v['is_guo']     and v['xianzhong_kc'] == '单交'
    f[14] = lambda v: is_fuel(v) and not v['is_new'] and v['is_guo']     and v['xianzhong_kc'] == '交三'
    f[15] = lambda v: is_fuel(v) and not v['is_new'] and v['is_guo']     and v['xianzhong_kc'] == '交商'
    f[16] = lambda v: is_fuel(v) and not v['is_new'] and v['is_guo']     and v['xianzhong_kc'] == '单商业'
    # 燃油/燃气 新车 (R17-R20)
    f[17] = lambda v: is_fuel(v) and v['is_new']                          and v['xianzhong_kc'] == '单交'
    f[18] = lambda v: is_fuel(v) and v['is_new']                          and v['xianzhong_kc'] == '交三'
    f[19] = lambda v: is_fuel(v) and v['is_new']                          and v['xianzhong_kc'] == '交商'
    f[20] = lambda v: is_fuel(v) and v['is_new']                          and v['xianzhong_kc'] == '单商业'
    # 燃油/燃气 企业车 (R21-R23)
    f[21] = lambda v: is_fuel(v) and v['is_qiye']                         and v['xianzhong_kc'] == '单交'
    f[22] = lambda v: is_fuel(v) and v['is_qiye']                         and v['xianzhong_kc'] == '交三'
    f[23] = lambda v: is_fuel(v) and v['is_qiye']                         and v['xianzhong_kc'] == '交商'

    # ── 货车 R25-R38 (需 2吨以下) ──────────
    # 普货 (R25-R28)
    f[25] = lambda v: v['truck_sub'] == '普货' and not v['is_xingyong'] and v['load_lt_2'] and v['xianzhong_hc'] == '单交'
    f[26] = lambda v: v['truck_sub'] == '普货' and not v['is_xingyong'] and v['load_lt_2'] and v['xianzhong_hc'] == '联合单'
    f[27] = lambda v: v['truck_sub'] == '普货' and v['is_xingyong']     and v['load_lt_2'] and v['xianzhong_hc'] == '单交'
    f[28] = lambda v: v['truck_sub'] == '普货' and v['is_xingyong']     and v['load_lt_2'] and v['xianzhong_hc'] == '联合单'
    # 箱货 (R29-R32)
    f[29] = lambda v: v['truck_sub'] == '箱货' and not v['is_xingyong'] and v['load_lt_2'] and v['xianzhong_hc'] == '单交'
    f[30] = lambda v: v['truck_sub'] == '箱货' and not v['is_xingyong'] and v['load_lt_2'] and v['xianzhong_hc'] == '联合单'
    f[31] = lambda v: v['truck_sub'] == '箱货' and v['is_xingyong']     and v['load_lt_2'] and v['xianzhong_hc'] == '单交'
    f[32] = lambda v: v['truck_sub'] == '箱货' and v['is_xingyong']     and v['load_lt_2'] and v['xianzhong_hc'] == '联合单'
    # 仓栏 (R33-R36)
    f[33] = lambda v: v['truck_sub'] == '仓栏' and not v['is_xingyong'] and v['load_lt_2'] and v['xianzhong_hc'] == '单交'
    f[34] = lambda v: v['truck_sub'] == '仓栏' and not v['is_xingyong'] and v['load_lt_2'] and v['xianzhong_hc'] == '联合单'
    f[35] = lambda v: v['truck_sub'] == '仓栏' and v['is_xingyong']     and v['load_lt_2'] and v['xianzhong_hc'] == '单交'
    f[36] = lambda v: v['truck_sub'] == '仓栏' and v['is_xingyong']     and v['load_lt_2'] and v['xianzhong_hc'] == '联合单'
    # 多用途/自卸 (不限 险种 = 交强/商业 任一即算)
    f[37] = lambda v: v['truck_sub'] == '多用途' and not v['is_xingyong'] and v['load_lt_2'] and (v['has_jq'] or v['has_sy'])
    f[38] = lambda v: v['truck_sub'] == '自卸'   and not v['is_xingyong'] and v['load_lt_2'] and (v['has_jq'] or v['has_sy'])
    return f


# ── 数据加载 & 车辆分类 ─────────────────────
def load_data(src, exclude_sns=None):
    """读源 xlsx, 按 (车牌, 车架) 去重. 黑名单保司的记录在去重前剔除.

    Returns:
        (by_key, excluded_cnt) — 去重字典与剔除记录数
    """
    if exclude_sns is None:
        exclude_sns = EXCLUDE_SNS
    wb = openpyxl.load_workbook(src, data_only=True)
    ws = wb.active
    by_key = {}
    excluded_cnt = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row: continue
        # 黑名单保司剔除 (使用 short_name 后的简称匹配, 例: 前海财险 -> 前海)
        sn_raw = str(row[I_SN]).strip() if row[I_SN] else ''
        if exclude_sns and short_name(sn_raw) in exclude_sns:
            excluded_cnt += 1
            continue
        plate = str(row[I_PLATE]).strip() if row[I_PLATE] else ''
        vin   = str(row[I_VIN]).strip()   if row[I_VIN]   else ''
        if not plate or not vin: continue
        by_key.setdefault((plate, vin), []).append(row)
    return by_key, excluded_cnt


# 保司后置名单 (2026-07-08 指挥官新增规则: 出现则自动置末)
PUSH_BACK = {'人保', '平安'}

# 保司黑名单 (2026-07-09 指挥官确认): 这些保司的车辆不参与推荐计算
# 记录在 load_data() 阶段从源 xlsx 里直接剔除
EXCLUDE_SNS = {'前海'}


def top12(counter):
    """
    Top12 推荐, 人保/平安 出现时自动置末 (其他保原顺序)。

    业务规则 (2026-07-08 指挥官): 只要人保/平安在数据中, 它们一定在结果中, 且在末位。
    算法:
      1. most_common() 拉出全部
      2. 拆为 P (人保/平安) 与 M (其他)
      3. 预留 |P| 个末位给 P, 剩余 (12-|P|) 个头位给 M
      4. 结果 = M[:12-|P|] + P[:|P|]
    边界:
      - P 0 个 → 原 top12 (向后填充 12 个 M)
      - M 0 个 → 只 P
      - |P| > 12 → 只取前 12 个 P (按原计次)
    """
    items = counter.most_common()
    P = [(n, c) for n, c in items if n in PUSH_BACK]
    M = [(n, c) for n, c in items if n not in PUSH_BACK]
    p_slots = min(len(P), 12)
    m_slots = 12 - p_slots
    result = M[:m_slots] + P[:p_slots]
    return [n for n, _ in result]


# 兼容旧调用 (handler.py 老代码 / 引用过 top8 / top10 的脚本)
top8  = top12
top10 = top12


def compute_buckets(by_key, filters):
    """
    对每行: 遍历所有车辆, 过滤, 累计 first_sn.
    """
    # 先分类所有车辆
    vehicles = []
    for key, recs in by_key.items():
        v = classify_vehicle(recs)
        vehicles.append(v)

    out = {}
    for r, filt in filters.items():
        c = Counter()
        for v in vehicles:
            if filt(v):
                sn = v['first_sn']
                if sn: c[sn] += 1
        out[r] = c
    return out, len(vehicles)


# ── 填充模板 (zip-level 改 sheet1.xml) ───────────
def _set_cell(sheet, ref, value, style_attr=''):
    """替换已有单元格"""
    m = re.search(rf'<c r="{re.escape(ref)}"([^>]*?)/>', sheet)
    if m:
        return sheet[:m.start()] + \
            f'<c r="{ref}"{style_attr} t="inlineStr"><is><t>{value}</t></is></c>' + \
            sheet[m.end():]
    m = re.search(rf'<c r="{re.escape(ref)}"([^>]*?)>(.*?)</c>', sheet, re.DOTALL)
    if m:
        return sheet[:m.start()] + \
            f'<c r="{ref}"{style_attr} t="inlineStr"><is><t>{value}</t></is></c>' + \
            sheet[m.end():]
    return sheet


def fill_via_zip(tmpl_path, out_path, row_buckets):
    shutil.copy(tmpl_path, out_path)
    with zipfile.ZipFile(out_path, 'r') as zin:
        names = zin.namelist()
        files = {n: zin.read(n) for n in names}
    sheet = files['xl/worksheets/sheet1.xml'].decode('utf-8')

    # 抓 E2 样式作参考 (E-L 列各 cell 套同一行样式)
    e2_style = ''
    m = re.search(r'<c r="E2"([^>]*?)>', sheet)
    if m:
        sm = re.search(r'\bs="(\d+)"', m.group(1))
        if sm: e2_style = f' s="{sm.group(1)}"'

    for r, counter in sorted(row_buckets.items()):
        vals = top12(counter)
        for col_offset, val in enumerate(vals):
            ref = f'{get_column_letter(5 + col_offset)}{r}'
            sheet = _set_cell(sheet, ref, val, e2_style)
        for col in range(5 + len(vals), 17):  # E-P = 12 列
            ref = f'{get_column_letter(col)}{r}'
            sheet = _set_cell(sheet, ref, '', e2_style)

    files['xl/worksheets/sheet1.xml'] = sheet.encode('utf-8')
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, files[name])


# ── 主流程 ────────────────────────────────────
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

    cols, headers = detect_columns(src)
    # 覆盖模块级常量
    for k, v in cols.items():
        globals()[k] = v
    print(f'列探测: 险种={I_ZHONG} 险别={I_XIANBIE} 能源={I_NENG} 核载={I_LOAD} 车辆种类={I_CHEX}')

    by_key, excluded = load_data(src)
    if excluded:
        print(f'去重车辆: {len(by_key)} 辆 (黑名单剔除 {excluded} 条记录: {sorted(EXCLUDE_SNS)})')
    else:
        print(f'去重车辆: {len(by_key)} 辆')

    filters = ROW_FILTERS()
    row_buckets, veh_total = compute_buckets(by_key, filters)
    print(f'分类车辆: {veh_total} 辆')

    today = datetime.now().strftime('%Y-%m-%d')
    tpl = os.path.join(sk, '保司推荐表.xlsx')
    out = os.path.join(ws2, f'保司推荐表_{today}.xlsx')
    fill_via_zip(tpl, out, row_buckets)
    print(f'-> {out}')

    # 调试
    print('\n=== 调试: 每行命中数 + Top3 ===')
    for r in sorted(row_buckets):
        c = row_buckets[r]
        total = sum(c.values())
        t3 = top12(c)[:3]
        print(f'  R{r:>2}: {total:>4} 辆 | top3: {t3}')


if __name__ == '__main__':
    main()
