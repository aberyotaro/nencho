#!/usr/bin/env python3
"""設定ファイルの値を forms/ の様式PDFに書き込み、out/ に保存する。

使い方: python3 nencho.py [設定ファイル]（省略時は config.toml）
"""
import os, sys

if sys.version_info < (3, 11):
    sys.exit("エラー: Python 3.11 以上が必要です（tomllib を使うため）。run.sh 経由で実行してください。")
import tomllib

try:
    import pymupdf
except ImportError:
    sys.exit("エラー: PyMuPDF が見つかりません。./run.sh から実行してください。")

HERE = os.path.dirname(os.path.abspath(__file__))
FORM_FUYO = os.path.join(HERE, "forms", "R9_fuyo_kojo.pdf")
FORM_KISO = os.path.join(HERE, "forms", "R8_kiso_kojo.pdf")
OUT_DIR = os.path.join(HERE, "out")
OUT_FUYO = "令和9年分扶養控除等申告書.pdf"
OUT_KISO = "令和8年分基礎控除申告書等.pdf"
BUNDLED_FONT = os.path.join(HERE, "fonts", "BIZUDPGothic-Regular.ttf")
MAC_FONTS = [  # 同梱フォントが無いときに使う。.ttc は先頭の書体を使う
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]
INK = (0.05, 0.1, 0.45)
ERAS = {"明治": "明", "大正": "大", "昭和": "昭", "平成": "平", "令和": "令",
        "明": "明", "大": "大", "昭": "昭", "平": "平", "令": "令"}

def kyuyo_shotoku_r8(a: int) -> int:
    """令和8年分 基礎控除申告書 裏面「【参考】給与所得金額の計算方法」の表。"""
    if a <= 740_999: return 0
    if a <= 2_190_999: return a - 740_000
    if a <= 2_192_999: return 1_451_000
    if a <= 2_195_999: return 1_453_000
    if a <= 2_199_999: return 1_456_000
    q = (a // 4) // 1000 * 1000  # ÷4（千円未満切捨て）
    if a <= 3_599_999: return int(q * 2.8 - 80_000)
    if a <= 6_599_999: return int(q * 3.2 - 440_000)
    if a <= 8_499_999: return int(a * 0.9 - 1_100_000)
    return a - 1_950_000

# 表面「控除額の計算」表: (合計所得の上限(以下), 基礎控除額)
KISO_TABLE = [(4_890_000, 1_040_000), (6_550_000, 670_000), (9_000_000, 620_000),
              (9_500_000, 620_000), (10_000_000, 620_000), (23_500_000, 620_000),
              (24_000_000, 480_000), (24_500_000, 320_000), (25_000_000, 160_000)]
KISO_CHECK_Y = [229, 242.5, 256, 269.5, 283, 296.5, 310, 323.5, 337]  # 判定欄 □ の上端

def kiso_kojo(total: int):
    for i, (lim, amt) in enumerate(KISO_TABLE):
        if total <= lim: return i, amt
    return None, 0

REQUIRED = [
    ("payer", "name", "給与の支払者の名称"), ("payer", "address", "給与の支払者の所在地"),
    ("office", "zeimusho", "所轄税務署"), ("office", "shikuchoson", "市区町村"),
    ("employee", "name", "氏名"), ("employee", "furigana", "フリガナ"),
    ("employee", "birth_era", "生年月日の元号"), ("employee", "birth_y", "生年月日の年"),
    ("employee", "birth_m", "生年月日の月"), ("employee", "birth_d", "生年月日の日"),
    ("employee", "address", "住所"), ("employee", "head_of_household", "世帯主の氏名"),
    ("employee", "relation", "続柄"), ("employee", "has_spouse", "配偶者の有無"),
    ("income", "salary_revenue", "給与の収入金額"),
]

def load_config(path):
    if not os.path.exists(path):
        sys.exit(f"エラー: 設定ファイルが見つかりません: {path}")
    try:
        with open(path, "rb") as f: c = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        sys.exit(f"エラー: config.toml の書き方に誤りがあります（\"\" の閉じ忘れ等）: {e}")
    errs = []
    def g(sec, key): return c.get(sec, {}).get(key, "")
    for sec, key, label in REQUIRED:
        v = g(sec, key)
        if v is None or (isinstance(v, str) and v.strip() == ""):
            errs.append(f"  ・{label}（[{sec}] {key}）が空欄です")
    e = c.setdefault("employee", {})
    if str(e.get("birth_era", "")).strip() and str(e["birth_era"]).strip() not in ERAS:
        errs.append("  ・生年月日の元号は 明治/大正/昭和/平成/令和 のいずれかで書いてください")
    for k, lab, lo, hi in [("birth_y", "年", 1, 64), ("birth_m", "月", 1, 12), ("birth_d", "日", 1, 31)]:
        v = str(e.get(k, "")).strip()
        if v and not (v.isdigit() and lo <= int(v) <= hi):
            errs.append(f"  ・生年月日の{lab}は数字で書いてください（{lo}〜{hi}）: {v!r}")
    if str(e.get("has_spouse", "")).strip() not in ("", "有", "無"):
        errs.append("  ・配偶者の有無は 有 か 無 で書いてください")
    p = str(e.get("postal", "")).strip().replace("－", "-").replace("ー", "-")
    if p and not (len(p) == 8 and p[3] == "-" and (p[:3] + p[4:]).isdigit()):
        errs.append(f"  ・郵便番号は 123-4567 の形で書いてください: {p!r}")
    e["postal"] = p
    inc = c.setdefault("income", {})
    for k, lab in [("salary_revenue", "給与の収入金額"), ("other_income", "給与以外の所得")]:
        v = inc.get(k, 0 if k == "other_income" else "")
        if v == "" and k == "other_income": v = 0
        if v != "" and not (isinstance(v, int) and v >= 0):
            errs.append(f"  ・{lab}は 0 以上の整数（\"\"やカンマなし）で書いてください: {v!r}")
        inc[k] = v
    if errs:
        sys.exit("config.toml を確認してください:\n" + "\n".join(errs))
    return c

class Pen:
    def __init__(self, font_path):
        self.path = font_path
        self.font = pymupdf.Font(fontfile=font_path)
    def put(self, page, rect, text, size=10, align="left", min_size=5):
        text = str(text).strip()
        if not text: return
        x0, y0, x1, y1 = rect
        s = min(size, (y1 - y0) * 0.9)
        while self.font.text_length(text, fontsize=s) > (x1 - x0) and s > min_size: s -= 0.25
        if self.font.text_length(text, fontsize=s) > (x1 - x0):
            print(f"注意: 「{text}」が欄に収まりきりません。出力を確認してください。")
        w = self.font.text_length(text, fontsize=s)
        x = {"left": x0, "right": x1 - w, "center": (x0 + x1 - w) / 2}[align]
        page.insert_text((x, (y0 + y1) / 2 + s * 0.36), text, fontsize=s,
                         fontname="jpfont", fontfile=self.path, color=INK)

def circle(page, cx, cy, r): page.draw_circle((cx, cy), r, color=INK, width=0.8)

def check(page, x0, y0, x1, y1):
    sh = page.new_shape()
    sh.draw_polyline([(x0 + 0.8, (y0 + y1) / 2), ((x0 + x1) / 2 - 0.3, y1 - 0.8), (x1 + 0.6, y0 - 0.4)])
    sh.finish(color=INK, width=1.1, closePath=False); sh.commit()

def yen(n): return f"{n:,}"

def fill_fuyo(pen, page, c):
    P, O, E = c["payer"], c["office"], c["employee"]
    pen.put(page, (31, 51, 97, 69), O["zeimusho"], 10, "center")      # 所轄税務署長
    pen.put(page, (31, 85, 97, 101), O["shikuchoson"], 10, "center")  # 市区町村長
    pen.put(page, (172, 34, 328, 63), P["name"], 11)
    pen.put(page, (172, 90, 328, 114), P["address"], 9)
    pen.put(page, (389, 33.5, 533, 43), E["furigana"], 7.5)
    pen.put(page, (389, 45, 533, 64), E["name"], 12)
    era = {"明": (582.6, 36.9), "大": (592.7, 36.9), "昭": (602.9, 36.9),
           "平": (582.6, 42.7), "令": (592.7, 42.7)}[ERAS[str(E["birth_era"]).strip()]]
    circle(page, *era, 3.3)
    pen.put(page, (606, 34, 627, 46), E["birth_y"], 10, "right")
    pen.put(page, (637, 34, 658, 46), E["birth_m"], 10, "right")
    pen.put(page, (667, 34, 686, 46), E["birth_d"], 10, "right")
    pen.put(page, (582, 49, 695, 64), E["head_of_household"], 10)
    pen.put(page, (582, 67, 695, 87), E["relation"], 10)
    if E["postal"]:
        pen.put(page, (423, 88, 441, 98), E["postal"][:3], 8, "center")
        pen.put(page, (450, 88, 478, 98), E["postal"][4:], 8, "center")
    pen.put(page, (389, 100, 627, 115), E["address"], 10)
    circle(page, *((669.7, 100.8) if E["has_spouse"].strip() == "有" else (685.3, 100.8)), 5.2)
    # 個人番号、扶養親族、障害者等、住民税の欄は書かない。従たる給与の欄に○がなければ主たる給与になる

def fill_kiso(pen, page, c):
    P, O, E, I = c["payer"], c["office"], c["employee"], c["income"]
    pen.put(page, (58, 54, 104, 80), O["zeimusho"], 10, "center")     # 所轄税務署長
    pen.put(page, (189, 39, 351, 55.5), P["name"], 10)
    pen.put(page, (189, 76, 351, 93.5), P["address"], 9)
    pen.put(page, (417, 38.5, 652, 49.5), E["furigana"], 7.5)
    pen.put(page, (417, 51, 652, 74), E["name"], 12)
    pen.put(page, (417, 76, 652, 93.5), E["address"], 10)
    a, other = I["salary_revenue"], I["other_income"]
    inc = kyuyo_shotoku_r8(a); total = inc + other
    pen.put(page, (140, 143, 208, 164), yen(a), 10, "right")
    pen.put(page, (222, 145, 303, 164), yen(inc), 10, "right")
    pen.put(page, (222, 175, 303, 191), yen(other), 10, "right")
    pen.put(page, (222, 194, 302, 212), yen(total), 10.5, "right")
    row, amt = kiso_kojo(total)
    if row is not None:
        y = KISO_CHECK_Y[row]; check(page, 83, y, 88.5, y + 8)
        pen.put(page, (246, 290, 305, 309), yen(amt), 11, "right")
    # 区分Ⅰ、配偶者控除等、特定親族、所得金額調整控除の欄は書かない
    return a, inc, total, amt

def pick_font(c):
    fp = str(c.get("options", {}).get("font_path", "")).strip()
    if fp:
        fp = os.path.expanduser(fp)
        if not os.path.exists(fp): sys.exit(f"エラー: font_path のフォントが見つかりません: {fp}")
        return fp
    for f in [BUNDLED_FONT] + MAC_FONTS:
        if os.path.exists(f): return f
    sys.exit("エラー: 日本語フォントが見つかりません。config.toml の font_path を指定してください。")

def main():
    cfg = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "config.toml")
    c = load_config(cfg)
    for f in (FORM_FUYO, FORM_KISO):
        if not os.path.exists(f): sys.exit(f"エラー: 様式PDFが見つかりません: {f}")
    pen = Pen(pick_font(c))
    os.makedirs(OUT_DIR, exist_ok=True)
    result = None
    for src, out, fn in [(FORM_FUYO, OUT_FUYO, fill_fuyo), (FORM_KISO, OUT_KISO, fill_kiso)]:
        doc = pymupdf.open(src)
        r = fn(pen, doc[0], c)
        if r: result = r
        path = os.path.join(OUT_DIR, out)
        doc.save(path, garbage=3, deflate=True)
        print("作成:", path)
    a, inc, total, amt = result
    print(f"\n給与の収入金額 {a:,}円 → 給与所得 {inc:,}円 / 合計所得金額 {total:,}円 / 基礎控除 {amt:,}円")
    print("out/ のPDFを開いて内容を確認してください。マイナンバー欄は空欄です。")

if __name__ == "__main__":
    main()
