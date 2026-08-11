"""
Gerador de mockups de medalhas personalizadas.

Uso individual:
    python main.py imagem.jpg
    -> saida/imagem_medalha.png

Uso em lote (todas as imagens de uma pasta):
    python main.py --pasta entrada
    -> saida/<nome>_medalha.png para cada imagem em entrada/

Calibracao (gera overlay mostrando centro/raio configurados em config.py):
    python main.py --calibrar

Escolher outra base cadastrada em config.py (ex.: futura medalha 12mm):
    python main.py imagem.jpg --medalha prata_16mm
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import IMAGE_EXTENSIONS, SAIDA_DIR, get_medal_spec
from compositor import build_calibration_preview, compose_medal, save_output


def _listar_imagens(pasta: Path) -> list[Path]:
    return sorted(
        p for p in pasta.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def processar_arquivo(caminho: Path, medal_id: str | None, saida_dir: Path) -> Path:
    spec = get_medal_spec(medal_id)
    resultado = compose_medal(spec, caminho)
    destino = saida_dir / f"{caminho.stem}{spec.output_suffix}.png"
    save_output(resultado, destino)
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gerador de mockups de medalhas.")
    parser.add_argument("imagem", nargs="?", help="Caminho de uma imagem para processar")
    parser.add_argument("--pasta", metavar="PASTA", help="Processa todas as imagens de uma pasta")
    parser.add_argument("--saida", metavar="PASTA", default=str(SAIDA_DIR),
                         help="Pasta de saida (padrao: saida/)")
    parser.add_argument("--medalha", metavar="ID", default=None,
                         help="ID da base cadastrada em config.py (padrao: ACTIVE_MEDAL_ID)")
    parser.add_argument("--calibrar", action="store_true",
                         help="Gera imagem de calibracao com centro/raios sobrepostos na base")
    args = parser.parse_args(argv)

    saida_dir = Path(args.saida)

    if args.calibrar:
        spec = get_medal_spec(args.medalha)
        preview = build_calibration_preview(spec)
        destino = saida_dir / f"calibracao_{spec.id}.png"
        save_output(preview, destino)
        print(f"Calibracao gerada em: {destino}")
        return 0

    if args.pasta:
        pasta = Path(args.pasta)
        if not pasta.is_dir():
            parser.error(f"Pasta nao encontrada: {pasta}")
        imagens = _listar_imagens(pasta)
        if not imagens:
            print(f"Nenhuma imagem encontrada em {pasta}")
            return 1
        print(f"Processando {len(imagens)} imagem(ns) de {pasta} ...")
        falhas = 0
        for caminho in imagens:
            try:
                destino = processar_arquivo(caminho, args.medalha, saida_dir)
                print(f"  OK  {caminho.name} -> {destino}")
            except Exception as exc:
                falhas += 1
                print(f"  ERRO {caminho.name}: {exc}", file=sys.stderr)
        print(f"Concluido. {len(imagens) - falhas} ok, {falhas} falha(s).")
        return 1 if falhas else 0

    if args.imagem:
        caminho = Path(args.imagem)
        if not caminho.is_file():
            parser.error(f"Imagem nao encontrada: {caminho}")
        destino = processar_arquivo(caminho, args.medalha, saida_dir)
        print(f"Gerado: {destino}")
        return 0

    parser.error("Informe uma imagem, --pasta ou --calibrar. Use -h para ajuda.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
