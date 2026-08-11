"""
Versao web do gerador de mockups de medalhas -- pensada para ser usada
do celular (Safari/Chrome), sem precisar instalar nada.

Rodar localmente:
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python app.py
    # abre em http://localhost:8000

Producao (Render, Railway, Fly.io, etc.):
    gunicorn app:app

Mesma logica de composicao de main.py/gui.py (compose_medal em
compositor.py) -- este arquivo so cuida de receber o upload, mostrar a
previa/oferecer o download, e nada mais. compose_medal espera um
caminho de arquivo de verdade (nao um stream), entao cada upload e
salvo num arquivo temporario antes de chamar a mesma funcao que
main.py/gui.py usam.
"""

from __future__ import annotations

import base64
import io
import tempfile
import zipfile
from pathlib import Path

from flask import Flask, render_template, request, send_file
from werkzeug.datastructures import FileStorage

from compositor import compose_medal
from config import IMAGE_EXTENSIONS, get_medal_spec

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # 60MB no total do upload

spec = get_medal_spec()


def _extensao_valida(nome_arquivo: str) -> bool:
    nome_lower = nome_arquivo.lower()
    return any(nome_lower.endswith(ext) for ext in IMAGE_EXTENSIONS)


def _processar_upload(arquivo: FileStorage):
    """Salva o upload num arquivo temporario e chama compose_medal --
    mesma funcao usada por main.py/gui.py, so muda como a imagem chega."""
    sufixo = Path(arquivo.filename).suffix or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=sufixo) as tmp:
        arquivo.save(tmp.name)
        return compose_medal(spec, Path(tmp.name))


def _sem_extensao(nome_arquivo: str) -> str:
    return Path(nome_arquivo).stem


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/processar", methods=["POST"])
def processar():
    arquivos = [f for f in request.files.getlist("imagens") if f and f.filename]
    if not arquivos:
        return render_template("index.html", erro="Selecione ao menos uma imagem.")

    validos = [f for f in arquivos if _extensao_valida(f.filename)]
    invalidos = [f.filename for f in arquivos if not _extensao_valida(f.filename)]

    if not validos:
        return render_template(
            "index.html",
            erro="Nenhum arquivo valido. Formatos aceitos: " + ", ".join(IMAGE_EXTENSIONS),
        )

    if len(arquivos) == 1 and not invalidos:
        arquivo = validos[0]
        try:
            resultado = _processar_upload(arquivo)
        except Exception as exc:
            return render_template("index.html", erro=f"Erro ao gerar mockup: {exc}")

        buffer = io.BytesIO()
        resultado.save(buffer, format="PNG")
        data_uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
        nome_saida = f"{_sem_extensao(arquivo.filename)}{spec.output_suffix}.png"
        return render_template("index.html", preview_src=data_uri, preview_nome=nome_saida)

    # multiplos arquivos (ou 1 valido + algum invalido): processa os
    # validos e devolve um .zip com todos, ja que o navegador nao deixa
    # escolher uma pasta para salvar varios arquivos de uma vez.
    zip_buffer = io.BytesIO()
    falhas = list(invalidos)
    ok = 0
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for arquivo in validos:
            try:
                resultado = _processar_upload(arquivo)
            except Exception as exc:
                falhas.append(f"{arquivo.filename}: {exc}")
                continue
            img_buffer = io.BytesIO()
            resultado.save(img_buffer, format="PNG")
            nome_saida = f"{_sem_extensao(arquivo.filename)}{spec.output_suffix}.png"
            zf.writestr(nome_saida, img_buffer.getvalue())
            ok += 1

    if ok == 0:
        return render_template(
            "index.html",
            erro="Nenhuma imagem pode ser processada. Falhas: " + "; ".join(falhas),
        )

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="medalhas.zip",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
