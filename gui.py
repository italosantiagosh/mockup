"""
Interface grafica do gerador de mockups de medalhas.

Uso:
    python gui.py

Abre uma janela com um botao para selecionar uma ou mais imagens:

- Uma imagem: gera o mockup, mostra a previa na janela e so depois
  pergunta onde salvar (clicar em "Salvar imagem...").
- Varias imagens: pergunta uma pasta de destino e salva todas la
  automaticamente (<nome>_medalha.png para cada uma).

Nao depende de nada alem do que compositor.py/config.py ja usam, mais o
tkinter da biblioteca padrao do Python (em alguns Linux precisa instalar
o pacote do sistema, ex.: `sudo apt install python3-tk`; no Windows/Mac
do instalador oficial do python.org ja vem incluso).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from compositor import compose_medal, load_rgba
from config import IMAGE_EXTENSIONS, get_medal_spec

PREVIEW_MAX_SIDE = 420

FILE_TYPES = [
    ("Imagens", " ".join(f"*{ext}" for ext in IMAGE_EXTENSIONS)),
    ("Todos os arquivos", "*.*"),
]


class MedalhaApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Gerador de Mockups de Medalhas")
        self.root.geometry("520x620")
        self.root.minsize(420, 480)

        self.spec = get_medal_spec()
        self.resultado_atual: Image.Image | None = None
        self.origem_atual: Path | None = None
        self._preview_photo: ImageTk.PhotoImage | None = None

        self._build_widgets()

    def _build_widgets(self) -> None:
        pad = {"padx": 16, "pady": 8}

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)

        self.select_btn = ttk.Button(
            top, text="Selecionar imagem(ns)...", command=self.on_select
        )
        self.select_btn.pack(side="left")

        self.status_var = tk.StringVar(value="Nenhuma imagem selecionada.")
        status_label = ttk.Label(self.root, textvariable=self.status_var, wraplength=480)
        status_label.pack(fill="x", **pad)

        self.preview_frame = ttk.Frame(self.root, relief="groove", borderwidth=1)
        self.preview_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self.preview_label = ttk.Label(
            self.preview_frame, text="A previa aparece aqui apos escolher UMA imagem.",
            anchor="center", justify="center",
        )
        self.preview_label.pack(fill="both", expand=True)

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", **pad)

        self.save_btn = ttk.Button(
            bottom, text="Salvar imagem...", command=self.on_save, state="disabled"
        )
        self.save_btn.pack(side="left")

        self.progress = ttk.Progressbar(self.root, mode="determinate")

    def on_select(self) -> None:
        caminhos = filedialog.askopenfilenames(
            title="Selecione uma ou mais imagens", filetypes=FILE_TYPES
        )
        if not caminhos:
            return

        arquivos = [Path(c) for c in caminhos]
        if len(arquivos) == 1:
            self._processar_unico(arquivos[0])
        else:
            self._processar_lote(arquivos)

    def _processar_unico(self, caminho: Path) -> None:
        self._limpar_preview()
        self.status_var.set(f"Gerando previa de {caminho.name} ...")
        self.root.update_idletasks()
        try:
            resultado = compose_medal(self.spec, caminho)
        except Exception as exc:
            messagebox.showerror("Erro ao gerar mockup", str(exc))
            self.status_var.set("Falha ao gerar a previa. Selecione outra imagem.")
            return

        self.resultado_atual = resultado
        self.origem_atual = caminho
        self._mostrar_preview(resultado)
        self.save_btn.configure(state="normal")
        self.status_var.set(
            f"Previa de {caminho.name} pronta. Clique em \"Salvar imagem...\" para baixar."
        )

    def _mostrar_preview(self, imagem: Image.Image) -> None:
        preview = imagem.convert("RGB")
        preview.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE), Image.LANCZOS)
        self._preview_photo = ImageTk.PhotoImage(preview)
        self.preview_label.configure(image=self._preview_photo, text="")

    def _limpar_preview(self) -> None:
        self.resultado_atual = None
        self.origem_atual = None
        self._preview_photo = None
        self.preview_label.configure(image="", text="A previa aparece aqui apos escolher UMA imagem.")
        self.save_btn.configure(state="disabled")

    def on_save(self) -> None:
        if self.resultado_atual is None or self.origem_atual is None:
            return
        sugestao = f"{self.origem_atual.stem}{self.spec.output_suffix}.png"
        destino = filedialog.asksaveasfilename(
            title="Salvar imagem como",
            initialfile=sugestao,
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
        )
        if not destino:
            return
        try:
            self.resultado_atual.save(destino, format="PNG")
        except Exception as exc:
            messagebox.showerror("Erro ao salvar", str(exc))
            return
        self.status_var.set(f"Salvo em: {destino}")
        messagebox.showinfo("Salvo", f"Imagem salva em:\n{destino}")

    def _processar_lote(self, arquivos: list[Path]) -> None:
        pasta_destino = filedialog.askdirectory(title="Escolha a pasta onde salvar as medalhas")
        if not pasta_destino:
            return
        pasta_destino = Path(pasta_destino)

        self._limpar_preview()
        self.progress.pack(fill="x", padx=16, pady=(0, 8))
        self.progress.configure(maximum=len(arquivos), value=0)
        self.select_btn.configure(state="disabled")

        ok, falhas = 0, []
        for i, caminho in enumerate(arquivos, start=1):
            self.status_var.set(f"Processando {i}/{len(arquivos)}: {caminho.name}")
            self.progress.configure(value=i)
            self.root.update_idletasks()
            try:
                resultado = compose_medal(self.spec, caminho)
                destino = pasta_destino / f"{caminho.stem}{self.spec.output_suffix}.png"
                resultado.save(destino, format="PNG")
                ok += 1
            except Exception as exc:
                falhas.append(f"{caminho.name}: {exc}")

        self.progress.pack_forget()
        self.select_btn.configure(state="normal")

        resumo = f"{ok} imagem(ns) salva(s) em:\n{pasta_destino}"
        if falhas:
            resumo += f"\n\n{len(falhas)} falha(s):\n" + "\n".join(falhas)
            messagebox.showwarning("Concluido com falhas", resumo)
        else:
            messagebox.showinfo("Concluido", resumo)
        self.status_var.set(f"Lote concluido: {ok} ok, {len(falhas)} falha(s).")


def main() -> None:
    try:
        load_rgba(get_medal_spec().base_path)
    except FileNotFoundError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Assets faltando", str(exc))
        return

    root = tk.Tk()
    MedalhaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
