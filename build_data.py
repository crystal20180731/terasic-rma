# -*- coding: utf-8 -*-
"""
把 rma_data_v4.csv 转换为加密的 data.enc，供前端用口令解密。
加密：AES-256-GCM + PBKDF2(SHA256, 200000 迭代)，与浏览器 Web Crypto API 兼容。
口令来源：环境变量 RMA_PW，或本项目根目录 secret.txt（该文件不入库）。
产物：site/data.enc
"""
import os, csv, json, sys, datetime, re, base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "rma_data_v4.csv")
OUT = os.path.join(HERE, "data.enc")
ATT_DIR = os.path.join(HERE, "attachments")
INDEX_FILE = os.path.join(HERE, "attachments_index.json")
ITER = 200000
MAX_ATT_BYTES = 10 * 1024 * 1024   # 单文件超过 10MB 跳过，避免 data.enc 过大

def parse_date(s):
    s = (s or '').strip()
    if not s:
        return None
    for fmt in ('%Y.%m.%d', '%Y-%m-%d', '%Y/%m/%d', '%Y%m%d'):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None

def calc_warranty(ship, rma):
    """保固判定：报修日期 − 出货日期 > 90 天 为保外，否则保内。"""
    d_s = parse_date(ship)
    d_r = parse_date(rma)
    if not d_s or not d_r:
        return ''
    return '保外' if (d_r - d_s).days > 90 else '保内'

def check_flag(warranty, calc):
    """表单标注与 90 天推算不一致时标记。"""
    if not warranty or not calc:
        return ''
    return '' if warranty == calc else f"不符：表单{warranty}/推算{calc}"

def clean_report(text):
    """去掉维修报告开头的销售记录前缀，保留板卡序号（如 1. 17010028-0831），从『一、故障现象』开始。"""
    t = (text or '').strip()
    lines = t.split('\n')
    # 找到第一个包含『一、故障现象』的行
    start_idx = -1
    for i, line in enumerate(lines):
        if '一、故障现象' in line:
            start_idx = i
            break
    if start_idx <= 0:
        return t
    # 向前回溯，保留连续的板卡序号行（如 1. xxx / 2. xxx）
    keep_idx = start_idx
    for i in range(start_idx - 1, -1, -1):
        s = lines[i].strip()
        if re.match(r'^\d+\.\s+\S', s):
            keep_idx = i
        else:
            break
    return '\n'.join(lines[keep_idx:]).strip()

def clean_sales_note(text):
    """销售备注：截掉维修报告正文（『一、故障现象』起）及人工分隔标记（==/RMA-编号等），只留真正的销售信息。"""
    t = (text or '').strip()
    if not t:
        return ''
    # 1) 最高优先级：截掉维修报告正文
    idx = t.find('一、故障现象')
    if idx >= 0:
        t = t[:idx]
    if not t.strip():
        return ''
    # 2) 逐行扫描，遇分隔标记则从该行起截断
    keep = []
    for line in t.split('\n'):
        s = line.strip()
        if re.match(r'^=+$', s):               # 纯等号分隔行 ==
            break
        if re.match(r'^RMA-\w', s):             # 单独成行的 RMA- 编号
            break
        keep.append(line)
    return '\n'.join(keep).strip()

def load_att_index():
    """读取抓取脚本产出的 attachments_index.json：RMA编号 -> [{name,type,mime}]。"""
    if os.path.exists(INDEX_FILE):
        try:
            return json.load(open(INDEX_FILE, encoding="utf-8"))
        except Exception as e:
            print(f"  ⚠ 读取 attachments_index.json 失败：{e}")
    return {}

def build_attachments(att_index, rmaNo, rma):
    """把某条 RMA 的附件转成静态文件引用，供前端按需加载。"""
    key = (rmaNo or '').strip() or (rma or '').strip()
    recs = att_index.get(key) or []
    out = []
    for a in recs:
        path = os.path.join(ATT_DIR, key, a["name"])
        if not os.path.exists(path):
            continue
        try:
            size = os.path.getsize(path)
        except Exception as e:
            print(f"  ⚠ 读取附件失败 {path}：{e}")
            continue
        if size > MAX_ATT_BYTES:
            print(f"  ⚠ 跳过超大附件 {a['name']}（{size//1024//1024} MB）")
            continue
        out.append({
            "name": a["name"],
            "type": a.get("type", "file"),
            "mime": a.get("mime", "application/octet-stream"),
            "size": size,
            "url": f"attachments/{key}/{a['name']}",
        })
    return out

def get_password():
    pw = os.environ.get("RMA_PW")
    if pw:
        return pw
    secret = os.path.join(ROOT, "secret.txt")
    if os.path.exists(secret):
        return open(secret, encoding="utf-8").read().strip()
    print("✗ 找不到口令：请设置环境变量 RMA_PW 或在项目根目录建 secret.txt")
    sys.exit(1)

def main():
    pw = get_password()
    att_index = load_att_index()
    if att_index:
        print(f"   已加载附件索引：{len(att_index)} 条 RMA 含附件")
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    records = []
    for r in rows:
        calc = calc_warranty(r["出货日期"], r["report时间"])
        records.append({
            "rma": r["RMA完整号"].strip(),
            "rmaNo": r["RMA编号"].strip(),
            "site": r["站点"].strip(),
            "company": r["公司名称"].strip(),
            "contact": r["联系人"].strip(),
            "phone": r["电话"].strip(),
            "email": r["邮箱"].strip(),
            "address": r["客户地址"].strip(),
            "series": r["产品系列"].strip(),
            "product": r["产品明细"].strip(),
            "qty": r["数量"].strip(),
            "sn": r["序列号"].strip(),
            "warranty": calc if calc else r["保固状态"].strip(),
            "fee": r["维修费用"].strip(),
            "currency": r["币别"].strip(),
            "reportTime": r["report时间"].strip(),
            "year": r["年份"].strip(),
            "sales": r["业务人员"].strip(),
            "repairman": r["维修人员"].strip(),
            "stateRaw": r["状态原始"].strip(),
            "stateCat": r["状态分类"].strip(),
            "closed": r["是否结案"].strip(),
            "report": clean_report(r["维修报告全文"]),
            "noteSales": clean_sales_note(r["销售备注原文"]),
            "noteTech": r["技术备注"].strip(),
            "fault": r["故障类型"].strip(),
            "shipDate": r["出货日期"].strip(),
            "calcWarranty": calc,
            "warrantyBasis": r["保固判定依据"].strip(),
            "checkFlag": check_flag(r["保固状态"], calc),
            "attachments": build_attachments(att_index, r["RMA编号"].strip(), r["RMA完整号"].strip()),
        })

    # 去重下拉选项
    def distinct(field):
        s = sorted({rec[field] for rec in records if rec[field]})
        return s
    meta = {
        "companies": distinct("company"),
        "contacts": distinct("contact"),
        "products": distinct("product"),
        "series": distinct("series"),
        "sales": distinct("sales"),
        "faults": distinct("fault"),
        "states": distinct("stateCat"),
        "years": sorted({int(rec["year"]) for rec in records if rec["year"].isdigit()}),
    }
    mismatch = [rec for rec in records if rec["checkFlag"].startswith("不符")]

    updated_at = os.environ.get("RMA_UPDATED", "")
    if not updated_at:
        updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    payload = {
        "updated": updated_at,
        "count": len(records),
        "mismatchCount": len(mismatch),
        "records": records,
        "meta": meta,
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    salt = os.urandom(16)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER)
    key = kdf.derive(pw.encode("utf-8"))
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, raw, None)
    out = salt + nonce + ct
    with open(OUT, "wb") as f:
        f.write(out)
    att_total = sum(len(rec.get("attachments", [])) for rec in records)
    print(f"✓ 已加密写入 {OUT}")
    print(f"  记录数: {len(records)} | 保固待核: {len(mismatch)} | 年份: {meta['years'][0]}~{meta['years'][-1]}")
    print(f"  附件引用: {att_total} 个 | data.enc 大小: {len(out)//1024} KB")

if __name__ == "__main__":
    main()
