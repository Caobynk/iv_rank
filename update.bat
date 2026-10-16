@echo off
setlocal
cd /d D:\WorkBuddy\GithubToPages

REM ============================================================
REM  update.bat - Commodity Options Dashboard data fetch + build + push
REM  Steps:
REM   1. ensure venv (create + install deps on first run)
REM   2. fetch latest data from exchanges (update_data.py, ~10-15 min)
REM   3. rebuild static site from fresh data (build_site.py, ~2 min)
REM   4. git commit (only when static/ actually changed)
REM   5. push: .workbuddy\tools\push_deploy.py (probe, direct, proxy, API)
REM  Site: https://iv-rank.caobynk.workers.dev/
REM ============================================================

echo ==========================================================
echo  Commodity Options Dashboard - data update + deploy
echo  ETA: fetch 10-15 min + build 2 min (first run adds install)
echo ==========================================================
echo.

REM step 0: pick python for venv creation (managed 3.13 preferred)
set PYLAUNCH=python
if exist C:\Users\DELL\.workbuddy\binaries\python\versions\3.13.12\python.exe (
  set PYLAUNCH=C:\Users\DELL\.workbuddy\binaries\python\versions\3.13.12\python.exe
)

REM step 1: ensure venv exists, create and install deps if missing
if not exist venv\Scripts\python.exe (
  echo.
  echo ==========================================================
  echo  [1/5] Creating venv + installing dependencies on first run...
  echo ==========================================================
  "%PYLAUNCH%" -m venv venv
  venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
) else (
  echo.
  echo  [1/5] venv ready, skip install.
)

REM step 2: fetch latest data from exchanges
echo.
echo ==========================================================
echo  [2/5] Fetching latest data from exchanges (10-15 min)...
echo ==========================================================
echo   - overview : 5 exchange daily data
echo   - oi_dist  : 5 exchange option contracts
echo   - vol_hist : volatility from Excel (no network)
echo   - pcr      : incremental PCR + rebuild tables
echo   - gex      : all-variety market quotes
echo.
venv\Scripts\python.exe update_data.py
if errorlevel 1 (
  echo.
  echo  [WARN] update_data.py reported failures.
  echo  Continuing with build using existing cache...
  echo  some varieties may fall back to older data
)

REM step 3: rebuild static site
echo.
echo ==========================================================
echo  [3/5] Rebuilding static site (~2 min)...
echo ==========================================================
venv\Scripts\python.exe build_site.py
if errorlevel 1 (
  echo build_site.py failed, abort
  pause
  exit /b 1
)

REM step 4: commit new snapshots only if they actually changed
echo.
echo ==========================================================
echo  [4/5] Committing changes...
echo ==========================================================
git add static
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "data update %date%"
  echo  committed.
) else (
  echo  nothing changed, skip commit.
)

REM step 5: push local commits to origin
echo.
echo ==========================================================
echo  [5/5] Pushing to GitHub...
echo ==========================================================
REM The push logic now lives in .workbuddy\tools\push_deploy.py, because cmd
REM has no reliable command timeout and this machine's git smart-protocol can
REM HANG after "expected flush after ref listing" - that froze this batch at
REM step 5 with no error output. The script runs, in order and each with a
REM hard timeout: skip-if-nothing-to-push, git-protocol probe, direct push,
REM proxy push, GitHub API channel. So this batch can no longer hang.
venv\Scripts\python.exe -u push_deploy.py
if errorlevel 1 (
  echo.
  echo [ERROR] push failed - site NOT updated.
  echo  Read the channel results printed above to see which step failed.
  pause
  exit /b 1
)
goto PUSH_OK

:PUSH_OK
echo.
echo ==========================================================
echo  Push succeeded. Cloudflare will rebuild automatically.
echo  Site: https://iv-rank.caobynk.workers.dev/
echo ==========================================================
echo.
pause

endlocal
