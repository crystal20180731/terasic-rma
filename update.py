# -*- coding: utf-8 -*-
"""
每日更新：重新抓取 RMA -> 抓取附件 -> 重建清洗数据 -> 重新加密 -> 生成 data.enc
由 Windows 计划任务在每天 09:05 调用（run_update.bat）。
仅抓取新增工单（已缓存的明细复用），速度快；如需全量刷新先删 details_cache_link/。
"""
import os, sys, subprocess, datetime, logging

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable

# 强制 stdout/stderr 为 UTF-8，避免计划任务（GBK 环境）下中文日志编码崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 日志输出到 stdout，由 run_update.bat 负责重定向到文件。
logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format="%(asctime)s %(message)s", encoding="utf-8")
log = logging.getLogger()

def run(script, cwd=ROOT):
    log.info("[RUN] %s", script)
    p = subprocess.run([PY, os.path.join(cwd, script)], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (p.stdout or "").strip()
    for line in out.splitlines()[-8:]:
        log.info("   %s", line)
    if p.returncode != 0:
        log.error("[FAIL] %s:\n%s", script, p.stderr[-500:])
        raise SystemExit(f"{script} 失败，详见 update.log")
    log.info("[OK] %s", script)

def main():
    os.chdir(ROOT)
    today = datetime.date.today().strftime("%Y-%m-%d")
    log.info("====== 每日更新开始 %s ======", today)
    run("fetch_rma.py")              # 刷新列表 rma_data.csv
    run("fetch_enrich_v3.py")        # 抓取新增明细到 details_cache_link
    run("build_v4.py")               # 重建 rma_data_v4.csv
    run("scrape_attachments.py", HERE)  # 抓取技术备注附件（在 site 子目录）
    # 重新加密
    pw = open(os.path.join(ROOT, "secret.txt"), encoding="utf-8").read().strip()
    env = dict(os.environ, RMA_PW=pw, RMA_UPDATED=today)
    log.info("[RUN] build_data.py")
    subprocess.run([PY, os.path.join(HERE, "build_data.py")], cwd=HERE, env=env, check=True)
    deploy_push(log)
    log.info("====== 每日更新完成 %s ======", today)

def deploy_push(log):
    """自动提交并推送 data.enc 与附件到 GitHub（Cloudflare 自动部署）。
    计划任务环境带超时保护；GitHub 凭据已通过 Windows 凭据管理器缓存，无需交互。"""
    try:
        subprocess.run(["git", "-C", HERE, "add", "data.enc", "attachments/"],
                       check=True, capture_output=True, timeout=120)
        # 无变化时 commit 会失败，忽略即可
        c = subprocess.run(["git", "-C", HERE, "commit", "-m", "daily RMA update"],
                           capture_output=True, text=True, timeout=120)
        if c.returncode != 0:
            log.info("[SKIP] 无内容变化，跳过提交")
        p = subprocess.run(["git", "-C", HERE, "push"], capture_output=True, text=True, timeout=300)
        if p.returncode == 0:
            log.info("[OK] 已推送到 GitHub，Cloudflare 将自动重新部署")
        else:
            log.warning("[WARN] git push 未成功（可能凭据未缓存）：%s", p.stderr.strip()[:200])
    except subprocess.TimeoutExpired:
        log.warning("[WARN] git push 超时（>300s），请手动推送")
    except Exception as e:
        log.warning("[WARN] 自动推送跳过：%s", str(e)[:200])

if __name__ == "__main__":
    main()
