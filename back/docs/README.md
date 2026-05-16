# Documentação para Base de Conhecimento (RAG)

Esta pasta contém os arquivos Markdown que serão utilizados como base de conhecimento pelo sistema de RAG.

## Estrutura

Organize os arquivos da seguinte forma:

```
docs/
├── nome_do_projeto/
│   ├── visao_geral.md
│   ├── funcionalidades.md
│   ├── erros_comuns.md
│   └── faq.md
└── ...
```

## Como funciona

Ao executar o script de ingestão (`ingest.py`), todos os arquivos `.md` desta pasta serão:
1. Lidos e divididos em blocos menores (chunks)
2. Transformados em embeddings vetoriais pelo Gemini
3. Salvos no PostgreSQL com pgvector, associados ao nome do projeto (subpasta)

## Executar ingestão

```bash
python ingest.py
```

> **Atenção**: Sempre que adicionar ou atualizar arquivos de documentação, execute o script de ingestão novamente para atualizar a base de conhecimento.
