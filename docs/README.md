# Documentação do Ro-DOU NER

Comece pela [página inicial](wiki/Home.md). Os guias em `docs/wiki/` são a fonte principal da documentação e acompanham o código na mesma branch.

## Organização e escrita

- Use Markdown compatível com GitHub, uma página por assunto e nomes sem espaços ou acentos.
- Apresente objetivo e pré-requisitos antes dos comandos; explique a saída e as limitações relevantes.
- Use títulos em ordem, blocos com linguagem e tabelas para parâmetros ou comparações.
- Escreva em português brasileiro e mantenha nomes de comandos, campos e labels como no código.
- Centralize contratos técnicos na página responsável; nas demais, forneça um link.
- Separe comportamento implementado, exemplos ilustrativos e evidências históricas.
- Use links relativos entre páginas e caminhos para fontes do repositório.

`Home.md` é a entrada; `_Sidebar.md` e `_Footer.md` seguem os nomes especiais da GitHub Wiki. Dentro do repositório, a navegação usa links Markdown convencionais com extensão `.md`.

## Publicar na GitHub Wiki

A Wiki possui um repositório separado, `ro-dou-ner.wiki.git`. Um push nesta branch atualiza a documentação do código; a publicação na Wiki é uma operação independente. A [documentação oficial do GitHub](https://docs.github.com/en/communities/documenting-your-project-with-wikis/adding-or-editing-wiki-pages) descreve criação e clonagem, e o [guia de navegação](https://docs.github.com/en/communities/documenting-your-project-with-wikis/creating-a-footer-or-sidebar-for-your-wiki) explica sidebar e footer.

Depois de habilitar a Wiki e criar sua primeira página no GitHub, clone-a em um diretório separado. A partir da raiz deste projeto:

```bash
git clone https://github.com/xxggabriel/ro-dou-ner.wiki.git ../ro-dou-ner-wiki
```

Para preparar as páginas, este comando copia apenas os arquivos Markdown, adapta links entre páginas para os slugs da Wiki e transforma links para código em URLs da branch documentada:

```bash
python3 - <<'PY'
import re
from pathlib import Path
from urllib.parse import quote

source = Path("docs/wiki").resolve()
target = Path("../ro-dou-ner-wiki").resolve()
root = Path.cwd().resolve()
if not (target / ".git").exists():
    raise SystemExit("Clone a Wiki antes de preparar as páginas.")
base = "https://github.com/xxggabriel/ro-dou-ner/blob/feat/inlabs-ner-architecture/"
for page in source.glob("*.md"):
    def convert(match):
        label, link = match.groups()
        if link.startswith("../../"):
            path, _, anchor = link.partition("#")
            relative = (source / path).resolve().relative_to(root)
            link = base + quote(relative.as_posix())
            if anchor:
                link += "#" + anchor
        elif re.fullmatch(r"[\w-]+\.md(?:#[\w-]+)?", link):
            link = link.replace(".md", "", 1)
        return f"[{label}]({link})"
    content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", convert, page.read_text())
    (target / page.name).write_text(content, encoding="utf-8")
PY
```

Revise o diff no clone da Wiki, os links e a renderização antes de criar um commit e fazer push na branch padrão da Wiki. O comando pode sobrescrever páginas de mesmo nome, mas não remove páginas antigas; remova arquivos obsoletos de forma explícita quando necessário.
