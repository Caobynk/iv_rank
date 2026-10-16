#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""push_deploy.py — 推送部署（三级兜底 + 硬超时）

为什么要单独用 Python 做推送：
    本机 git-over-HTTPS 到 github.com 的 ref 协商会被链路切断，git 打印
    `expected flush after ref listing` 之后**进程不退出**（挂死）。
    在 cmd/bat 里没有可靠的命令超时手段，update.bat 因此会永久卡在直连 push，
    既报不出错也走不到兜底通道。Python 的 subprocess(timeout=...) 可以可靠
    杀死挂死进程，故把推送逻辑整体放在这里。

执行顺序（任一步成功即结束）：
    0. 预探测 git ls-remote（硬超时 40s）—— 协议已挂死时直接跳到 API 通道，省时
    1. 直连 git push（硬超时 120s）
    2. 代理 git push（硬超时 120s，代理地址取 deploy_proxy.txt）
    3. GitHub API 通道（.workbuddy/tools/_api_pub_all.py，内容级校验后发布）

退出码：0 = 已推送成功（或本来就没有待推送内容）；1 = 全部通道失败
"""
from __future__ import annotations

import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))          # 本脚本位于项目根目录
PY = os.path.join(BASE, 'venv', 'Scripts', 'python.exe')
# API 发布器优先取项目根目录，同时兼容旧位置 .workbuddy/tools/
API_PUB = os.path.join(BASE, '_api_pub_all.py')
if not os.path.isfile(API_PUB):
    API_PUB = os.path.join(BASE, '.workbuddy', 'tools', '_api_pub_all.py')

PROBE_TIMEOUT = 40      # ls-remote 预探测
PUSH_TIMEOUT = 120      # 单次 git push
API_TIMEOUT = 1800      # API 通道（文件多时较慢）

GIT_OPTS = [
    '-c', 'protocol.version=0',            # v2 协商需要额外 POST，本网络下会被切断
    '-c', 'http.sslBackend=schannel',
    '-c', 'http.schannelCheckRevoke=false',
    '-c', 'http.connectTimeout=15',
    '-c', 'http.postBuffer=524288000',
    '-c', 'http.lowSpeedLimit=1000',
    '-c', 'http.lowSpeedTime=45',
]


def log(msg: str = '') -> None:
    print(msg, flush=True)


def read_first_line(path: str) -> str:
    try:
        with open(path, encoding='utf-8') as f:
            return f.read().strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return ''


def run(cmd: list, timeout: int):
    """执行命令，返回 (returncode, 输出文本)。超时返回 124 并已杀进程。"""
    env = dict(os.environ)
    env['GIT_TERMINAL_PROMPT'] = '0'
    env['PYTHONIOENCODING'] = 'utf-8'
    try:
        r = subprocess.run(cmd, cwd=BASE, env=env, timeout=timeout,
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    except subprocess.TimeoutExpired as e:
        out = ''
        for part in (getattr(e, 'stdout', None), getattr(e, 'stderr', None)):
            if part:
                out += part if isinstance(part, str) else part.decode('utf-8', 'replace')
        return 124, out + f'\n[超时] 超过 {timeout}s，已终止（该通道判定为失败）'
    except FileNotFoundError as e:
        return 127, f'命令不存在: {e}'


def tail(text: str, n: int = 6) -> str:
    lines = [ln for ln in (text or '').splitlines() if ln.strip()]
    return '\n'.join('    ' + ln for ln in lines[-n:])


def main() -> int:
    token = read_first_line(os.path.join(BASE, 'deploy_token.txt')) or os.environ.get('GH_TOKEN', '')
    proxy = read_first_line(os.path.join(BASE, 'deploy_proxy.txt')) or os.environ.get('GH_PROXY', '')
    url_rewrite = ['-c', f'url.https://x-access-token:{token}@github.com/.insteadOf=https://github.com/'] if token else []

    log('=' * 56)
    log(' 推送部署（三级兜底 + 硬超时）')
    log(f'  token: {"已读取" if token else "未找到"}   代理: {proxy or "未配置"}')
    log('=' * 56)

    # ---- 待推送检查（本地 origin/main 记录每次发布后都会同步）-----------
    rc, out = run(['git', 'rev-list', '--count', 'origin/main..HEAD'], 30)
    if rc == 0 and out.strip().isdigit() and int(out.strip()) == 0:
        log('\n本地与 origin/main 一致，没有待推送提交 —— 跳过推送。')
        return 0

    # ---- 0. 预探测：git 协议是否健康 -------------------------------------
    log(f'\n[0/3] 探测 git 协议（ls-remote，超时 {PROBE_TIMEOUT}s）...')
    rc, out = run(['git', *GIT_OPTS, *url_rewrite, 'ls-remote', 'origin', 'HEAD'], PROBE_TIMEOUT)
    proto_ok = rc == 0
    log(f'      结果: {"协议可用" if proto_ok else f"不可用（rc={rc}）"}')
    if not proto_ok:
        log(tail(out, 3))

    # ---- 1. 直连 push -----------------------------------------------------
    if proto_ok:
        log(f'\n[1/3] 直连 git push（超时 {PUSH_TIMEOUT}s）...')
        rc, out = run(['git', *GIT_OPTS, *url_rewrite, 'push', 'origin', 'main'], PUSH_TIMEOUT)
        log('      ' + ('成功 ✓' if rc == 0 else f'失败（rc={rc}）'))
        if rc == 0:
            return 0
        log(tail(out))
    else:
        log('\n[1/3] 跳过直连 push（协议已不可用，避免挂死）')

    # ---- 2. 代理 push -----------------------------------------------------
    if proxy and proto_ok:
        log(f'\n[2/3] 代理 push（{proxy}，超时 {PUSH_TIMEOUT}s）...')
        rc, out = run(['git', *GIT_OPTS, '-c', f'http.proxy={proxy}', *url_rewrite,
                       'push', 'origin', 'main'], PUSH_TIMEOUT)
        log('      ' + ('成功 ✓' if rc == 0 else f'失败（rc={rc}）'))
        if rc == 0:
            return 0
        log(tail(out))
    elif proxy:
        log('\n[2/3] 跳过代理 push（协议不可用）')
    else:
        log('\n[2/3] 跳过代理 push（未配置代理）')

    # ---- 3. GitHub API 通道 ----------------------------------------------
    if not token:
        log('\n[ERROR] 无 token，无法使用 API 通道')
        return 1
    if not os.path.isfile(API_PUB):
        log(f'\n[ERROR] 未找到 API 发布脚本: {API_PUB}')
        return 1
    log(f'\n[3/3] GitHub API 通道（超时 {API_TIMEOUT}s）...')
    rc, out = run([PY, '-u', API_PUB], API_TIMEOUT)
    log('      ' + ('成功 ✓' if rc == 0 else f'失败（rc={rc}）'))
    log(tail(out, 8))
    return 0 if rc == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
