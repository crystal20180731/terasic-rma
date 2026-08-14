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

# 日志输出到 stdout，由 run_update.bat 负责重定向到文件。
# 避免 Python 自身打开 update.log 时因文件被锁而崩溃。
logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format="%(asctime)s %(message)s", encoding="utf-8")
log = logging.getLogger()

def run(script, cwd=ROOT):
    log.info("▶ 运行 %s", script)
    p = subprocess.run([PY, os.path.join(cwd, script)], cwd=cwd,
                       capture_output=True, text=True)
    for line in p.stdout.strip().splitlines()[-8:]:
        log.info("   %s", line)
    if p.returncode != 0:
        log.error("✗ %s 失败:\n%s", script, p.stderr[-500:])
        raise SystemExit(f"{script} 失败，详见 update.log")
    log.info("✓ %s 完成", script)

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
    log.info("▶ 重新加密数据")
    subprocess.run([PY, os.path.join(HERE, "build_data.py")], cwd=HERE, env=env, check=True)
    deploy_push(log)
    log.info("====== 每日更新完成 %s ======", today)

def deploy_push(log):
    """把更新后的 data.enc 与附件目录提交并推送到 GitHub（供 Cloudflare 自动部署）。
    若未配置 git 远程/凭据，或非交互环境（计划任务），则只生成提交但不硬推，避免卡住。"""
    try:
        # 非交互环境（计划任务）不自动 push，防止凭据弹窗无限等待
        if not sys.stdout.isatty():
            log.info("△ 非交互环境，跳过自动 push。data.enc 已更新，请手动执行 git push")
            return
        subprocess.run(["git", "-C", HERE, "add", "data.enc"], check=True, capture_output=True)
        subprocess.run(["git", "-C", HERE, "add", "--all", "attachments/"], check=True, capture_output=True)
        subprocess.run(["git", "-C", HERE, "commit", "-m", "daily RMA update"],
                       check=True, capture_output=True)
        r = subprocess.run(["git", "-C", HERE, "push"], capture_output=True, text=True)
        if r.returncode == 0:
            log.info("✓ 已推送到 GitHub，Cloudflare 将自动重新部署")
        else:
            log.warning("△ git push 未成功（可能未配置远程/凭据）：%s", r.stderr.strip()[:200])
    except Exception as e:
        log.warning("△ 自动推送跳过：%s", str(e)[:200])

if __name__ == "__main__":
    main()
