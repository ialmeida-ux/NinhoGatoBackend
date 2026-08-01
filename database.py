import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

# 1. Pegamos a URL do banco que você configurou no .env ou no Render
# IMPORTANTE: Se a URL começar com postgres://, o SQLAlchemy exige que seja postgresql+asyncpg://
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# 2. Criamos o "Motor" que vai gerenciar a comunicação com o Render
engine = create_async_engine(DATABASE_URL, echo=False)

# 3. Criamos a Fábrica de Sessões. A "Sessão" é o que usamos para salvar ou buscar dados.
SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# 4. Criamos a Base. Todas as nossas tabelas vão herdar dessa Base para que o SQLAlchemy as reconheça.
Base = declarative_base()

# 5. Função para fornecer uma sessão de banco de dados para as rotas do FastAPI
async def get_db():
    async with SessionLocal() as session:
        yield session