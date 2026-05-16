# Ingere todos os .md da pasta docs/
python ingest.py

# Ingere limpando o índice anterior
python ingest.py --clear

# Diretório personalizado
python ingest.py --docs-dir ./outra_pasta


GEMINI_API_KEY=sua_chave_do_gemini_aqui
POSTGRES_URL=postgresql://usuario:senha@host:5432/ticket_maker


OPENPROJECT_API_URL=http://openproject.ormel.com.br/
OPENPROJECT_TIMEOUT=30
OPENPROJECT_TOKEN=1-230df0411f514a8d10c56152b27cfe5ceec21618b7d738aa05243a7c504b63a9


# Na pasta back/
python -m alembic upgrade head   # cria as tabelas
python ingest.py                  # indexa os Markdowns no PgVector
