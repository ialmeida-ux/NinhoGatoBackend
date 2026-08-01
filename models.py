from sqlalchemy import Column, Integer, String, Boolean
from database import Base

class Transacao(Base):
    __tablename__ = "transacoes"

    id = Column(Integer, primary_key=True, index=True)
    txid = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, default="PENDENTE")
    payment = Column(Boolean, default=False)
    anonimo = Column(Boolean, default=False)
    
    # Colunas adicionadas para o seu mural de doações
    valor = Column(String)
    nome = Column(String)
    mensagem = Column(String)
