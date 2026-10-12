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
REM   5. push: hardened git push, then proxy, then GitHub API channel
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
REM Hardening notes - what each piece protects against:
REM   for /f token read  : strips the trailing CR that set /p can leave in the token
REM   x-access-token:    : the plain https://TOKEN@host form can hang, use this form
REM   protocol.version=0 : skips the protocol v2 negotiation round-trip; when the
REM                        network cuts it git dies with
REM                        "expected flush after ref listing"
REM   schannel + revoke off + connectTimeout + lowSpeed guards: keep TLS working
REM                        and stop a stalled transfer from hanging forever
REM   API channel last   : publishes the same content when the git protocol is cut
set TOKEN=
if exist deploy_token.txt (
  for /f "usebackq delims=" %%a in ("deploy_token.txt") do set "TOKEN=%%a"
) else (
  if defined GH_TOKEN set "TOKEN=%GH_TOKEN%"
)
set GIT_TERMINAL_PROMPT=0
set GITFLAGS=-c protocol.version=0 -c http.sslBackend=schannel -c http.schannelCheckRevoke=false -c http.connectTimeout=15 -c http.postBuffer=524288000 -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=45

REM informational probe: is the API fallback channel usable right now?
set API200=0
if not "%TOKEN%"=="" (
  for /f %%c in ('curl -s -o nul -w "%%{http_code}" --ssl-no-revoke --max-time 20 -H "Authorization: Bearer %TOKEN%" https://api.github.com/repos/Caobynk/iv_rank') do set API200=%%c
)
echo  Probe - GitHub API reachable: %API200%

echo Pushing to GitHub via system network...
if not "%TOKEN%"=="" (
  git %GITFLAGS% -c "url.https://x-access-token:%TOKEN%@github.com/.insteadOf=https://github.com/" push origin main
) else (
  git %GITFLAGS% push origin main
)
if not errorlevel 1 goto PUSH_OK

echo Direct push failed - trying proxy fallback...
set PROXY=
if exist deploy_proxy.txt (
  for /f "usebackq delims=" %%a in ("deploy_proxy.txt") do set "PROXY=%%a"
) else (
  if defined GH_PROXY set "PROXY=%GH_PROXY%"
)
if not "%PROXY%"=="" (
  echo  Using proxy: %PROXY%
  if not "%TOKEN%"=="" (
    git %GITFLAGS% -c http.proxy=%PROXY% -c "url.https://x-access-token:%TOKEN%@github.com/.insteadOf=https://github.com/" push origin main
  ) else (
    git %GITFLAGS% -c http.proxy=%PROXY% push origin main
  )
  if not errorlevel 1 goto PUSH_OK
) else (
  echo  No proxy configured - skipped.
)

echo Git push failed - falling back to the GitHub API channel...
venv\Scripts\python.exe -u .workbuddy\tools\_api_pub_all.py
if not errorlevel 1 goto PUSH_OK

echo [ERROR] push failed - site NOT updated. Check deploy_token.txt / GH_TOKEN or network.
pause
exit /b 1

:PUSH_OK
echo.
echo ==========================================================
echo  Push succeeded. Cloudflare will rebuild automatically.
echo  Site: https://iv-rank.caobynk.workers.dev/
echo ==========================================================
echo.
pause

endlocal
