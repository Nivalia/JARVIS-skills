"""
build_template.py - 保司推荐表 模板 (16 列 × 38 行, 含 1 行标题)

v3 (2026-07-08 11:36): 颜色升级 + 顶部加标题
  - 顶部 R1 合并 A1:P1 = "保司推荐表 - 2026-07-09" (深蓝 18pt 粗体白字)
  - 原 12x37 全部下移 1 行 → 16x38 (R2 客车头, R3-R23 客车数据, R24 货车头, R25-R38 货车数据)
  - 调色板: 弃用苍白 pastel, 改用 Office 2010 中度饱和调色板
  - 边框: thin 黑色 → thin 浅灰 (#BFBFBF), 减少刺眼

v4 (2026-07-09): 推荐 8→10, 模板从 12 列扩到 14 列
  - 表头 R2/R24 扩 2 列 (推荐9, 推荐10)
  - 推荐区 E-N (10 列), 列宽循环 +2
  - 行数据填充 5..15, 标题合并 A1:N1

v5 (2026-07-09): 推荐 10→12, 模板从 14 列扩到 16 列
  - 表头 R2/R24 扩 2 列 (推荐11, 推荐12)
  - 推荐区 E-P (12 列), 列宽循环 +2
  - 行数据填充 5..17, 标题合并 A1:P1
"""
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OUT = '/root/.openclaw/workspace/skills/xianzhong-tuijian/assets/保司推荐表.xlsx'

# ── 调色板 (v10 IMA「配色」子文件夹 pei_98 单一来源) ─
# 设计: 6 段全部出自同一张色卡, 色系统一
# 提取方法: PIL 排除白底+黑底后, 像素聚类取主色
COLOR_TITLE_BG     = '301830'   # 标题深紫 (pei_98, Deep Plum)
COLOR_HEADER_BG    = 'A84860'   # 表头玫红 (pei_98, Rose)
COLOR_GENERAL_BG   = 'F0D8C0'   # 通用 米色 (pei_98, Sand)
COLOR_NEWENERGY_BG = 'A8C090'   # 新能源 草绿 (pei_98, Sage)
COLOR_FUEL_BG      = 'F0C0C0'   # 燃油/燃气 浅红 (pei_98, Blush)
COLOR_TRUCK_BG     = 'D8D8D8'   # 货车 浅灰 (pei_98, Mist)

# 行底色映射 (新行号, 含标题行)
ROW_COLOR = {}
# R1: 标题 (深蓝)
ROW_COLOR[1] = COLOR_TITLE_BG
# R2: 客车头 (中蓝)
ROW_COLOR[2] = COLOR_HEADER_BG
# R3-R5: 通用
for r in range(3, 6):   ROW_COLOR[r] = COLOR_GENERAL_BG
# R6-R8: 新能源
for r in range(6, 9):   ROW_COLOR[r] = COLOR_NEWENERGY_BG
# R9-R23: 燃油/燃气 (15 行)
for r in range(9, 24):  ROW_COLOR[r] = COLOR_FUEL_BG
# R24: 货车头 (中蓝)
ROW_COLOR[24] = COLOR_HEADER_BG
# R25-R38: 货车 (14 行)
for r in range(25, 39): ROW_COLOR[r] = COLOR_TRUCK_BG

# ── 边框 (浅灰替代纯黑) ──────────────────────────────
SIDE_THIN = Side(border_style='thin', color='BFBFBF')
BORDER_THIN = Border(left=SIDE_THIN, right=SIDE_THIN, top=SIDE_THIN, bottom=SIDE_THIN)

# ── 字体 ─────────────────────────────────────────────
FONT_TITLE   = Font(name='微软雅黑', size=18, bold=True, color='FFFFFF')
FONT_HEADER  = Font(name='微软雅黑', size=12, bold=True, color='FFFFFF')
FONT_BODY    = Font(name='微软雅黑', size=10, bold=False, color='000000')
FONT_BODY_B  = Font(name='微软雅黑', size=10, bold=True,  color='000000')

# ── 对齐 ─────────────────────────────────────────────
ALIGN_CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)

# ── 列宽 / 行高 ─────────────────────────────────────
COL_WIDTHS = {'A': 12, 'B': 12, 'C': 10, 'D': 12}
for c in 'EFGHIJKLMNOP':
    COL_WIDTHS[c] = 9

ROW_HEIGHTS = {
    1: 42,    # 标题
    2: 30,    # 客车头
    24: 30,   # 货车头
}
for r in list(range(3, 24)) + list(range(25, 39)):
    ROW_HEIGHTS[r] = 22

# ── 表头 (R2 客车, R24 货车) ─────────────────────
HEADER_KECHE = ['能源类型', '类别', '过户', '险种',
                '推荐1', '推荐2', '推荐3', '推荐4', '推荐5', '推荐6', '推荐7', '推荐8',
                '推荐9', '推荐10', '推荐11', '推荐12']
HEADER_HUOCHE = ['使用性质', '车型', '吨位', '险种',
                 '推荐1', '推荐2', '推荐3', '推荐4', '推荐5', '推荐6', '推荐7', '推荐8',
                 '推荐9', '推荐10', '推荐11', '推荐12']

# ── 客车区域 R3-R23 的 维度标签 (A, B, C, D) ─────
# 行号已 +1 (原 R2 → R3, 原 R22 → R23)
KECHE_LABELS = {
    3:  ('通用',     '行唐地址'),
    4:  (None,       '异地身份证'),
    5:  (None,       '25岁以下'),
    6:  ('新能源',   '单交'),
    7:  (None,       '交三'),
    8:  (None,       '交商'),
    9:  ('燃油/燃气', None,     '非过户', '单交'),
    10: (None,       None,       None,    '交三'),
    11: (None,       None,       None,    '交商'),
    12: (None,       None,       None,    '单商业'),
    13: (None,       '旧车',     '过户',   '单交'),
    14: (None,       None,       None,    '交三'),
    15: (None,       None,       None,    '交商'),
    16: (None,       None,       None,    '单商业'),
    17: (None,       '新车',     None,    '单交'),
    18: (None,       None,       None,    '交三'),
    19: (None,       None,       None,    '交商'),
    20: (None,       None,       None,    '单商业'),
    21: (None,       '企业车',   None,    '单交'),
    22: (None,       None,       None,    '交三'),
    23: (None,       None,       None,    '交商'),
}

# ── 货车区域 R25-R38 的 维度标签 ─────────────
HUOCHE_LABELS = {
    25: ('非营业', '普货', '2吨以下', '单交'),
    26: (None,     None,   None,     '联合单'),
    27: ('营业',   None,   None,     '单交'),
    28: (None,     None,   None,     '联合单'),
    29: ('非营业', '箱货', None,     '单交'),
    30: (None,     None,   None,     '联合单'),
    31: ('营业',   None,   None,     '单交'),
    32: (None,     None,   None,     '联合单'),
    33: ('非营业', '仓栏', None,     '单交'),
    34: (None,     None,   None,     '联合单'),
    35: ('营业',   None,   None,     '单交'),
    36: (None,     None,   None,     '联合单'),
    37: ('非营业', '多用途', None,   '不限'),
    38: ('自卸',   None,     None,   '不限'),
}

# ── 合并单元格 (新行号) ──────────────────────────
MERGES = [
    # 标题 (16 列: A1:P1)
    'A1:P1',
    # 客车
    'A3:A5',     # 通用
    'A6:A8',     # 新能源
    'A9:A23',    # 燃油/燃气
    'B3:D3', 'B4:D4', 'B5:D5',  # 通用 类别
    'B6:D6', 'B7:D7', 'B8:D8',  # 新能源 类别
    'B9:B16',                    # 旧车 (R9-R16, 8 行)
    'C9:C12', 'C13:C16',         # 非过户 / 过户
    'B17:B20',                   # 新车 (R17-R20, 4 行)
    'B21:B23',                   # 企业车 (R21-R23, 3 行)
    # 货车
    'A25:A26', 'A27:A28',        # 普货
    'A29:A30', 'A31:A32',        # 箱货
    'A33:A34', 'A35:A36',        # 仓栏
    'A38:B38',                   # 自卸 (R38)
    'B25:B28',                   # 普货 车型
    'B29:B32',                   # 箱货
    'B33:B36',                   # 仓栏
    'C25:C38',                   # 2吨以下 (整列 14 行)
]


def style_title(cell):
    cell.font = FONT_TITLE
    cell.fill = PatternFill('solid', fgColor=COLOR_TITLE_BG)
    cell.alignment = ALIGN_CENTER
    cell.border = BORDER_THIN


def style_header(cell):
    cell.font = FONT_HEADER
    cell.fill = PatternFill('solid', fgColor=COLOR_HEADER_BG)
    cell.alignment = ALIGN_CENTER
    cell.border = BORDER_THIN


def style_body(cell, bg, bold=False):
    cell.font = FONT_BODY_B if bold else FONT_BODY
    cell.fill = PatternFill('solid', fgColor=bg)
    cell.alignment = ALIGN_CENTER
    cell.border = BORDER_THIN


def write_header_row(ws, r, headers):
    for c, h in enumerate(headers, start=1):
        style_header(ws.cell(r, c, h))


def write_data_row(ws, r, labels_4):
    bg = ROW_COLOR[r]
    for c, label in enumerate(labels_4, start=1):
        cell = ws.cell(r, c)
        if label is not None:
            cell.value = label
        style_body(cell, bg, bold=(c == 1 and label is not None))
    # E-P 12 列空模板 (推荐区)
    for c in range(5, 17):
        cell = ws.cell(r, c)
        cell.fill = PatternFill('solid', fgColor=bg)
        cell.alignment = ALIGN_CENTER
        cell.border = BORDER_THIN
        cell.font = FONT_BODY


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Sheet'

    for c, w in COL_WIDTHS.items():
        ws.column_dimensions[c].width = w
    for r, h in ROW_HEIGHTS.items():
        ws.row_dimensions[r].height = h

    ws.freeze_panes = 'E3'

    # R1 标题
    style_title(ws['A1'])
    ws['A1'].value = '保司推荐表'

    # R2 客车头
    write_header_row(ws, 2, HEADER_KECHE)

    # R3-R23 客车数据
    for r in range(3, 24):
        labels = KECHE_LABELS[r] + (None,) * (4 - len(KECHE_LABELS[r]))
        write_data_row(ws, r, labels[:4])

    # R24 货车头
    write_header_row(ws, 24, HEADER_HUOCHE)

    # R25-R38 货车数据
    for r in range(25, 39):
        labels = HUOCHE_LABELS[r] + (None,) * (4 - len(HUOCHE_LABELS[r]))
        write_data_row(ws, r, labels[:4])

    for mr in MERGES:
        ws.merge_cells(mr)

    wb.save(OUT)
    print(f'-> {OUT}')
    print(f'   dims: {ws.dimensions}  merges: {len(MERGES)}  cols: 16  rows: 38 (含 1 行标题)')


if __name__ == '__main__':
    main()
