# -*- coding: utf-8 -*-
"""
把 rma_data_v4.csv 转换为加密的 data.enc，供前端用口令解密。
加密：AES-256-GCM + PBKDF2(SHA256, 200000 迭代)，与浏览器 Web Crypto API 兼容。
口令来源：环境变量 RMA_PW，或本项目根目录 secret.txt（该文件不入库）。
产物：site/data.enc
"""
import os, csv, json, sys
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "rma_data_v4.csv")
OUT = os.path.join(HERE, "data.enc")
ITER = 200000

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
            "report": r["维修报告全文"].strip(),
            "noteSales": r["销售备注原文"].strip(),
            "noteTech": r["技术备注"].strip(),
            "fault": r["故障类型"].strip(),
            "shipDate": r["出货日期"].strip(),
            "calcWarranty": r["推算保固"].strip(),
            "warrantyBasis": r["保固判定依据"].strip(),
            "checkFlag": r["校验标记"].strip(),
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
