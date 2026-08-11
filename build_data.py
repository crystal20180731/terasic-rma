# -*- coding: utf-8 -*-
"""
把 rma_data_v4.csv 转换为加密的 data.enc，供前端用口令解密。
加密：AES-256-GCM + PBKDF2(SHA256, 200000 迭代)，与浏览器 Web Crypto API 兼容。
口令来源：环境变量 RMA_PW，或本项目根目录 secret.txt（该文件不入库）。
产物：site/data.enc
"""
import os, csv, json, sys, datetime, re
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "rma_data_v4.csv")
OUT = os.path.join(HERE, "data.enc")
ITER = 200000

def parse_date(s):
    s = (s or '').strip()
    if not s:
        return None
    for fmt in ('%Y.%m.%d', '%Y-%m-%d', '%Y/%m/%d'):
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
    """去掉维修报告开头的销售记录前缀，从『一、故障现象』开始。"""
    t = (text or '').strip()
    idx = t.find('一、故障现象')
    if idx > 0:
        t = t[idx:]
    return t

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
            "warranty": r["保固状态"].strip(),
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

    payload = {
        "updated": os.environ.get("RMA_UPDATED", ""),
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
    print(f"✓ 已加密写入 {OUT}")
    print(f"  记录数: {len(records)} | 保固待核: {len(mismatch)} | 年份: {meta['years'][0]}~{meta['years'][-1]}")
    print(f"  文件大小: {len(out)//1024} KB")

if __name__ == "__main__":
    main()
