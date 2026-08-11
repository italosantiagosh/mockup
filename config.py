"""
Configuracao do gerador de mockups de medalhas.

Toda a geometria (onde fica a cavidade interna da medalha, onde a resina
e aplicada, etc.) mora aqui, separada da logica de composicao em
compositor.py. Isso permite calibrar visualmente uma base nova, ou
cadastrar bases novas (12mm, 16mm, dourada, etc.) sem tocar no codigo.

Como calibrar:
    python main.py --calibrar
Isso gera saida/calibracao_<id>.png desenhando por cima da base atual:
    - um "+" no centro configurado (CENTER_X, CENTER_Y)
    - um circulo verde = area onde a imagem do usuario e recortada (INNER_RADIUS)
    - um circulo azul  = area onde a camada de resina e posicionada (RESINA_RADIUS)
Ajuste os numeros abaixo ate os circulos baterem exatamente com a parede
metalica interna da base_medalha.png e salve novamente.
"""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
ENTRADA_DIR = BASE_DIR / "entrada"
SAIDA_DIR = BASE_DIR / "saida"
REFERENCIAS_DIR = BASE_DIR / "referencias"

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")

# Geometria nativa de cada arquivo de efeito de resina: onde o domo de
# vidro fica DENTRO dos proprios pixels do arquivo (centro_x, centro_y,
# raio), medida uma unica vez direto na imagem (contorno escuro nitido da
# borda do vidro) e independente de qualquer calibracao de base. Chaveado
# pelo nome do arquivo para que MedalSpec resolva isso sozinho -- assim a
# calibracao da base (center_x/center_y/inner_radius) nunca precisa, nem
# deve, tocar nesses numeros.
RESINA_DOME_GEOMETRY: dict[str, tuple[float, float, float]] = {
    "efeito_resina.png": (629.5, 613.0, 473.0),
}


@dataclass(frozen=True)
class ResolvedGeometry:
    """Geometria ja resolvida em pixels, prontos para uso pelo compositor."""

    center_x: float
    center_y: float
    inner_radius: float
    resina_radius: float


@dataclass(frozen=True)
class MedalSpec:
    """
    Descreve uma "base" de medalha completa: os arquivos de camada e a
    posicao/tamanho da cavidade interna onde a imagem do usuario entra.

    A geometria pode ser dada de duas formas (a segunda serve como
    estimativa inicial enquanto a base nao foi calibrada em pixels):

    1) Pixels absolutos (precisao total, preferido apos calibrar):
         center_x, center_y, inner_radius (e opcionalmente resina_radius)

    2) Fracoes do tamanho da propria base_medalha.png (0.0 a 1.0), usadas
       somente quando o valor em pixel correspondente for None:
         center_x_frac, center_y_frac, inner_radius_frac

    Tambem e possivel usar IMAGE_BOX explicito com from_box(), se preferir
    pensar em termos de retangulo (x1, y1, x2, y2) ao inves de
    centro+raio.
    """

    id: str
    nome: str
    base_path: Path
    resina_path: Path

    center_x: Optional[float] = None
    center_y: Optional[float] = None
    inner_radius: Optional[float] = None
    resina_radius: Optional[float] = None

    # Geometria NATIVA do efeito_resina.png (onde o vidro/domo esta dentro
    # do proprio arquivo da resina, que pode nao estar registrado no mesmo
    # lugar/escala da cavidade da base). Quando definido, a resina inteira
    # e escalada e deslocada para que esse circulo nativo caia exatamente
    # sobre (center_x, center_y, resina_radius) -- ou seja, foto e resina
    # ficam com o MESMO diametro e no MESMO lugar. Quando None, tenta
    # resolver automaticamente pelo nome do arquivo via RESINA_DOME_GEOMETRY
    # (ver mais abaixo) antes de cair para overlay direto sem transformacao.
    #
    # NAO defina estes 3 campos aqui manualmente copiando os mesmos valores
    # de center_x/center_y/inner_radius -- eles descrevem coisas diferentes
    # (a posicao do vidro DENTRO do arquivo efeito_resina.png, nao a
    # cavidade da base) e ficam errados por coincidencia de numero, nao por
    # design. Cadastre o arquivo em RESINA_DOME_GEOMETRY em vez disso.
    resina_native_cx: Optional[float] = None
    resina_native_cy: Optional[float] = None
    resina_native_radius: Optional[float] = None

    # Retangulos (x1, y1, x2, y2) em pixels da base onde a foto/resina NUNCA
    # devem aparecer, mesmo que o raio calibrado alcance ali -- a area e
    # restaurada para a base original (fundo branco + base_medalha.png) por
    # cima de tudo. Serve para proteger partes como a argola, que ficam
    # fisicamente acima/fora da cavidade e nunca devem ser cobertas.
    keepout_boxes: tuple[tuple[float, float, float, float], ...] = ()

    # Estimativas usadas apenas enquanto os valores em pixel acima forem None.
    # Valores de partida para uma base "medalha redonda com argola no topo",
    # baseados na leitura visual das referencias fornecidas: a argola ocupa
    # a faixa superior do canvas, entao o centro do circulo principal fica
    # um pouco abaixo do centro vertical da imagem.
    center_x_frac: float = 0.50
    center_y_frac: float = 0.565
    inner_radius_frac: float = 0.355
    resina_radius_frac: Optional[float] = None  # None => usa inner_radius

    output_suffix: str = "_medalha"
    # Margem de seguranca (em px) subtraida do raio interno no recorte da
    # foto, para garantir que a foto va ligeiramente POR BAIXO da borda
    # metalica (evita fiapo de fundo branco caso a calibracao fique 1-2px
    # curta). 0 = a foto termina exatamente no raio calibrado.
    overlap_px: float = 2.0

    def resolve(self, base_size: tuple[int, int]) -> ResolvedGeometry:
        w, h = base_size
        cx = self.center_x if self.center_x is not None else self.center_x_frac * w
        cy = self.center_y if self.center_y is not None else self.center_y_frac * h
        r = (
            self.inner_radius
            if self.inner_radius is not None
            else self.inner_radius_frac * min(w, h)
        )
        final_r = r + self.overlap_px
        if self.resina_radius is not None:
            rr = self.resina_radius
        elif self.resina_radius_frac is not None:
            rr = self.resina_radius_frac * min(w, h)
        else:
            # Por padrao a resina usa o MESMO diametro final da foto (mesmo
            # lugar, mesmo tamanho), a menos que explicitamente configurada
            # para um raio diferente.
            rr = final_r
        return ResolvedGeometry(cx, cy, final_r, rr)

    def resolve_resina_native(self) -> Optional[tuple[float, float, float]]:
        """(cx, cy, radius) do domo dentro do arquivo de resina, ou None se
        nao ha geometria conhecida (cai para overlay direto sem transformar)."""
        if self.resina_native_radius is not None:
            return (self.resina_native_cx, self.resina_native_cy, self.resina_native_radius)
        return RESINA_DOME_GEOMETRY.get(self.resina_path.name)

    @classmethod
    def from_box(cls, id: str, nome: str, base_path: Path, resina_path: Path,
                 image_box: tuple[float, float, float, float], **kwargs) -> "MedalSpec":
        """Cria um MedalSpec a partir de um retangulo (x1, y1, x2, y2)."""
        x1, y1, x2, y2 = image_box
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        r = min(x2 - x1, y2 - y1) / 2
        return cls(id=id, nome=nome, base_path=base_path, resina_path=resina_path,
                   center_x=cx, center_y=cy, inner_radius=r, **kwargs)


# ---------------------------------------------------------------------------
# Catalogo de bases disponiveis. Adicionar uma medalha nova (12mm, dourada,
# outro efeito de resina, etc.) e so acrescentar uma entrada aqui.
# ---------------------------------------------------------------------------

MEDAL_SPECS: dict[str, MedalSpec] = {
    # Geometria de assets/base_medalha.png (arquivo trocado pelo cliente em
    # 2026-08-11, 1080x1080px). O proprio arquivo traz uma linha guia sutil
    # ciano tracando a parede interna; extraida por deteccao de cor (canal
    # G > canal R) e ajustada por circulo de minimos quadrados: centro
    # (530, 604), raio da linha guia ~377 (residual std ~4px).
    #
    # center_x/center_y/inner_radius/overlap_px: geometria da cavidade da
    # base, calibrada pelo cliente com --calibrar. Esses 4 numeros sao os
    # unicos que devem ser ajustados aqui ao recalibrar. A geometria da
    # resina (resina_native_*) e resolvida automaticamente por
    # RESINA_DOME_GEOMETRY acima, com base no nome do arquivo -- nao
    # precisa (e nao deve) ser repetida aqui.
    #
    # Base trocada pelo cliente por uma versao mais simples (circulo
    # perfeito, sem a complicacao da argola cruzando a parede) -- sem
    # keepout_boxes, nao precisa proteger nada. Calibracao fornecida pelo
    # cliente diretamente.
    "prata_16mm": MedalSpec(
        id="prata_16mm",
        nome="Medalha redonda prata 16mm",
        base_path=ASSETS_DIR / "base_medalha.png",
        resina_path=ASSETS_DIR / "efeito_resina.png",
        center_x=630,
        center_y=655,
        inner_radius=355,
        overlap_px=8,
    ),
}

ACTIVE_MEDAL_ID = "prata_16mm"


def get_medal_spec(medal_id: Optional[str] = None) -> MedalSpec:
    medal_id = medal_id or ACTIVE_MEDAL_ID
    try:
        return MEDAL_SPECS[medal_id]
    except KeyError as exc:
        disponiveis = ", ".join(sorted(MEDAL_SPECS))
        raise SystemExit(
            f"Medalha '{medal_id}' nao cadastrada em config.py. "
            f"Disponiveis: {disponiveis}"
        ) from exc
