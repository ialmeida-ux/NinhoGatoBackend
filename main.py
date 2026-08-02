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

    nome_preenchido = req.nome.strip() if req.nome else ""
    
    if not nome_preenchido and not req.anonimo:
        # Se os dois estiverem vazios, encerramos a requisição aqui mesmo com Erro 400
        raise HTTPException(
            status_code=400, 
            detail="Para prosseguir, informe um nome ou selecione a opção de doação anônima."
        )
    
    txid = uuid.uuid4().hex

    # Garante que o valor tenha sempre o formato decimal correto (ex: "20.00" ou "0.01") exigido pela Efí
    valor_formatado = f"{float(req.valor.replace(',', '.')):.2f}"

    body = {
        "calendario": {"expiracao": 3600},
        "valor": {"original": valor_formatado},
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

        nome_real = req.nome.strip() if req.nome else ""

        transaction_data = {
            "status": "PENDENTE",
            "payment": False, 
            "anonimo": req.anonimo, # 🔴 ENVIANDO A FLAG
            "valor": req.valor,
            "nome": nome_real,
            "mensagem": req.mensagem
        }
        
        # Salvando no PostgreSQL
        await crud.criar_transacao(db, txid, transaction_data)

        return {
            "txid": txid, 
            "qrcode_image": qr_image, 
            "qrcode_text": qr_text, 
            "qr_data": transaction_data
        }

        return {"txid": txid, "qr_data": transaction_data}

    except Exception as e:
        # 🔴 ISSO VAI FORÇAR O RENDER A MOSTRAR O ERRO
        print(f"=====================================")
        print(f"ERRO FATAL NA GERAÇÃO DO PIX: {str(e)}")
        print(f"=====================================")
        
        # Devolvemos o erro técnico para a tela para facilitar
        raise HTTPException(
            status_code=500, 
            detail=f"Erro interno: {str(e)}"
        )
    
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
    
    TOKEN_SECRETO = "ninhogato_seguro_2026"
    
    if token != TOKEN_SECRETO and token != f"{TOKEN_SECRETO}/pix":
        return {"status": "200 OK"}

    if request.method == "GET":
        return {"status": "200 OK"}
    
    try:
        payload = await request.json()
        
        # 🔴 MÁGICA DA OBSERVABILIDADE: flush=True força o Render a exibir o log na mesma hora!
        print("\n===================================", flush=True)
        print("WEBHOOK RECEBIDO DA EFÍ:", payload, flush=True)
        print("===================================\n", flush=True)
    
        if "pix" in payload:
            for pagamento in payload["pix"]:
                txid = pagamento.get("txid")
                print(f"🔍 Buscando TXID no banco: {txid}", flush=True)
                
                if txid:
                    # Tenta atualizar no banco
                    tx_atualizada = await crud.marcar_pix_como_pago(db, txid)
                    
                    if tx_atualizada:
                        print(f"✅ SUCESSO: Pix {txid} salvo como PAGO no banco!", flush=True)
                    else:
                        print(f"❌ ALERTA: TXID {txid} não existe no nosso banco de dados. (Foi pago um código antigo?)", flush=True)
                        
    except Exception as e:
        print(f"❌ ERRO CRÍTICO NO WEBHOOK: {e}", flush=True)
            
    return {"status": "200 OK"}

# 5. LISTAR DOAÇÕES PAGAS (PARA O MURAL)
@app.get("/doacoes")
async def listar_doacoes(db: AsyncSession = Depends(get_db)):
    transacoes = await crud.listar_doacoes_pagas(db)
    
    doacoes_pagas = []
    total_arrecadado = 0.0 # 🔴 Variável para guardar a soma
    
    for info in transacoes:
        nome_exibicao = "Doador Anônimo" if info.anonimo or not info.nome else info.nome
        
        # Converte a string "10.00" ou "10,00" para float e soma
        try:
            valor_limpo = info.valor.replace(',', '.')
            total_arrecadado += float(valor_limpo)
        except ValueError:
            pass # Ignora se houver algum erro de formatação em doações antigas
            
        doacoes_pagas.append({
            "nome": nome_exibicao,
            "valor": info.valor,
            "mensagem": info.mensagem
        })
            
    return {
        "doacoes": doacoes_pagas,
        "total_arrecadado": total_arrecadado # 🔴 Enviando o total consolidado
    }
