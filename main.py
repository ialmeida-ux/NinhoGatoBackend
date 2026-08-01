from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from gerencianet import Gerencianet
import uuid
import os
from typing import Optional
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from typing import Optional

# Nossas novas importações de banco de dados
from database import engine, get_db
import models
import crud
from sqlalchemy.ext.asyncio import AsyncSession


load_dotenv()

def str_to_bool(val: str) -> bool:
    return str(val).lower() in ("true", "1", "t", "yes")

# 1. INICIALIZAÇÃO E CRIAÇÃO DAS TABELAS NO BANCO
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Conecta no Render e cria a tabela do PostgreSQL se ela não existir
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    yield 

app = FastAPI(lifespan=lifespan)

# Permite que o frontend HTML local chame a API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Credenciais da Efí
credentials = {
    'client_id': os.environ.get('EFI_CLIENT_ID'),
    'client_secret': os.environ.get('EFI_CLIENT_SECRET'),
    'sandbox': str_to_bool(os.environ.get('EFI_SANDBOX', 'False')),
    'certificate': os.environ.get('EFI_CERTIFICATE_PATH', 'certificado.pem')
}

PIX_KEY = os.environ.get('EFI_PIX_KEY')
efi = Gerencianet(credentials)

class PixRequest(BaseModel):
    valor: str
    nome: Optional[str] = ""
    anonimo: bool = False
    mensagem: Optional[str] = ""

@app.get("/", response_class=HTMLResponse)
def ler_index():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# 2. GERAR O PIX
@app.post("/gerar-pix")
async def gerar_pix(req: PixRequest, db: AsyncSession = Depends(get_db)):
    txid = uuid.uuid4().hex

    body = {
        "calendario": {"expiracao": 3600},
        "valor": {"original": req.valor},
        "chave": PIX_KEY 
    }

    try:
        resposta_cob = efi.pix_create_charge(params={"txid": txid}, body=body)
        loc_id = resposta_cob.get("loc", {}).get("id")
        
        if not loc_id:
            raise HTTPException(status_code=500, detail="Falha ao gerar cobrança")

        resposta_qr = efi.pix_generate_QRCode(params={"id": loc_id})

        qr_image = (resposta_qr.get("imagemQrcode") or resposta_qr.get("imagemQRCode") or resposta_qr.get("qrcode_image"))
        qr_text = (resposta_qr.get("qrcode") or resposta_qr.get("qrCode") or resposta_qr.get("brcode"))

        if not qr_image and "dados" in resposta_qr:
            qr_image = resposta_qr["dados"].get("imagemQrcode")
            qr_text = resposta_qr["dados"].get("qrcode")

        if not qr_image or not qr_text:
            raise HTTPException(status_code=502, detail="Falha ao mapear os dados do QR Code retornados pela Efí.")

        nome_doador = "Anônimo" if req.anonimo or not req.nome else req.nome.strip()

        transaction_data = {
            "status": "PENDENTE",
            "payment": False, 
            "valor": req.valor,
            "nome": nome_doador,
            "mensagem": req.mensagem,
            "qrcode_image": qr_image,
            "qrcode_text": qr_text
        }
        
        # Salvando no PostgreSQL
        await crud.criar_transacao(db, txid, transaction_data)

        return {"txid": txid, "qr_data": transaction_data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# 3. VERIFICAR STATUS DO PIX
@app.get("/status/{txid}")
async def verificar_status(txid: str, db: AsyncSession = Depends(get_db)):
    # Buscando no PostgreSQL
    tx_data = await crud.buscar_transacao_por_txid(db, txid)
    if not tx_data:
        raise HTTPException(status_code=404, detail="Transação não encontrada")
    
    return {"txid": txid, "status": tx_data.status}

@app.api_route("/webhook", methods=["GET", "POST"])
@app.api_route("/webhook/", methods=["GET", "POST"])
@app.api_route("/webhook/pix", methods=["GET", "POST"])
@app.api_route("/webhook/pix/", methods=["GET", "POST"])
async def efi_webhook(request: Request, token: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    
    # 1. VALIDAÇÃO DE SEGURANÇA (Garante que só a Efí acesse)
    TOKEN_SECRETO = "ninhogato_seguro_2026"
    if token != TOKEN_SECRETO:
        print("Tentativa de acesso negada ao Webhook. Token inválido.")
        # Retornamos 403 Forbidden para quem tentar invadir a rota
        raise HTTPException(status_code=403, detail="Acesso negado")

    # 2. Se a Efí mandar um GET apenas para testar se a URL existe...
    if request.method == "GET":
        print("EFÍ FEZ UM PING DE VALIDAÇÃO (GET)")
        return {"status": "200 OK"}

# 5. LISTAR DOAÇÕES PAGAS (PARA O MURAL)
@app.get("/doacoes")
async def listar_doacoes(db: AsyncSession = Depends(get_db)):
    # Buscando diretamente a lista de transações pagas do banco
    transacoes = await crud.listar_doacoes_pagas(db)
    
    doacoes_pagas = []
    for info in transacoes:
        doacoes_pagas.append({
            "nome": info.nome,
            "valor": info.valor,
            "mensagem": info.mensagem
        })
            
    return {"doacoes": doacoes_pagas}
