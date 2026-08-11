# Gerador de mockups de medalhas

Compõe mockups fotorrealistas de medalhas personalizadas a partir de camadas
prontas (PNG com transparência) — **sem nenhuma geração por IA**. É apenas
recorte "cover" + máscara circular + alpha compositing com Pillow, na ordem:

1. fundo branco
2. `assets/base_medalha.png` (estrutura metálica, argolas, sombra)
3. imagem do usuário (redimensionada/recortada para preencher a cavidade
   interna, sem deformar, sem sobrar borda)
4. `assets/efeito_resina.png` (vidro/resina, reflexos, sombra da resina)

## Status

Assets reais (`assets/base_medalha.png`, `assets/efeito_resina.png`,
1254×1254px) já calibrados. A cavidade interna foi localizada por
análise de componentes conexos (não a olho): a área branca isolada
dentro do anel tem centro ≈ (645, 685) e raio ≈ 375–384px dependendo do
limiar na borda anti-aliased — valores atuais em
`MEDAL_SPECS["prata_16mm"]` (`config.py`): `center_x=645, center_y=685,
inner_radius=380, overlap_px=3`. `teste_composicao.png` (na raiz do
repo) é o resultado gerado com esses valores; comparar com
`referencias/` para validar antes de gerar o lote completo.

## Instalação

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Uso individual

```bash
python main.py imagem.jpg
# -> saida/imagem_medalha.png
```

## Processamento em lote

```bash
python main.py --pasta entrada
# -> saida/<nome>_medalha.png para cada imagem da pasta
```

## Calibração

A geometria da cavidade interna (onde a foto e a resina entram) fica em
`config.py`, como `MedalSpec` (por padrão `prata_16mm`). Para visualizar
onde o programa *acha* que fica o centro e o raio da cavidade,
sobrepostos na base atual:

```bash
python main.py --calibrar
# -> saida/calibracao_prata_16mm.png
```

A imagem gerada mostra:

- **cruz vermelha** — centro configurado (`center_x`, `center_y`)
- **círculo verde** — raio onde a foto do usuário é recortada (`inner_radius`)
- **círculo azul** — raio onde a resina é posicionada, se diferente do verde

Ajuste os valores em `config.py` (em `MEDAL_SPECS["prata_16mm"]`) até os
círculos baterem exatamente com a parede metálica interna da base e rode
`--calibrar` de novo. Enquanto os valores em pixel (`center_x`,
`center_y`, `inner_radius`) não forem definidos, o programa usa frações
estimadas do tamanho da própria `base_medalha.png`
(`center_x_frac`/`center_y_frac`/`inner_radius_frac`) como ponto de
partida — apenas uma estimativa visual, calibre com os arquivos reais.

Também é possível definir a área com um retângulo em vez de
centro+raio, via `MedalSpec.from_box(..., image_box=(x1, y1, x2, y2))`.

## Estrutura

```
assets/         base_medalha.png, efeito_resina.png (e futuras variantes)
entrada/        imagens a processar em lote
saida/          resultado (<nome>_medalha.png)
referencias/    medalhas reais prontas, só para comparação visual
config.py       geometria e catálogo de bases (MedalSpec)
compositor.py   lógica pura de composição (Pillow)
main.py         CLI (arquivo único, --pasta, --calibrar)
tests/          teste de fumaça do pipeline com fixtures sintéticas
```

## Extensibilidade

Cada base de medalha (tamanho, cor, efeito de resina) é uma entrada em
`MEDAL_SPECS`, em `config.py`. Para adicionar uma medalha 12mm ou uma
base dourada, por exemplo:

```python
MEDAL_SPECS["dourada_12mm"] = MedalSpec(
    id="dourada_12mm",
    nome="Medalha redonda dourada 12mm",
    base_path=ASSETS_DIR / "base_medalha_dourada_12mm.png",
    resina_path=ASSETS_DIR / "efeito_resina.png",
    center_x=..., center_y=..., inner_radius=...,  # calibrar com --calibrar
)
```

e usar com `python main.py imagem.jpg --medalha dourada_12mm`.

O mesmo padrão comporta, no futuro: processamento por CSV (basta iterar
linhas chamando `compose_medal`), outros formatos de base (oval,
quadrada — troque a máscara elíptica/retangular em `compositor.py`), e
uma interface gráfica (o `compositor.py` não depende do CLI, pode ser
importado direto).

## Testes

```bash
.venv/bin/python -m unittest tests/test_compositor.py -v
```

Os testes geram fixtures sintéticas (formas simples desenhadas com
Pillow) em memória/tmp — não usam nem substituem os assets reais.
Validam: a foto preenche a cavidade sem deixar anel vazio, não há
deformação no recorte "cover", a composição preserva RGBA/transparência
corretamente, e o fundo fora da medalha fica branco puro.
