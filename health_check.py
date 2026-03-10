from __future__ import annotations

import importlib
import py_compile
import socket
import sys
from pathlib import Path


def run_check(name: str, ok: bool, details: str, failures: list[str]) -> None:
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {name}: {details}")
    if not ok:
        failures.append(name)


def main() -> int:
    root = Path(__file__).resolve().parent
    failures: list[str] = []

    print("=== Health Check | Engenharia Clinica ===")
    print(f"Projeto: {root}")

    required_files = [
        root / "app.py",
        root / "run_app.py",
        root / "requirements.txt",
        root / ".streamlit" / "config.toml",
    ]
    for file_path in required_files:
        run_check(
            name=f"Arquivo {file_path.name}",
            ok=file_path.exists(),
            details=str(file_path),
            failures=failures,
        )

    for module_name in ["pandas", "streamlit", "plotly", "openpyxl"]:
        try:
            importlib.import_module(module_name)
            run_check(
                name=f"Import {module_name}",
                ok=True,
                details="modulo importado",
                failures=failures,
            )
        except Exception as exc:
            run_check(
                name=f"Import {module_name}",
                ok=False,
                details=f"erro: {exc}",
                failures=failures,
            )

    for script_name in ["app.py", "run_app.py"]:
        script_path = root / script_name
        try:
            py_compile.compile(str(script_path), doraise=True)
            run_check(
                name=f"Compile {script_name}",
                ok=True,
                details="compilacao valida",
                failures=failures,
            )
        except Exception as exc:
            run_check(
                name=f"Compile {script_name}",
                ok=False,
                details=f"erro: {exc}",
                failures=failures,
            )

    try:
        import app

        expected = {
            "REGIAO",
            "QUADRO",
            "STATUS",
            "TIPO_EQUIPAMENTO",
            "TAG",
            "MODELO",
            "FABRICANTE",
            "DATA_ABERTURA",
            "FALHA",
            "CRITICIDADE",
        }
        actual = set(app.REQUIRED_COLUMNS)
        run_check(
            name="REQUIRED_COLUMNS",
            ok=expected.issubset(actual),
            details=f"{len(actual)} colunas obrigatorias mapeadas",
            failures=failures,
        )
    except Exception as exc:
        run_check(
            name="Import app",
            ok=False,
            details=f"erro: {exc}",
            failures=failures,
        )

    try:
        import run_app

        app_path = Path(run_app.resolve_app_path())
        run_check(
            name="resolve_app_path",
            ok=app_path.exists(),
            details=str(app_path),
            failures=failures,
        )

        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.bind(("127.0.0.1", 0))
        preferred_port = int(test_socket.getsockname()[1])
        test_socket.listen(1)
        try:
            chosen_port = run_app.choose_port(preferred=preferred_port, max_tries=200)
        finally:
            test_socket.close()

        run_check(
            name="choose_port fallback",
            ok=chosen_port != preferred_port,
            details=f"porta ocupada: {preferred_port} | porta escolhida: {chosen_port}",
            failures=failures,
        )
    except Exception as exc:
        run_check(
            name="Checks run_app",
            ok=False,
            details=f"erro: {exc}",
            failures=failures,
        )

    print("=== Resultado ===")
    if failures:
        print(f"Falhas: {len(failures)} -> {', '.join(failures)}")
        return 1

    print("Todos os checks passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
