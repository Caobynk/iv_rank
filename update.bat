@echo off
setlocal
cd /d D:\WorkBuddy\IV_Rank

REM step 1: ensure venv exists, create and install deps if missing
if not exist venv\Scripts\python.exe (
  python -m venv venv
  venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)

REM step 2: regenerate static snapshots from Excel
venv\Scripts\python.exe build_data.py
if errorlevel 1 (
  echo build_data.py failed, abort
  pause
  exit /b 1
)

REM step 3: commit new snapshots only if they actually changed
git add static/api
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "data update %date%"
)

REM step 4: push local commits to origin
REM also pushes commits committed earlier but failed to push (no false "deploy" message)
set TOKEN=
if exist deploy_token.txt (
  set /p TOKEN=<deploy_token.txt
) else (
  if defined GH_TOKEN set TOKEN=%GH_TOKEN%
)
set PROXY=
if exist deploy_proxy.txt (
  set /p PROXY=<deploy_proxy.txt
) else (
  if defined GH_PROXY set PROXY=%GH_PROXY%
)
if not "%TOKEN%"=="" (
  if not "%PROXY%"=="" (
    git -c http.proxy=%PROXY% -c "url.https://%TOKEN%@github.com/.insteadOf=https://github.com/" push origin main
  ) else (
    git -c "url.https://%TOKEN%@github.com/.insteadOf=https://github.com/" push origin main
  )
) else (
  if not "%PROXY%"=="" (
    git -c http.proxy=%PROXY% push origin main
  ) else (
    git push origin main
  )
)
if errorlevel 1 (
  echo [ERROR] push failed - site NOT updated. Check deploy_token.txt / GH_TOKEN or network.
  pause
  exit /b 1
)
echo Push done. Cloudflare Pages rebuilds automatically if changes were sent.

endlocal
