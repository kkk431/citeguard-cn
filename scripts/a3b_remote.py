"""Tiny SSH/SFTP helper for the A3b GPU host (paramiko, password auth).

Connection details never live in the repo: export them first.

    export A3B_HOST=... A3B_USER=... A3B_PASS=...
    python scripts/a3b_remote.py run "nvidia-smi --query-gpu=index,memory.used --format=csv,noheader"
    python scripts/a3b_remote.py put local.tar.gz /data1/GYX/citeguard/a3b/local.tar.gz
    python scripts/a3b_remote.py get /data1/GYX/citeguard/a3b/out/metrics.json out/metrics.json

`run` streams stdout/stderr and exits with the remote exit code.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import paramiko


def connect(timeout: int = 20) -> paramiko.SSHClient:
    host, user, password = os.environ.get("A3B_HOST"), os.environ.get("A3B_USER"), os.environ.get("A3B_PASS")
    if not (host and user and password):
        raise SystemExit("set A3B_HOST / A3B_USER / A3B_PASS")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, timeout=timeout)
    return client


def run(client: paramiko.SSHClient, command: str, timeout: int = 3600) -> int:
    _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    chan = stdout.channel
    while True:
        while chan.recv_ready():
            sys.stdout.write(chan.recv(65536).decode("utf-8", "replace"))
            sys.stdout.flush()
        while chan.recv_stderr_ready():
            sys.stdout.write(chan.recv_stderr(65536).decode("utf-8", "replace"))
            sys.stdout.flush()
        if chan.exit_status_ready() and not chan.recv_ready() and not chan.recv_stderr_ready():
            break
        if chan.closed:
            break
        time.sleep(0.05)
    return chan.recv_exit_status()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("run", "put", "get"))
    ap.add_argument("args", nargs="+")
    args = ap.parse_args()
    client = connect()
    try:
        if args.action == "run":
            return run(client, " ".join(args.args))
        sftp = client.open_sftp()
        if args.action == "put":
            local, remote = args.args[0], args.args[1]
            sftp.put(str(Path(local)), remote)
            print(f"put {local} -> {remote} ({Path(local).stat().st_size} B)")
        else:
            remote, local = args.args[0], args.args[1]
            Path(local).parent.mkdir(parents=True, exist_ok=True)
            sftp.get(remote, str(local))
            print(f"get {remote} -> {local} ({Path(local).stat().st_size} B)")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
