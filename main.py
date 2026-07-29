from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from gerencianet import Gerencianet
import uuid
from db_manager import init_db, get_transaction, save_transaction
from typing import Optional
import os
from dotenv import load_dotenv

# 4. NOVA ROTA: Listar apenas as doações pagas
import json
from db_manager import DB_FILE, db_lock

load_dotenv()

def str_to_bool(val: str) -> bool:
    return str(val).lower() in ("true", "1", "t", "yes")

app = FastAPI()

# Permite que o frontend HTML local chame a API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Credenciais da Efí (Substitua pelos seus dados)
credentials = {
    'client_id': os.environ.get('EFI_CLIENT_ID'),
    'client_secret': os.environ.get('EFI_CLIENT_SECRET'),
    'sandbox': str_to_bool(os.environ.get('EFI_SANDBOX', 'False')),
    'certificate': os.environ.get('EFI_CERTIFICATE_PATH', 'certificado.pem')
}

# A variável que o corpo da requisição vai usar:
PIX_KEY = os.environ.get('EFI_PIX_KEY')


efi = Gerencianet(credentials)

# Inicializa o JSON vazio se não existir
init_db()

class PixRequest(BaseModel):
    valor: str
    nome: Optional[str] = ""
    anonimo: bool = False
    mensagem: Optional[str] = ""

def str_to_bool(val: str) -> bool:
    return str(val).lower() in ("true", "1", "t", "yes")

@app.get("/", response_class=HTMLResponse)
def ler_index():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

    
@app.post("/gerar-pix")
def gerar_pix(req: PixRequest):
    txid = uuid.uuid4().hex

    # Como conversamos, o body do banco central não precisa do devedor 
    # para a chave aleatória/email funcionar de forma anônima ou não
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

        # Lógica de negócio: Tratar nome anônimo
        nome_doador = "Anônimo" if req.anonimo or not req.nome else req.nome.strip()

        # Salvando os novos campos, incluindo payment: False
        transaction_data = {
            "status": "PENDENTE",
            "payment": False, 
            "valor": req.valor,
            "nome": nome_doador,
            "mensagem": req.mensagem,
            "qrcode_image": qr_image,
            "qrcode_text": qr_text
        }
        save_transaction(txid, transaction_data)

        return {"txid": txid, "qr_data": transaction_data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/status/{txid}")
def verificar_status(txid: str):
    tx_data = get_transaction(txid)
    if not tx_data:
        raise HTTPException(status_code=404, detail="Transação não encontrada")
    return {"txid": txid, "status": tx_data["status"]}

# Rota que a Efí chamará quando o Pix for pago
@app.post("/webhook(/pix)?")
async def efi_webhook(request: Request):
    payload = await request.json()
    
    # A Efí envia um array 'pix' com os pagamentos recebidos
    if "pix" in payload:
        for pagamento in payload["pix"]:
            txid = pagamento.get("txid")
            if txid:
                tx_data = get_transaction(txid)
                if tx_data:
                    tx_data["status"] = "PAGO"
                    tx_data["payment"] = True # Flag que autoriza exibir no mural
                    save_transaction(txid, tx_data)
    return {"status": "200 OK"}

@app.get("/doacoes")
def listar_doacoes():
    with db_lock:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
    
    doacoes_pagas = []
    
    for txid, info in data.items():
        if info.get("payment") is True:
            doacoes_pagas.append({
                "nome": info.get("nome"),
                "valor": info.get("valor"),
                "mensagem": info.get("mensagem")
            })
            
    return {"doacoes": list(reversed(doacoes_pagas))}