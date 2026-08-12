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
compositor.py) -- este arquivo so cuida de receber o upload, o editor de
recorte (posicao/zoom escolhidos pelo usuario, ver templates/index.html)
e os downloads. compose_medal espera um caminho de arquivo de verdade
(nao um stream), entao cada upload e salvo num arquivo temporario antes
de chamar a mesma funcao que main.py/gui.py usam.

Sobre o recorte manual: o editor no navegador manda um retangulo
quadrado (x1, y1, x2, y2) em pixels da imagem ORIGINAL (nao da tela) --
o <canvas> do navegador ja auto-orienta a imagem pela tag EXIF ao
desenhar (Safari/Chrome modernos fazem isso), e load_rgba() do lado do
servidor tambem aplica ImageOps.exif_transpose, entao os dois lados
concordam no mesmo sistema de coordenadas (imagem ja "endireitada").
"""

from __future__ import annotations

import base64
import io
import json
import tempfile
import zipfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image
from werkzeug.datastructures import FileStorage

from compositor import auto_cover_box, compose_medal, crop_to_box, load_rgba
from config import IMAGE_EXTENSIONS, get_medal_spec

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # 60MB no total do upload

spec = get_medal_spec()

CropBox = tuple[float, float, float, float]


def _extensao_valida(nome_arquivo: str) -> bool:
    nome_lower = nome_arquivo.lower()
    return any(nome_lower.endswith(ext) for ext in IMAGE_EXTENSIONS)


def _sem_extensao(nome_arquivo: str) -> str:
    return Path(nome_arquivo).stem


def _ler_box(valores: dict, prefixo: str = "") -> CropBox | None:
    """Le x1/y1/x2/y2 (ou <prefixo>x1 etc.) de um dict tipo form; None se
    algum campo faltar ou nao for numero (cai para recorte automatico)."""
    try:
        return (
            float(valores[f"{prefixo}x1"]),
            float(valores[f"{prefixo}y1"]),
            float(valores[f"{prefixo}x2"]),
            float(valores[f"{prefixo}y2"]),
        )
    except (KeyError, ValueError, TypeError):
        return None


def _to_data_uri(imagem: Image.Image, mimetype: str = "image/png") -> str:
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return f"data:{mimetype};base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _crop_quadrada(caminho: Path, crop_box: CropBox | None) -> Image.Image:
    """Recorte quadrado 1:1 'cru' (sem mascara circular, sem moldura da
    medalha) no angulo/posicao escolhidos -- pronto pra reenviar pra outro
    programa. Achatado em fundo branco caso a foto tenha transparencia."""
    img = load_rgba(caminho)
    box = crop_box if crop_box is not None else auto_cover_box(img.size)
    quadrado = crop_to_box(img, box)
    fundo = Image.new("RGB", quadrado.size, (255, 255, 255))
    fundo.paste(quadrado, mask=quadrado.split()[3])
    return fundo


def _salvar_temp(arquivo: FileStorage) -> tempfile._TemporaryFileWrapper:
    sufixo = Path(arquivo.filename).suffix or ".jpg"
    tmp = tempfile.NamedTemporaryFile(suffix=sufixo)
    arquivo.save(tmp.name)
    return tmp


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/api/preview", methods=["POST"])
def api_preview():
    """Uma imagem + recorte (opcional) -> previa da medalha + recorte
    quadrado 1:1, os dois como data URIs (sem gravar nada no servidor)."""
    arquivo = request.files.get("imagem")
    if not arquivo or not arquivo.filename:
        return jsonify(erro="Nenhuma imagem enviada."), 400
    if not _extensao_valida(arquivo.filename):
        return jsonify(erro="Formato invalido. Aceitos: " + ", ".join(IMAGE_EXTENSIONS)), 400

    box = _ler_box(request.form)
    with _salvar_temp(arquivo) as tmp:
        caminho = Path(tmp.name)
        try:
            resultado = compose_medal(spec, caminho, crop_box=box)
            recorte = _crop_quadrada(caminho, box)
        except Exception as exc:
            return jsonify(erro=f"Erro ao gerar mockup: {exc}"), 400

    nome_base = _sem_extensao(arquivo.filename)
    return jsonify(
        preview=_to_data_uri(resultado),
        crop=_to_data_uri(recorte),
        nome_preview=f"{nome_base}{spec.output_suffix}.png",
        nome_crop=f"{nome_base}_recorte.png",
    )


@app.route("/processar", methods=["POST"])
def processar():
    """Lote SEM revisao individual: recorte automatico (cover) pra cada
    imagem, baixa um .zip direto -- comportamento original."""
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

    zip_buffer = io.BytesIO()
    falhas = list(invalidos)
    ok = 0
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for arquivo in validos:
            try:
                with _salvar_temp(arquivo) as tmp:
                    resultado = compose_medal(spec, Path(tmp.name))
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
        zip_buffer, mimetype="application/zip", as_attachment=True, download_name="medalhas.zip"
    )


@app.route("/api/lote-revisado", methods=["POST"])
def api_lote_revisado():
    """Lote COM revisao individual: um recorte por imagem (escolhido no
    navegador, um de cada vez), devolve dois .zip -- previas e recortes
    quadrados -- como data URIs num unico JSON."""
    arquivos = [f for f in request.files.getlist("imagens") if f and f.filename]
    if not arquivos:
        return jsonify(erro="Nenhuma imagem enviada."), 400

    try:
        caixas = json.loads(request.form.get("caixas", "[]"))
    except ValueError:
        caixas = []
    if len(caixas) != len(arquivos):
        return jsonify(erro="Numero de recortes nao corresponde ao numero de imagens."), 400

    previews_buf = io.BytesIO()
    crops_buf = io.BytesIO()
    falhas: list[str] = []
    ok = 0
    with zipfile.ZipFile(previews_buf, "w", zipfile.ZIP_DEFLATED) as zp, \
         zipfile.ZipFile(crops_buf, "w", zipfile.ZIP_DEFLATED) as zc:
        for arquivo, caixa in zip(arquivos, caixas):
            if not _extensao_valida(arquivo.filename):
                falhas.append(f"{arquivo.filename}: formato invalido")
                continue
            box = tuple(caixa) if caixa and len(caixa) == 4 else None
            try:
                with _salvar_temp(arquivo) as tmp:
                    caminho = Path(tmp.name)
                    resultado = compose_medal(spec, caminho, crop_box=box)
                    recorte = _crop_quadrada(caminho, box)
            except Exception as exc:
                falhas.append(f"{arquivo.filename}: {exc}")
                continue

            nome_base = _sem_extensao(arquivo.filename)
            pbuf = io.BytesIO()
            resultado.save(pbuf, format="PNG")
            zp.writestr(f"{nome_base}{spec.output_suffix}.png", pbuf.getvalue())
            cbuf = io.BytesIO()
            recorte.save(cbuf, format="PNG")
            zc.writestr(f"{nome_base}_recorte.png", cbuf.getvalue())
            ok += 1

    if ok == 0:
        return jsonify(erro="Nenhuma imagem pode ser processada. Falhas: " + "; ".join(falhas)), 400

    previews_buf.seek(0)
    crops_buf.seek(0)
    return jsonify(
        previews_zip="data:application/zip;base64," + base64.b64encode(previews_buf.getvalue()).decode("ascii"),
        crops_zip="data:application/zip;base64," + base64.b64encode(crops_buf.getvalue()).decode("ascii"),
        ok=ok,
        falhas=falhas,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
