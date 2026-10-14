# BioFut

Site e ferramentas da pelada BioFut: tabela do campeonato e estatísticas que se atualizam sozinhas (WhatsApp, prints de súmula e o histórico do Excel), mais as camadas de zoeira por cima: draft, BioBet, cartinhas, bot de WhatsApp.

Projeto feito pela galera do grupo, para o grupo. Quer ajudar? Leia o [CONTRIBUTING.md](CONTRIBUTING.md) e pegue uma issue. Issues com etiqueta `bounty` pagam em gols e assistências: veja [BOUNTIES.md](BOUNTIES.md).

## O que já existe

- `site/`: o site no ar em https://biofut.h-brain.org. Python puro (stdlib): tabela, jogos, perfis, cartinhas,
  lista + draft da semana, BioBet, resenha e Pix. Os jogos vêm ao vivo da planilha do grupo (a cada 10 min).
  `python server.py` roda local; precisa de um `biofut.json` (gerado por `build_data.py`, fora do git).
- `dashboard/`: o B.D.S.M. (BioFut Department of Statistical Magic), dashboard React + Vite + Tailwind + recharts de 2025.

Deploy (`site/deploy.ps1`, `bot/deploy-bot.ps1`): defina `BIOFUT_SSH_KEY`, `BIOFUT_HOST_IP`, `CF_ZONE_ID` e `CF_TOKEN_FILE` no ambiente.

## O que não entra no repositório

Dados pessoais do grupo (planilha, nomes, telefones, export do WhatsApp, fotos). Eles ficam fora do git (`.gitignore`). Para desenvolver, use dados de exemplo.

## Ajude a manter o site no ar

Veja [DONATE.md](DONATE.md).

## Licença

MIT. Veja [LICENSE](LICENSE).
