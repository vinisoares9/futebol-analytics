import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_FUTEBOL_KEY")
BASE_URL = "https://api.api-futebol.com.br/v1"

headers = {
    "Authorization": f"Bearer {API_KEY}"
}

# Busca as partidas da 1ª rodada do Brasileirão (campeonato_id = 10)
response = requests.get(f"{BASE_URL}/campeonatos/10/rodadas/1", headers=headers)

print("Status code:", response.status_code)
print(response.json())