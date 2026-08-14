# -*- coding: utf-8 -*-
"""从原 RMA 系统抓取技术备注里上传的附件（图片/文档），按 RMA 编号存到本地 attachments/。

依赖：requests（pip install requests）
凭据：通过环境变量 TERASIC_USER / TERASIC_PASS 传入，不写盘。
产物：
  attachments/<RMA编号>/<文件名>        下载的原始文件
  attachments_index.json                RMA编号 -> [{name,type,mime}]，供 build_data.py 读取嵌入 data.enc

运行（cmd，项目目录下）：
  set TERASIC_USER=mycheng
  set "TERASIC_PASS=cmy#3gng"
  python scrape_attachments.py
"""
import os, re, sys, json
import requests

BASE = "http://office.terasic.com.tw"
LIST = BASE + "/cgi-bin/serena/rmareportall.pl"
USER = os.environ.get("TERASIC_USER")
PASS = os.environ.get("TERASIC_PASS")
if not USER or not PASS:
    print('✗ 请先设置环境变量：')
    print('    set TERASIC_USER=mycheng')
    print('    set "TERASIC_PASS=cmy#3gng"')
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
ATT_DIR = os.path.join(HERE, "attachments")
os.makedirs(ATT_DIR, exist_ok=True)

IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".bmp": "image/bmp", ".webp": "image/webp", ".tif": "image/tiff", ".tiff": "image/tiff",
    ".pdf": "application/pdf", ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain", ".zip": "application/zip", ".rar": "application/x-rar-compressed",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

def ext_of(name):
    _, e = os.path.splitext(name)
    return e.lower()

def mime_of(name):
    return MIME.get(ext_of(name), "application/octet-stream")

def resolve(u):
    if u.startswith("http"):
        return u
    if u.startswith("/"):
        return BASE + u
    return BASE + "/" + u.lstrip("./")

print("[1] 访问列表页并收集所有 RMA（含分页）...")
sess = requests.Session()
sess.auth = (USER, PASS)
sess.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

def get(url):
    return sess.get(url, timeout=60, auth=(USER, PASS))

rma_pairs = {}   # rmaNo -> siteNo
page = 1
while True:
    url = LIST if page == 1 else f"{LIST}?Page={page}"
    r = get(url)
    if r.status_code != 200:
        print(f"   列表页第 {page} 页失败：{r.status_code}")
        break
    pairs = re.findall(r"FnRmaNo=(\d+)&FnSiteNo=(\d+)", r.text)
    added = 0
    for rn, sn in pairs:
        if rn not in rma_pairs:
            rma_pairs[rn] = sn
            added += 1
    if f"Page={page + 1}" not in r.text:
        break
    if added == 0 and page > 1:
        break
    page += 1
    if page > 200:
        break
print(f"   共发现 {len(rma_pairs)} 条 RMA")

print("[2] 逐条扫描 view 页，抓取附件 ...")
index = {}          # rmaNo -> [{"name","type","mime"}]
total_files = 0
total_bytes = 0
for rn, sn in rma_pairs.items():
    vurl = f"{LIST}?Method=view&FnRmaNo={rn}&FnSiteNo={sn}"
    try:
        r = get(vurl)
    except Exception as e:
        print(f"   RMA={rn} view 页异常: {e}")
        continue
    if r.status_code != 200:
        continue
    # 真实附件：URL 含 /serena/attachment/rma_info/（排除系统图标、排除 deleteFile 控件）
    urls = re.findall(r'(?:href|src)="([^"]*attachment/rma_info/[^"#?]+)"', r.text)
    seen = set()
    atts = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        full = resolve(u)
        fn = requests.utils.unquote(u.rstrip("/").split("/")[-1])
        if not fn:
            continue
        atts.append((full, fn))
    if not atts:
        continue
    rdir = os.path.join(ATT_DIR, rn)
    os.makedirs(rdir, exist_ok=True)
    # 幂等：先清空该 RMA 目录里已有的旧附件，避免重复下载产生 _1/_2 堆积
    for old in os.listdir(rdir):
        old_path = os.path.join(rdir, old)
        if os.path.isfile(old_path):
            os.remove(old_path)
    recs = []
    for full, fn in atts:
        dest = os.path.join(rdir, fn)
        try:
            fr = sess.get(full, timeout=120, auth=(USER, PASS))
            if fr.status_code != 200:
                print(f"   RMA={rn} 下载失败 {fn}: HTTP {fr.status_code}")
                continue
            with open(dest, "wb") as f:
                f.write(fr.content)
            total_files += 1
            total_bytes += len(fr.content)
            et = ext_of(fn)
            recs.append({"name": os.path.basename(dest), "type": "image" if et in IMG_EXT else "file",
                         "mime": mime_of(fn)})
        except Exception as e:
            print(f"   RMA={rn} 下载异常 {fn}: {e}")
    if recs:
        index[rn] = recs

with open(os.path.join(HERE, "attachments_index.json"), "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, indent=2)

print(f"[完成] 共抓取 {total_files} 个附件，合计 {total_bytes // 1024} KB")
print(f"   涉及 {len(index)} 条 RMA 有附件")
print(f"   索引已写入 attachments_index.json")
