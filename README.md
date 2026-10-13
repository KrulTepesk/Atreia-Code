# Meta Overlay

Overlay para **Aion 2** (Windows): avisos, mapa de coletáveis, farm de pet e medidor de dano.
Não lê a memória do jogo nem mexe em arquivos dele.

## O que faz
- **Festival do Shugo** — aviso com som 5 e 1 minuto antes (horários configuráveis).
- **Rifts e chefes do mundo** — aviso 5 minutos antes e na hora, com mini-mapa do local.
- **Mapa de coletáveis** — Elyos, Asmodian e Abismo (com o mapa de Reshanta Inferior), ícone de cada recurso, filtros e "coletado".
- **Minimapa do Alt+M** — reconhece onde você está e desenha os recursos por cima; clique no ícone
  para marcar a coleta e iniciar um timer de renascimento (5 min).
- **Farm de pet automático (experimental)** — lê o tráfego do jogo: ao matar um monstro que dá alma de pet o farm começa
  sozinho; cada abate e cada alma que você ganha são contados; lista os monstros de pet da região onde você está.
- **Hidden Cubes** — no mapa de coletáveis, os locais onde o cubo *pode* nascer (Verteron, Altgard, Eltnen e
  Morheim). Não é garantido que o cubo esteja em todos.
- **Chefes de campo** — percebe sozinho quando um field boss morre perto de você e avisa 5 min antes e na hora
  em que ele renasce, com mini-mapa do local (ou marque "Morreu agora").
- **Medidor de DPS (desligado por padrão)** — lê o tráfego do jogo pelo Npcap; mostra
  dano, DPS, crítico, dupla chance, cura, a classe de cada jogador e o detalhe por habilidade; mostra a luta atual ou a sessão inteira.
- **PvP (experimental)** — um som quando você mata um jogador e outro quando dá assistência (você bateu e outro levou o
  abate); os dois sons e volumes podem ser trocados. Automático, pela mesma leitura do tráfego do medidor de DPS.
- Vários monitores, travar/destravar overlays, português, inglês e espanhol.

## Instalar (usuário comum)
**[⬇ Baixar o MetaOverlay-Setup.exe](https://github.com/KrulTepesk/Meta-Overlay/releases/latest/download/MetaOverlay-Setup.exe)**
— abra e instale. Não precisa de Python nem de baixar o código.
O Npcap só é necessário para o DPS (o instalador oferece instalar).
Ao instalar uma versão nova, a anterior é removida antes (inclusive a do antigo nome "Atreia Code");
as suas configurações são mantidas.

> O botão verde **Code → Download ZIP** é o código-fonte, para quem quer montar o programa.

## Gerar o instalador
No Windows, rode `CRIAR_INSTALADOR.bat`. Ele baixa o que faltar (Python, bibliotecas, Inno Setup,
ícones das habilidades) e gera `saida\MetaOverlay-Setup.exe`.
Também dá para gerar pelo GitHub: aba **Actions → Gerar instalador → Run workflow**.

## Rodar pelo código
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python overlay\main.py
```

## Aviso
Projeto de fã, sem ligação com a NCSOFT. Aion 2 e seus nomes, mapas e ícones pertencem aos donos.
Programas externos podem ir contra as regras do jogo: use por sua conta e risco.
