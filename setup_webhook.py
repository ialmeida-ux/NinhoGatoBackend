import os
from dotenv import load_dotenv
from gerencianet import Gerencianet

# Carrega as chaves do seu .env local
load_dotenv()

credentials = {
    'client_id': os.environ.get('EFI_CLIENT_ID'),
    'client_secret': os.environ.get('EFI_CLIENT_SECRET'),
    'sandbox': False, 
    'certificate': os.environ.get('EFI_CERTIFICATE_PATH', 'certificado.pem')
}

efi = Gerencianet(credentials)
pix_key = os.environ.get('EFI_PIX_KEY')

# ATENÇÃO: Substitua pela sua URL real do Render
render_url = "https://ninhogato-teste-api-pix.onrender.com"

# O endpoint que programamos no main.py
webhook_url = f"{render_url}/webhook"

print(f"Tentando registrar Webhook para a chave: {pix_key}")
print(f"Destino: {webhook_url}")

try:
    response = efi.pix_config_webhook(
        params={"chave": pix_key}, 
        body={"webhookUrl": webhook_url}
    )
    print("✅ Webhook configurado com sucesso!")
    print("Resposta da Efí:", response)
except Exception as e:
    print("❌ Erro ao configurar Webhook:")
    print(e)