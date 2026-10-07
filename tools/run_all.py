#!/usr/bin/env python3
"""
One-command LOCAL demo launcher. Starts the corridor server, the ambulance
agent, and (unless --phone) the bench route-player, waits for each, prints the
URLs, and shuts them all down cleanly on Ctrl-C.

Assumes deps are installed in the component venvs (server/.venv,
ambulance-unit/.venv). Run from the project root:

    python3 tools/run_all.py            # desk demo (route-player drives GPS)
    python3 tools/run_all.py --phone    # use a phone's browser GPS instead
"""
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def venv_py(sub: str) -> str:
    p = ROOT / sub / ".venv" / "bin" / "python"
    return str(p) if p.exists() else sys.executable


def wait_health(url: str, timeout: float = 25.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> None:
    phone = "--phone" in sys.argv
    procs = []
    try:
        print("starting corridor server on :4000 …")
        procs.append(subprocess.Popen(
            [venv_py("server"), "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "4000"],
            cwd=str(ROOT / "server")))
        if not wait_health("http://127.0.0.1:4000/health"):
            print("!! server did not come up — check `pip install -r server/requirements.txt`")
            raise SystemExit(1)

        print("server up. starting ambulance agent …")
        procs.append(subprocess.Popen([venv_py("ambulance-unit"), "main.py"],
                                      cwd=str(ROOT / "ambulance-unit" / "agent")))
        time.sleep(3)

        if not phone:
            print("starting bench route-player (real Chennai route → agent GPS) …")
            procs.append(subprocess.Popen([venv_py("ambulance-unit"), "route_player.py"],
                                          cwd=str(ROOT / "tools")))

        print("\n  ────────────────────────────────────────────")
        print("  Ops map:     http://localhost:4000/")
        print("  Call-taker:  http://localhost:4000/console")
        if phone:
            print("  Dashboard:   npm run dev in ambulance-unit/dashboard, open on the phone")
        print("  Dispatch  13.0809, 80.2757  in /console, then watch the ops map.")
        print("  Ctrl-C to stop everything.")
        print("  ────────────────────────────────────────────\n")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nshutting down …")
    finally:
        for p in reversed(procs):
            try:
                p.terminate()
            except Exception:
                pass
        for p in reversed(procs):
            try:
                p.wait(timeout=5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
