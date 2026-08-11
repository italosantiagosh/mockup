"""
Logica pura de composicao das camadas da medalha.

Nao ha nenhuma geracao de imagem por IA aqui: apenas carregamento de PNGs,
redimensionamento/recorte estilo `object-fit: cover`, mascara circular e
alpha compositing (Pillow puro), na ordem:

    1. fundo branco
    2. base_medalha.png
    3. imagem do usuario (cover + mascara circular, encostando na parede)
    4. efeito_resina.png

Tudo em RGBA do inicio ao fim para nao gerar bordas pretas/brancas por
transparencia mal tratada.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageOps

from config import MedalSpec, ResolvedGeometry

SUPERSAMPLE = 4  # anti-aliasing da mascara circular (4x, depois reduz)


def load_rgba(path: Path) -> Image.Image:
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo nao encontrado: {path}\n"
            "Verifique se os assets da medalha (base_medalha.png / "
            "efeito_resina.png) estao na pasta assets/."
        )
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGBA")


def _circular_mask(diameter: int, supersample: int = SUPERSAMPLE) -> Image.Image:
    """Mascara circular (modo 'L') com borda suavizada, sem serrilhado."""
    diameter = max(1, int(round(diameter)))
    big = diameter * supersample
    mask_big = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(mask_big)
    draw.ellipse((0, 0, big - 1, big - 1), fill=255)
    return mask_big.resize((diameter, diameter), Image.LANCZOS)


def fit_cover_circle(user_image: Image.Image, diameter: int) -> Image.Image:
    """
    Equivalente a CSS `object-fit: cover` dentro de um quadrado de lado
    `diameter`, seguido de mascara circular. A imagem nunca e deformada:
    e escalada mantendo proporcao ate cobrir totalmente o quadrado, o
    excesso (o que sobra fora do quadrado) e cortado, centralizado.
    """
    diameter = max(1, int(round(diameter)))
    img = user_image.convert("RGBA")
    w, h = img.size

    scale = diameter / min(w, h)
    new_w = max(diameter, round(w * scale))
    new_h = max(diameter, round(h * scale))
    img = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - diameter) // 2
    top = (new_h - diameter) // 2
    img = img.crop((left, top, left + diameter, top + diameter))

    mask = _circular_mask(diameter)
    # Multiplica pelo alpha original (caso a foto do usuario ja tenha
    # transparencia) em vez de sobrescrever: fora do circulo fica sempre
    # 100% transparente, dentro respeita a transparencia original.
    r, g, b, a = img.split()
    a = ImageChops.multiply(a, mask)
    img.putalpha(a)
    return img


def _paste_layer_fullsize(canvas: Image.Image, layer: Image.Image) -> None:
    """Aplica uma camada (base ou resina ja pre-alinhada) que ocupa o canvas
    inteiro, registrada pixel a pixel com base_medalha.png."""
    if layer.size != canvas.size:
        layer = layer.resize(canvas.size, Image.LANCZOS)
    canvas.alpha_composite(layer)


def _resize_rgba(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Redimensiona RGBA com alpha premultiplicado, evitando halos escuros
    nas bordas semi-transparentes que o resize direto do Pillow causaria."""
    if img.size == size:
        return img
    arr = np.asarray(img).astype(np.float32)
    rgb, a = arr[:, :, :3], arr[:, :, 3:4]
    premultiplied = np.concatenate([rgb * (a / 255.0), a], axis=2).astype(np.uint8)
    resized = np.asarray(
        Image.fromarray(premultiplied, "RGBA").resize(size, Image.LANCZOS)
    ).astype(np.float32)
    out_rgb, out_a = resized[:, :, :3], resized[:, :, 3:4]
    safe_a = np.where(out_a < 1.0, 1.0, out_a)
    unpremultiplied = np.clip(out_rgb / (safe_a / 255.0), 0, 255)
    result = np.concatenate([unpremultiplied, out_a], axis=2).astype(np.uint8)
    return Image.fromarray(result, "RGBA")


def _place_resina(canvas: Image.Image, resina: Image.Image, spec: MedalSpec,
                   geo: ResolvedGeometry) -> None:
    """
    Posiciona a camada de resina para que seu proprio domo de vidro (medido
    em spec.resina_native_*) fique com o MESMO diametro e no MESMO lugar da
    foto do usuario (geo.center_x/y, geo.resina_radius) -- em vez de assumir
    que efeito_resina.png ja vem pre-registrado com a base.

    Se nao houver geometria nativa conhecida para o arquivo de resina (nem
    manual em spec, nem em RESINA_DOME_GEOMETRY), cai de volta para o
    overlay direto de canvas inteiro (comportamento pre-calibracao).
    """
    native = spec.resolve_resina_native()
    if native is None:
        _paste_layer_fullsize(canvas, resina)
        return
    native_cx, native_cy, native_radius = native

    scale = geo.resina_radius / native_radius
    new_size = (max(1, round(resina.width * scale)), max(1, round(resina.height * scale)))
    resized = _resize_rgba(resina, new_size)

    scaled_native_cx = native_cx * scale
    scaled_native_cy = native_cy * scale
    paste_x = round(geo.center_x - scaled_native_cx)
    paste_y = round(geo.center_y - scaled_native_cy)

    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(resized, (paste_x, paste_y), resized)
    canvas.alpha_composite(layer)


def compose_medal(spec: MedalSpec, user_image_path: Path) -> Image.Image:
    base = load_rgba(spec.base_path)
    resina = load_rgba(spec.resina_path)
    geo = spec.resolve(base.size)

    # 1) fundo branco puro, do tamanho exato da base (mesma proporcao/resolucao)
    canvas = Image.new("RGBA", base.size, (255, 255, 255, 255))

    # 2) base da medalha
    _paste_layer_fullsize(canvas, base)

    # 3) imagem do usuario: cover + mascara circular, centralizada em (cx, cy)
    user_img = load_rgba(user_image_path)
    diameter = int(round(geo.inner_radius * 2))
    circle = fit_cover_circle(user_img, diameter)
    paste_x = int(round(geo.center_x - diameter / 2))
    paste_y = int(round(geo.center_y - diameter / 2))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.alpha_composite(circle, (paste_x, paste_y))
    canvas.alpha_composite(layer)

    # 4) resina por cima, escalada/reposicionada para o mesmo diametro e
    # lugar da foto (ver _place_resina)
    _place_resina(canvas, resina, spec, geo)

    # 5) keepout: restaura a base original (fundo branco + base_medalha.png,
    # sem foto/resina) nas areas protegidas, como a argola -- mesmo que o
    # raio calibrado tenha alcancado ali.
    if spec.keepout_boxes:
        canvas = _apply_keepout(canvas, base, spec.keepout_boxes)

    return canvas


def _apply_keepout(canvas: Image.Image, base: Image.Image,
                    boxes: tuple[tuple[float, float, float, float], ...]) -> Image.Image:
    """Restaura os pixels da base dentro das caixas de keepout, mas SO onde
    a base tem metal/sombra de fato (nao o retangulo inteiro) -- senao a
    caixa corta uma borda reta e artificial sobre a foto/resina onde o
    interior da cavidade (branco na base) legitimamente aparece."""
    original = Image.new("RGBA", canvas.size, (255, 255, 255, 255))
    _paste_layer_fullsize(original, base)

    box_mask = Image.new("L", canvas.size, 0)
    draw = ImageDraw.Draw(box_mask)
    for x1, y1, x2, y2 in boxes:
        draw.rectangle((x1, y1, x2, y2), fill=255)

    base_luminance = np.asarray(base.convert("L"))
    metal_mask = Image.fromarray(np.where(base_luminance < 245, 255, 0).astype(np.uint8), "L")

    mask = ImageChops.multiply(box_mask, metal_mask)
    return Image.composite(original, canvas, mask)


def save_output(image: Image.Image, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def build_calibration_preview(spec: MedalSpec) -> Image.Image:
    """Desenha centro / raio de recorte / raio da resina por cima da base,
    para validar visualmente os parametros de config.py."""
    base = load_rgba(spec.base_path)
    geo = spec.resolve(base.size)
    preview = base.copy()
    draw = ImageDraw.Draw(preview)

    cx, cy = geo.center_x, geo.center_y
    cross = 24
    draw.line((cx - cross, cy, cx + cross, cy), fill=(255, 0, 0, 255), width=3)
    draw.line((cx, cy - cross, cx, cy + cross), fill=(255, 0, 0, 255), width=3)

    r = geo.inner_radius
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(0, 200, 0, 255), width=4)

    rr = geo.resina_radius
    if rr != r:
        draw.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=(0, 120, 255, 255), width=4)

    for box in spec.keepout_boxes:
        draw.rectangle(box, outline=(255, 140, 0, 255), width=3)

    return preview
