@echo off
REM 每日 09:05 由 Windows 计划任务调用，重新抓取并加密 RMA 数据
cd /d "F:\work Buddy\2026-08-06-10-05-58"
"C:\Users\204\AppData\Local\Programs\Python\Python310\python.exe" "F:\work Buddy\2026-08-06-10-05-58\site\update.py" >> "F:\work Buddy\2026-08-06-10-05-58\update.log" 2>&1
