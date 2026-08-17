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
import secrets
import tempfile
import time
import zipfile
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file
from PIL import Image
from werkzeug.datastructures import FileStorage

from compositor import auto_cover_box, compose_medal, crop_to_box, load_rgba
from config import ACTIVE_MEDAL_ID, IMAGE_EXTENSIONS, MEDAL_SPECS, get_medal_spec

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # 60MB no total do upload

CropBox = tuple[float, float, float, float]

# Lista (id, nome) pra popular o seletor de estilo na pagina -- ordem do
# dict de MEDAL_SPECS em config.py, entao a ordem de cadastro la e a
# ordem que aparece pro usuario.
ESTILOS_DISPONIVEIS = [(spec_id, s.nome) for spec_id, s in MEDAL_SPECS.items()]


def _resolver_spec():
    """Le o campo 'medalha' do form (id de MEDAL_SPECS) -- cai pro padrao
    (ACTIVE_MEDAL_ID) se nao vier ou vier um id desconhecido, em vez de
    dar erro (o front sempre manda um valor valido, mas nao custa)."""
    medalha_id = request.form.get("medalha") or ACTIVE_MEDAL_ID
    if medalha_id not in MEDAL_SPECS:
        medalha_id = ACTIVE_MEDAL_ID
    return get_medal_spec(medalha_id)

# Downloads (previa, recorte 1:1, .zip de lote) sao guardados aqui em
# memoria por um token de uso unico, em vez de embutidos como data URI no
# HTML/JSON -- o Safari do iPhone (o motivo desta versao web existir) tem
# suporte inconsistente pra "baixar" data URIs grandes ou de tipos como
# .zip, so tipo mostra a pagina em branco ou nao faz nada. Um link de
# verdade pro navegador buscar (com Content-Disposition) funciona em
# qualquer navegador. So funciona com 1 worker do gunicorn (ver
# Procfile/render.yaml: --workers 1), senao o download podia cair num
# processo que nao tem o token.
_DOWNLOAD_TTL_SEGUNDOS = 15 * 60
_downloads: dict[str, tuple[bytes, str, str, float]] = {}


def _registrar_download(dados: bytes, mimetype: str, nome_arquivo: str) -> str:
    agora = time.time()
    for token, (_, _, _, expira_em) in list(_downloads.items()):
        if expira_em < agora:
            _downloads.pop(token, None)
    token = secrets.token_urlsafe(16)
    _downloads[token] = (dados, mimetype, nome_arquivo, agora + _DOWNLOAD_TTL_SEGUNDOS)
    return token


def _imagem_para_bytes(imagem: Image.Image) -> bytes:
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


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


def _preview_data_uri(imagem: Image.Image) -> str:
    """So para EXIBIR a previa inline na pagina (<img src="data:...">) --
    isso e confiavel em qualquer navegador. O download em si usa
    /download/<token> (ver _registrar_download), nao esta data URI."""
    return "data:image/png;base64," + base64.b64encode(_imagem_para_bytes(imagem)).decode("ascii")


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


def _render_index(**kwargs):
    return render_template(
        "index.html", estilos=ESTILOS_DISPONIVEIS, estilo_padrao=ACTIVE_MEDAL_ID, **kwargs
    )


@app.route("/", methods=["GET"])
def index():
    return _render_index()


@app.route("/download/<token>")
def download(token: str):
    """Serve um download registrado por _registrar_download -- uso unico
    (o token e removido assim que baixado) e expira em 15min se nunca for
    usado. Link de verdade (nao data URI), pra funcionar em qualquer
    navegador incluindo Safari do iPhone.

    Sempre serve como application/octet-stream, mesmo pras imagens PNG:
    o Safari do iOS tem visualizador nativo pra image/*, e quando o
    Content-Type e "image/png" ele costuma so EXIBIR a imagem (ignorando
    Content-Disposition: attachment) em vez de salvar -- octet-stream nao
    tem visualizador embutido, entao forca o comportamento de "baixar".
    """
    entrada = _downloads.pop(token, None)
    if entrada is None or entrada[3] < time.time():
        abort(404, description="Link de download expirado ou já utilizado. Gere a imagem de novo.")
    dados, _mimetype_original, nome_arquivo, _ = entrada
    resposta = send_file(
        io.BytesIO(dados),
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=nome_arquivo,
    )
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.route("/api/preview", methods=["POST"])
def api_preview():
    """Uma imagem + recorte (opcional) -> previa da medalha (mostrada
    inline) + links de download reais pra previa e pro recorte quadrado
    1:1 (ver /download/<token>)."""
    arquivo = request.files.get("imagem")
    if not arquivo or not arquivo.filename:
        return jsonify(erro="Nenhuma imagem enviada."), 400
    if not _extensao_valida(arquivo.filename):
        return jsonify(erro="Formato invalido. Aceitos: " + ", ".join(IMAGE_EXTENSIONS)), 400

    spec = _resolver_spec()
    box = _ler_box(request.form)
    with _salvar_temp(arquivo) as tmp:
        caminho = Path(tmp.name)
        try:
            resultado = compose_medal(spec, caminho, crop_box=box)
            recorte = _crop_quadrada(caminho, box)
        except Exception as exc:
            return jsonify(erro=f"Erro ao gerar mockup: {exc}"), 400

    nome_base = _sem_extensao(arquivo.filename)
    token_preview = _registrar_download(
        _imagem_para_bytes(resultado), "image/png", f"{nome_base}{spec.output_suffix}.png"
    )
    token_crop = _registrar_download(
        _imagem_para_bytes(recorte), "image/png", f"{nome_base}_recorte.png"
    )
    return jsonify(
        preview=_preview_data_uri(resultado),
        url_preview=f"/download/{token_preview}",
        url_crop=f"/download/{token_crop}",
    )


@app.route("/processar", methods=["POST"])
def processar():
    """Lote SEM revisao individual: recorte automatico (cover) pra cada
    imagem, baixa um .zip direto -- comportamento original."""
    arquivos = [f for f in request.files.getlist("imagens") if f and f.filename]
    if not arquivos:
        return _render_index(erro="Selecione ao menos uma imagem.")

    validos = [f for f in arquivos if _extensao_valida(f.filename)]
    invalidos = [f.filename for f in arquivos if not _extensao_valida(f.filename)]
    if not validos:
        return _render_index(
            erro="Nenhum arquivo valido. Formatos aceitos: " + ", ".join(IMAGE_EXTENSIONS),
        )

    spec = _resolver_spec()
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
        return _render_index(
            erro="Nenhuma imagem pode ser processada. Falhas: " + "; ".join(falhas),
        )

    zip_buffer.seek(0)
    return send_file(
        zip_buffer, mimetype="application/zip", as_attachment=True, download_name="medalhas.zip"
    )


@app.route("/api/lote-revisado", methods=["POST"])
def api_lote_revisado():
    """Lote COM revisao individual: um recorte por imagem (escolhido no
    navegador, um de cada vez), devolve links de download reais pra dois
    .zip -- previas e recortes quadrados (ver /download/<token>)."""
    arquivos = [f for f in request.files.getlist("imagens") if f and f.filename]
    if not arquivos:
        return jsonify(erro="Nenhuma imagem enviada."), 400

    try:
        caixas = json.loads(request.form.get("caixas", "[]"))
    except ValueError:
        caixas = []
    if len(caixas) != len(arquivos):
        return jsonify(erro="Numero de recortes nao corresponde ao numero de imagens."), 400

    spec = _resolver_spec()
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

    token_previews = _registrar_download(previews_buf.getvalue(), "application/zip", "medalhas.zip")
    token_crops = _registrar_download(crops_buf.getvalue(), "application/zip", "recortes.zip")
    return jsonify(
        url_previews_zip=f"/download/{token_previews}",
        url_crops_zip=f"/download/{token_crops}",
        ok=ok,
        falhas=falhas,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
