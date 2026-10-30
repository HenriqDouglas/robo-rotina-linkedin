"""Atualização pelo GitHub: baixa o robo-linkedin.zip da última versão publicada e troca só o código.

Dados da pessoa (.env, dados/, estado.sqlite, logs/) nunca são tocados.
Uso direto: python atualizar.py <pasta-da-instalação>   (o robô usa as funções daqui)
"""
from __future__ import annotations

import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import requests

ASSET = "robo-linkedin.zip"
PROTEGIDOS = {".env", "dados", "estado.sqlite", "logs", "python.txt", "PAUSADO", "backup", "__pycache__", ".git"}
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def versao_local(base: Path) -> str:
    arq = base / "versao.txt"
    return arq.read_text(encoding="utf-8-sig").strip() if arq.exists() else "0.0.0"


def _num(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def ultima_versao(repo: str) -> dict:
    r = requests.get(f"https://api.github.com/repos/{repo}/releases/latest",
                     headers={"Accept": "application/vnd.github+json"}, timeout=30)
    if r.status_code == 404:
        raise RuntimeError(f"nenhuma versão publicada em github.com/{repo}")
    r.raise_for_status()
    d = r.json()
    url = next((a["browser_download_url"] for a in d.get("assets", []) if a["name"] == ASSET), None)
    if not url:
        raise RuntimeError(f"a versão {d['tag_name']} não tem o anexo {ASSET}")
    return {"versao": d["tag_name"].lstrip("v"), "notas": d.get("body") or "", "url": url}


def tem_nova(base: Path, repo: str) -> dict | None:
    info = ultima_versao(repo)
    return info if _num(info["versao"]) > _num(versao_local(base)) else None


def _copiar(origem: Path, destino: Path):
    if destino.is_dir():
        shutil.rmtree(destino)
    elif destino.exists():
        destino.unlink()
    if origem.is_dir():
        shutil.copytree(origem, destino, ignore=shutil.ignore_patterns("__pycache__"))
    else:
        shutil.copy2(origem, destino)


def aplicar(base: Path, info: dict, log=print) -> str:
    """Baixa, valida, faz backup e troca os arquivos de código. Em caso de erro, volta o que estava."""
    tmp = Path(tempfile.mkdtemp(prefix="robo-atualizacao-"))
    try:
        log(f"atualizar: baixando {info['versao']}")
        r = requests.get(info["url"], timeout=120)
        r.raise_for_status()
        (tmp / ASSET).write_bytes(r.content)
        with zipfile.ZipFile(tmp / ASSET) as z:
            z.extractall(tmp / "novo")
        achados = list((tmp / "novo").rglob("robo.py"))
        if not achados:
            raise RuntimeError("o pacote não tem robo.py")
        raiz = achados[0].parent
        if versao_local(raiz) != info["versao"]:
            raise RuntimeError(f"versao.txt do pacote ({versao_local(raiz)}) não bate com a versão {info['versao']}")
        for py in raiz.glob("*.py"):  # código quebrado é recusado antes de trocar qualquer coisa
            py_compile.compile(str(py), cfile=str(tmp / (py.name + "c")), doraise=True)

        novos = [p for p in raiz.iterdir() if p.name not in PROTEGIDOS]
        backup = base / "backup" / versao_local(base)
        if backup.exists():
            shutil.rmtree(backup)
        backup.mkdir(parents=True)
        for p in base.iterdir():
            if p.name not in PROTEGIDOS:
                _copiar(p, backup / p.name)
        try:
            for p in novos:
                _copiar(p, base / p.name)
        except Exception:
            log("atualizar: erro ao copiar; voltando a versão anterior")
            for p in backup.iterdir():
                _copiar(p, base / p.name)
            raise
        if (base / "requirements.txt").exists():
            py = Path(sys.executable).with_name("python.exe")
            r = subprocess.run([str(py if py.exists() else sys.executable), "-m", "pip", "install", "--user", "--quiet",
                                "--disable-pip-version-check", "-r", str(base / "requirements.txt")],
                               capture_output=True, text=True, creationflags=SEM_JANELA)
            if r.returncode:
                log(f"atualizar: aviso do pip: {r.stderr[-300:]}")
        log(f"atualizar: código trocado para {info['versao']} (backup em {backup})")
        return info["versao"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def reiniciar(base: Path, esperar: bool = False):
    """Recria as tarefas e religa o ouvinte com o código novo (o agendar.ps1 encerra o ouvinte antigo)."""
    args = ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
            "-File", str(base / "agendar.ps1")]
    if esperar:
        subprocess.run(args)
    else:
        # processo solto: continua mesmo quando o agendar.ps1 encerra o ouvinte que o chamou
        subprocess.Popen(args, close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                         | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


if __name__ == "__main__":
    import json
    pasta = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    cfg = json.loads((Path(__file__).resolve().parent / "config.json").read_text(encoding="utf-8-sig"))
    info = ultima_versao(cfg["repositorio"])
    print(f"instalada: {versao_local(pasta)} · publicada: {info['versao']}")
    aplicar(pasta, info)
