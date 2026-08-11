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

Assets reais calibrados em `MEDAL_SPECS["prata_16mm"]` (`config.py`).
`teste_composicao.png` (na raiz do repo) é o resultado gerado com a
calibração atual; comparar com `referencias/` para validar antes de
gerar o lote completo.

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
Chrome do Android, etc. — nada para instalar). Uma imagem mostra a
prévia com um botão "Salvar imagem"; várias imagens baixam um `.zip`
com todas de uma vez (o navegador não deixa escolher uma pasta e salvar
vários arquivos soltos, então o `.zip` é o equivalente prático disso na
web).

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
