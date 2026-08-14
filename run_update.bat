@echo off
REM 每日 09:05 由 Windows 计划任务调用，重新抓取并加密 RMA 数据
REM 工作目录切换到当前项目根，再调用 terasic-rma 子目录的 update.py
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "F:\work Buddy\2026-08-10-16-26-40\terasic-rma"
set TERASIC_USER=mycheng
set "TERASIC_PASS=cmy#3gng"
"C:\Users\204\AppData\Local\Programs\Python\Python310\python.exe" "F:\work Buddy\2026-08-10-16-26-40\terasic-rma\update.py" > "F:\work Buddy\2026-08-10-16-26-40\terasic-rma\update.log" 2>&1
