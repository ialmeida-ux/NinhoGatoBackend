from gerencianet import Gerencianet
import os
from dotenv import load_dotenv

load_dotenv()

# Carregando credenciais
credentials = {
    'client_id': os.environ.get('EFI_CLIENT_ID'),
    'client_secret': os.environ.get('EFI_CLIENT_SECRET'),
    'sandbox': False, # Como estamos em produção
    'certificate': os.environ.get('EFI_CERTIFICATE_PATH', 'certificado.pem')
}

efi = Gerencianet(credentials)

# 1. Definindo a URL segura com o Token
TOKEN_SECRETO = "ninhogato_seguro_2026" # Precisa ser o mesmo que colocamos no main.py
render_url = "https://ninhogato-teste-api-pix.onrender.com"
webhook_url = f"{render_url}/webhook?token={TOKEN_SECRETO}"

params = {
    'chave': os.environ.get('EFI_PIX_KEY')
}

body = {
    'webhookUrl': webhook_url
}

# 2. O CABEÇALHO MÁGICO LIBERADO PELO BANCO
headers = {
    'x-skip-mtls-checking': 'true'
}

print(f"Tentando registrar Webhook para a chave: {params.get('chave')}")
print(f"Destino seguro: {webhook_url}")

try:
    # A SDK Python da Efí permite enviar headers customizados assim:
    resposta = efi.pix_config_webhook(params=params, body=body, headers=headers)
    print("\n✅ WEBHOOK CONFIGURADO COM SUCESSO!")
    print(resposta)
except Exception as e:
    print("\n❌ Falha ao configurar webhook:")
    print(e)