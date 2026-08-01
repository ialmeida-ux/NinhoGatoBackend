from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import Transacao

async def buscar_transacao_por_txid(db: AsyncSession, txid: str):
    query = select(Transacao).where(Transacao.txid == txid)
    resultado = await db.execute(query)
    return resultado.scalars().first()

async def criar_transacao(db: AsyncSession, txid: str, dados: dict):
    nova_transacao = Transacao(
        txid=txid,
        status=dados.get("status", "PENDENTE"),
        payment=dados.get("payment", False),
        anonimo=dados.get("anonimo", False),  
        valor=dados.get("valor"),
        nome=dados.get("nome"),
        mensagem=dados.get("mensagem"),
    )
    db.add(nova_transacao)
    await db.commit()
    await db.refresh(nova_transacao)
    return nova_transacao

async def marcar_pix_como_pago(db: AsyncSession, txid: str):
    transacao = await buscar_transacao_por_txid(db, txid)
    if transacao:
        transacao.status = "PAGO"
        transacao.payment = True
        await db.commit()
        await db.refresh(transacao)
    return transacao

async def listar_doacoes_pagas(db: AsyncSession):
    # Busca todas as transações pagas, ordenando das mais recentes para as mais antigas (.desc())
    query = select(Transacao).where(Transacao.payment == True).order_by(Transacao.id.desc())
    resultado = await db.execute(query)
    return resultado.scalars().all()