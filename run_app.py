from __future__ import annotations

import os
import signal
import socket
import sys
import tempfile
import threading
import time
import webbrowser
from contextlib import suppress

from streamlit import config as st_config
from streamlit.web import bootstrap

_APP_LOCK_HANDLE = None
_LOCK_PATH = os.path.join(tempfile.gettempdir(), "engenharia_clinica_app.lock")


def resolve_app_path() -> str:
    candidates: list[str] = []

    # One-file builds usually extract data files here.
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = getattr(sys, "_MEIPASS")
        candidates.append(os.path.join(meipass, "app.py"))

    # One-dir builds may keep app.py next to executable.
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "app.py"))

    # Source mode (python run_app.py).
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"))

    # Current working directory fallback.
    candidates.append(os.path.join(os.getcwd(), "app.py"))

    for path in candidates:
        if os.path.exists(path):
            return path

    raise FileNotFoundError(f"Nao foi possivel localizar app.py. Tentativas: {candidates}")


def kill_port_holder(port: int, wait: float = 2.0) -> None:
    """Encerra qualquer processo que esteja ocupando *port*."""
    import subprocess

    if os.name == "nt":
        try:
            out = subprocess.check_output(
                ["netstat", "-aon", "-p", "TCP"], text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and f":{port}" in parts[1] and parts[3] == "LISTENING":
                    pid = int(parts[4])
                    if pid > 0 and pid != os.getpid():
                        with suppress(Exception):
                            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    else:
        try:
            out = subprocess.check_output(
                ["lsof", "-ti", f":{port}"], text=True, stderr=subprocess.DEVNULL
            ).strip()
            for raw_pid in out.split():
                pid = int(raw_pid)
                if pid > 0 and pid != os.getpid():
                    with suppress(Exception):
                        os.kill(pid, signal.SIGTERM)
        except Exception:
            pass

    deadline = time.time() + wait
    while time.time() < deadline:
        if is_port_available(port):
            return
        time.sleep(0.2)


def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def choose_port(preferred: int = 3000, max_tries: int = 200) -> int:
    for offset in range(max_tries):
        candidate = preferred + offset
        if is_port_available(candidate):
            return candidate
    raise RuntimeError(
        f"Nao foi encontrada porta livre entre {preferred} e {preferred + max_tries - 1}."
    )


def acquire_single_instance_lock() -> bool:
    global _APP_LOCK_HANDLE

    lock_file = open(_LOCK_PATH, "a+", encoding="utf-8")

    try:
        if os.name == "nt":
            import msvcrt

            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        with suppress(Exception):
            lock_file.close()
        return False

    lock_file.seek(0)
    lock_file.truncate(0)
    lock_file.write(str(os.getpid()))
    lock_file.flush()
    _APP_LOCK_HANDLE = lock_file
    return True


def restart_existing_instance_from_lock(wait_seconds: float = 2.0) -> bool:
    if not os.path.exists(_LOCK_PATH):
        return False

    try:
        with open(_LOCK_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
        existing_pid = int(content)
    except Exception:
        return False

    if existing_pid <= 0 or existing_pid == os.getpid():
        return False

    with suppress(Exception):
        os.kill(existing_pid, signal.SIGTERM)

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if acquire_single_instance_lock():
            return True
        time.sleep(0.15)

    return False


def open_browser_when_ready(url: str, delay_seconds: float = 1.5) -> None:
    def _open() -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(url)  # type: ignore[attr-defined]
                return
        except Exception:
            pass

        try:
            webbrowser.open(url, new=2)
        except Exception:
            # Nao interrompe inicializacao caso o navegador nao possa ser aberto.
            pass

    timer = threading.Timer(delay_seconds, _open)
    timer.daemon = True
    timer.start()


def main() -> None:
    app_path = resolve_app_path()
    preferred_port = int(os.environ.get("ENG_CLINICA_PORT", "3001"))
    port_scan = int(os.environ.get("ENG_CLINICA_PORT_SCAN", "200"))
    external_mode = os.environ.get("ENG_CLINICA_EXTERNAL", "0") == "1"
    source_mode = not getattr(sys, "frozen", False)

    if not acquire_single_instance_lock():
        if source_mode and restart_existing_instance_from_lock():
            print("Instancia anterior reiniciada para carregar a versao mais recente do codigo.")
        else:
            open_browser_when_ready(f"http://127.0.0.1:{preferred_port}", delay_seconds=0.2)
            print("Aplicacao ja esta em execucao. Reutilizando a instancia existente.")
            return

    print(f"Iniciando app usando: {app_path}")

    if not is_port_available(preferred_port):
        print(f"Porta {preferred_port} ocupada. Encerrando processo anterior...")
        kill_port_holder(preferred_port)

    port = choose_port(preferred=preferred_port, max_tries=max(1, port_scan))

    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"

    st_config.set_option("browser.gatherUsageStats", False)
    st_config.set_option("client.toolbarMode", "minimal")
    st_config.set_option("ui.hideTopBar", True)
    st_config.set_option("global.developmentMode", False)
    st_config.set_option("server.headless", external_mode)
    st_config.set_option("server.address", "0.0.0.0" if external_mode else "127.0.0.1")
    st_config.set_option("server.port", port)
    st_config.set_option("server.enableCORS", False if external_mode else True)
    st_config.set_option("server.enableXsrfProtection", False if external_mode else True)

    if not external_mode:
        open_browser_when_ready(f"http://127.0.0.1:{port}")

    bootstrap.run(app_path, is_hello=False, args=[], flag_options={})


if __name__ == "__main__":
    main()
