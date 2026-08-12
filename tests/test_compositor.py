"""
Teste de fumaca do pipeline de composicao.

Nao usa os assets reais (que ainda nao existem neste repositorio): gera em
memoria uma base e uma resina SINTETICAS (formas simples desenhadas com
Pillow, so para validar a mecanica de alpha compositing, recorte
'cover' e mascara circular) e uma foto de teste. Serve para provar que o
pipeline roda de ponta a ponta; nao substitui a calibracao visual com os
arquivos reais (base_medalha.png / efeito_resina.png).

Rodar com:
    .venv/bin/python -m pytest tests/ -q
ou diretamente:
    .venv/bin/python tests/test_compositor.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw

from config import MedalSpec
from compositor import auto_cover_box, compose_medal, crop_to_box, fit_cover_circle, fit_manual_circle


def _make_synthetic_base(path: Path, size=(800, 900), center=(400, 490), radius=310, thickness=45):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = center
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                 fill=(190, 190, 195, 255))
    inner = radius - thickness
    draw.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=(0, 0, 0, 0))
    # argola simples no topo
    draw.ellipse((cx - 40, cy - radius - 70, cx + 40, cy - radius + 10),
                  outline=(190, 190, 195, 255), width=18)
    img.save(path)
    return center, inner


def _make_synthetic_resina(path: Path, size=(800, 900), center=(400, 490), radius=265):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = center
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                 fill=(255, 255, 255, 40))
    draw.ellipse((cx - radius * 0.4, cy - radius * 0.6, cx + radius * 0.05, cy - radius * 0.1),
                 fill=(255, 255, 255, 90))
    img.save(path)


def _make_test_photo(path: Path, size=(1600, 1000)):
    img = Image.new("RGB", size, (30, 30, 30))
    draw = ImageDraw.Draw(img)
    for i in range(0, size[0], 40):
        draw.line((i, 0, i, size[1]), fill=(200, 40, 40))
    draw.rectangle((0, 0, 60, 60), fill=(0, 255, 0))  # marca no canto p/ checar crop
    img.save(path)


class TestCompositor(unittest.TestCase):
    def test_pipeline_ponta_a_ponta(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            base_path = tmp / "base_medalha.png"
            resina_path = tmp / "efeito_resina.png"
            foto_path = tmp / "foto.jpg"

            center, inner_radius = _make_synthetic_base(base_path)
            _make_synthetic_resina(resina_path)
            _make_test_photo(foto_path)

            spec = MedalSpec(
                id="sintetica_teste",
                nome="Fixture sintetica de teste",
                base_path=base_path,
                resina_path=resina_path,
                center_x=center[0],
                center_y=center[1],
                inner_radius=inner_radius,
                overlap_px=1.0,
            )

            resultado = compose_medal(spec, foto_path)

            with Image.open(base_path) as base_img:
                self.assertEqual(resultado.size, base_img.size)
            self.assertEqual(resultado.mode, "RGBA")

            # centro deve estar preenchido pela foto (nao branco, nao transparente)
            cx, cy = int(center[0]), int(center[1])
            r, g, b, a = resultado.getpixel((cx, cy))
            self.assertEqual(a, 255)
            self.assertFalse((r, g, b) == (255, 255, 255))

            # fora da medalha (canto do canvas) deve continuar branco
            r, g, b, a = resultado.getpixel((5, 5))
            self.assertEqual((r, g, b, a), (255, 255, 255, 255))

            # nao deve haver anel vazio: logo dentro do raio interno (a poucos
            # px da parede) o pixel deve estar opaco (foto ou resina), nao
            # branco/transparente
            edge_x = int(cx + inner_radius - 3)
            r, g, b, a = resultado.getpixel((edge_x, cy))
            self.assertEqual(a, 255)

    def test_fit_cover_circle_nao_deforma_e_cobre_totalmente(self):
        img = Image.new("RGB", (400, 100), (10, 20, 30))
        out = fit_cover_circle(img, 250)
        self.assertEqual(out.size, (250, 250))
        # centro do circulo tem que estar opaco (coberto), cantos tem que
        # estar transparentes (fora do circulo, mascara aplicada)
        self.assertEqual(out.getpixel((125, 125))[3], 255)
        self.assertEqual(out.getpixel((2, 2))[3], 0)

    def test_auto_cover_box_e_quadrado_centralizado(self):
        self.assertEqual(auto_cover_box((400, 100)), (150, 0, 250, 100))
        self.assertEqual(auto_cover_box((100, 100)), (0, 0, 100, 100))

    def test_crop_to_box_recorta_exato_e_limita_aos_bordas(self):
        img = Image.new("RGB", (200, 200), (0, 0, 0))
        img.paste((255, 0, 0), (50, 50, 100, 100))  # quadrado vermelho
        recorte = crop_to_box(img, (50, 50, 100, 100))
        self.assertEqual(recorte.size, (50, 50))
        self.assertEqual(recorte.getpixel((0, 0)), (255, 0, 0))

        # caixa que extrapola os limites da imagem: deve ser limitada, nao
        # esticada nem preenchida com nada
        recorte_fora = crop_to_box(img, (-20, -20, 20, 20))
        self.assertEqual(recorte_fora.size, (20, 20))

    def test_fit_manual_circle_usa_o_recorte_escolhido_nao_o_automatico(self):
        # foto onde so o canto superior esquerdo e verde -- o recorte
        # automatico (centralizado) NAO pegaria essa marca, um recorte
        # manual apontando pro canto pega. Precisa ser uma foto RETANGULAR
        # (nao quadrada) -- numa foto ja quadrada o recorte "automatico"
        # e a imagem inteira, o que tornaria o teste sem sentido.
        img = Image.new("RGB", (600, 300), (10, 10, 10))
        img.paste((0, 255, 0), (0, 0, 60, 60))

        auto = fit_manual_circle(img, 100, auto_cover_box(img.size))
        manual = fit_manual_circle(img, 100, (0, 0, 300, 300))

        self.assertNotEqual(auto.getpixel((5, 5))[:3], (0, 255, 0))
        self.assertEqual(manual.getpixel((5, 5))[:3], (0, 255, 0))

    def test_compose_medal_respeita_crop_box_manual(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            base_path = tmp / "base_medalha.png"
            resina_path = tmp / "efeito_resina.png"
            foto_path = tmp / "foto.png"

            center, inner_radius = _make_synthetic_base(base_path)

            img = Image.new("RGB", (600, 300), (10, 10, 10))
            img.paste((0, 255, 0), (0, 0, 60, 60))
            img.save(foto_path)

            _make_synthetic_resina(resina_path)

            spec = MedalSpec(
                id="sintetica_crop_manual",
                nome="Fixture crop manual",
                base_path=base_path,
                resina_path=resina_path,
                center_x=center[0],
                center_y=center[1],
                inner_radius=inner_radius,
                overlap_px=1.0,
            )

            sem_crop = compose_medal(spec, foto_path)
            com_crop = compose_medal(spec, foto_path, crop_box=(0, 0, 300, 300))

            # o quadrado verde ocupa o canto superior-esquerdo do recorte
            # (0-60 de 0-300 -> 0-106 apos redimensionar pro circulo de
            # raio 265); so a fatia perto do canto INTERNO desse quadrado
            # (local ~90,90) fica ao mesmo tempo dentro do verde e dentro
            # do circulo -- por isso o offset e -175, nao -106.
            px = int(center[0] - 175)
            py = int(center[1] - 175)
            # tolerancia: o resize LANCZOS suaviza um pouco a borda entre
            # o verde e o fundo escuro da foto sintetica, entao o pixel
            # pode nao ser um (0,255,0) perfeito -- so precisa estar
            # claramente do lado verde, nao no cinza da base.
            r, g, b = com_crop.getpixel((px, py))[:3]
            self.assertGreater(g, 200)
            self.assertLess(r, 50)
            self.assertLess(b, 50)
            r2, g2, b2 = sem_crop.getpixel((px, py))[:3]
            self.assertFalse(g2 > 200 and r2 < 50 and b2 < 50)


if __name__ == "__main__":
    unittest.main()
