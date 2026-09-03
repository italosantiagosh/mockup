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

Todas as 6 bases cadastradas em `MEDAL_SPECS` (`config.py`) estão
calibradas com os assets reais: `prata_16mm` (Medalha 1 lado Inox),
`entremeio_prata` e `entremeio_ouro_velho` (para terço), `chaveiro`
(Chaveiro 1 lado) e `medalha_2lados_prata`/`medalha_2lados_ouro_velho`
(Medalha 2 lados). Nos entremeios/chaveiro/medalha 2 lados a cavidade
interna forma um círculo completo e ininterrupto (as argolas ficam
inteiramente por fora do anel/bezel, sem afinar a parede), então nenhum
`keepout_boxes` foi necessário — diferente da `prata_16mm` original
antes de virar "círculo perfeito". Todos reaproveitam
`assets/efeito_resina.png` por enquanto (cliente decide depois se manda
um efeito de resina diferente pra alguma peça específica).

Nos entremeios e na medalha de 2 lados, `resina_radius` é maior que o
raio da foto (`inner_radius + espessura_da_borda/2`) — pedido do
cliente em 2026-09-02/03 pra a resina avançar visivelmente por cima do
aro metálico, não só cobrir exatamente o mesmo círculo da foto. A
espessura de cada borda foi medida por varredura radial (raio externo -
raio interno do aro), documentado nos comentários de `config.py`.

`teste_composicao.png` (na raiz do repo) é o resultado gerado com a
calibração da `prata_16mm`; comparar com `referencias/` para validar
antes de gerar o lote completo.

### Peças de 2 lados

`medalha_2lados_prata`/`ouro_velho` são bases físicas próprias (aro fino,
sem disco sólido atrás — arquivo bem diferente da `prata_16mm`).
`entremeio_2lados_*` **não** é uma base nova: é a mesma
`entremeio_prata`/`entremeio_ouro_velho` de 1 lado, só usada duas vezes
(uma foto na frente, outra no verso) — decisão replicada do repositório
`catalogo` (site), que já tinha essa peça em produção (ver
`services/gerador/config.py` e o mapeamento `(formato, cor) -> spec_id`
em `app.py` de lá). Na versão web daqui (`app.py`/`templates/index.html`),
um estilo "2 lados" pede as 2 fotos de uma vez, abre o editor de recorte
duas vezes seguidas (frente, depois verso) e gera **uma única prévia
lado a lado** (frente | verso) pra revisão/aprovação — sem download
separado por lado nem suporte a lote ainda (só fluxo de peça única).

## Instalação

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

No Linux, a interface gráfica (`gui.py`) também precisa do pacote de
sistema do Tk, que não vem pelo pip: `sudo apt install python3-tk` (no
Windows/Mac do instalador oficial do python.org isso já vem incluso).

## Interface gráfica

```bash
python gui.py
```

Abre uma janela para escolher uma ou mais imagens:

- **Uma imagem**: gera o mockup, mostra a prévia na janela e só depois
  oferece "Salvar imagem..." para escolher onde baixar.
- **Várias imagens**: pergunta uma pasta de destino e salva todas lá
  automaticamente (`<nome>_medalha.png` para cada uma).

## Versão web (usar do celular)

```bash
.venv/bin/python app.py
# abre em http://localhost:8000
```

Mesma ideia da GUI, mas numa página web (funciona no Safari do iPhone,
Chrome do Android, etc. — nada para instalar).

Quando há mais de uma base cadastrada em `MEDAL_SPECS`, a tela inicial
mostra um seletor de estilo (chips) antes de escolher a(s) imagem(ns) —
o nome de cada opção vem do campo `nome` do `MedalSpec` correspondente.

**Uma imagem**: antes de gerar, um editor mostra a foto com um círculo
por cima — arraste para posicionar, use o controle deslizante pra dar
zoom (nunca ultrapassa os limites da própria foto, sem preencher com
branco/preto). Depois de gerar, aparecem 4 botões:
- **Baixar prévia** — a medalha pronta;
- **Baixar imagem recortada (1:1)** — só o recorte escolhido, quadrado,
  sem moldura da medalha, pronto pra usar em outro programa (ex.: o de
  adesivos);
- **Reposicionar** — volta pro editor de recorte com a última posição/
  zoom escolhidos, pra ajustar;
- **Gerar outra** — recomeça do zero.

**Várias imagens de uma vez**: primeiro pergunta se você quer revisar o
recorte de cada uma (abre o mesmo editor, uma imagem por vez) ou gerar
tudo direto com o recorte automático centralizado. No fim, baixa um
`.zip` com todas as prévias — o navegador não deixa escolher uma pasta e
salvar vários arquivos soltos de uma vez, então o `.zip` é o equivalente
prático disso na web. Se você revisou o recorte de cada uma, tem também
um segundo botão pra baixar as imagens recortadas 1:1 de todas, no
ângulo que você escolheu em cada uma.

**Estilo "2 lados"** (Medalha 2 lados, Entremeio 2 lados): ao escolher
um desses chips, o campo de upload passa a exigir exatamente 2 fotos
escolhidas juntas (frente e verso) — escolher 1 ou 3+ mostra um aviso
pedindo pra escolher as 2 juntas. O editor de recorte abre duas vezes
seguidas ("Frente (1/2)", depois "Verso (2/2)") e o resultado é **uma
única prévia com as duas faces lado a lado**, com um botão "Baixar
prévia" só (sem recorte 1:1 separado por lado). "Reposicionar" refaz o
recorte dos dois lados de novo, pré-carregado com a última posição de
cada um. Esse fluxo só existe pra peça única — os estilos "2 lados"
ainda não aparecem no modo de lote (várias imagens de uma vez).

### Publicar no Render (acesso de qualquer lugar, não só na mesma rede)

1. Suba este repositório no GitHub (se ainda não estiver lá).
2. Crie uma conta em [render.com](https://render.com) (tem plano
   gratuito).
3. "New" → "Blueprint" → conecte o repositório. O `render.yaml` já
   configura tudo (comando de build e de start) — é só confirmar.
   Se preferir configurar manualmente em vez do Blueprint: "New" → "Web
   Service", conecte o repo, e preencha:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --timeout 90`
4. Espere o deploy terminar; o Render dá uma URL pública
   (`https://algo.onrender.com`) — abra ela no Safari do iPhone e
   adicione à tela de início se quiser que pareça um app.

No plano gratuito o serviço "dorme" depois de um tempo sem uso e demora
uns 30-50s para acordar no primeiro acesso — normal, não é erro.

## Uso individual (linha de comando)

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
gui.py          interface gráfica de desktop (tkinter)
app.py          versão web (Flask), para usar do celular
templates/      HTML da versão web
Procfile        comando de start para hospedagem (Render/Railway/etc.)
render.yaml     configuração de deploy no Render
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
linhas chamando `compose_medal`) e outros formatos de base (oval,
quadrada — troque a máscara elíptica/retangular em `compositor.py`).
`compositor.py` não depende de nenhuma das interfaces — `main.py`
(CLI), `gui.py` (desktop) e `app.py` (web) só chamam `compose_medal`.

## Testes

```bash
.venv/bin/python -m unittest tests/test_compositor.py -v
```

Os testes geram fixtures sintéticas (formas simples desenhadas com
Pillow) em memória/tmp — não usam nem substituem os assets reais.
Validam: a foto preenche a cavidade sem deixar anel vazio, não há
deformação no recorte "cover", a composição preserva RGBA/transparência
corretamente, e o fundo fora da medalha fica branco puro.
