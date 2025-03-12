from flask import Flask, request, jsonify
import requests
from openai import OpenAI

# Configuración de DeepSeek API
api_key = 'sk-e33494f4827746be9d784b126b5b5623'
api_base = 'https://api.deepseek.com'
client = OpenAI(api_key=api_key, base_url=api_base)

# Training data for chatbot
chatbot_train_data = r'C:\Users\tomyy\OneDrive\Documentos\AI Clients\sofisticate_beauty\german_train_data.txt'

with open(chatbot_train_data, 'r', encoding='utf-8') as file:
    business_info = file.read().strip()

# Configuración de WhatsApp Cloud API
TU_PHONE_NUMBER_IDz = '592229297297867'
PHONE_NUMBER_SAMUEL = '529931031354'
WHATSAPP_API_URL = f"https://graph.facebook.com/v22.0/{TU_PHONE_NUMBER_IDz}/messages"
ACCESS_TOKEN = "EAAIcwRTOMDYBO95laz12EEExFJ1ZCMUhSKqicKQH36R2tpQmZB9HapFA73MV3f19bpXdv2nfTSSnSdqFWdg5SHMPMmlRI6PzpGqn44sse8KF87cbRpW9Yz9jSU2OAirjHuZBmO1H1ezvXevuVPYMFlfyzKqWVBddWqf3KFNgh1PBsLTEQAvaKZCZBUzhPtwUnWeC5cqw6xSYs6lgED0cjU61IzUWRCVJZBkdRjoFu5hOcZDv"

app = Flask(__name__)

# Función para interactuar con DeepSeek
def chat_with_deepseek(prompt):
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": business_info},
            {"role": "user", "content": prompt}
        ],
        stream=False
    )
    return str(response.choices[0].message.content.strip())

# Endpoint para recibir mensajes de WhatsApp
VERIFY_TOKEN = '123456'
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    data = request.get_json()
    # print("📩 Webhook recibido:", data)

    if request.method == "GET":  # Validación del Webhook
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if token == VERIFY_TOKEN:
            return challenge  # Responde con el challenge que espera Meta
        return "Token inválido", 403

    elif request.method == "POST":  # Manejo de mensajes
        data = request.get_json()
        if data and "entry" in data:
            for entry in data["entry"]:
                for change in entry["changes"]:
                    if "messages" in change["value"]:
                        for message in change["value"]["messages"]:
                            if "text" in message:
                                user_text = message["text"]["body"]
                                sender = message["from"]
                                # print(f"👤 Usuario: {sender}, 📩 Mensaje: {user_text}")
                                bot_response = chat_with_deepseek(user_text)
                                # print(f"🤖 Respuesta del bot: {bot_response}")
                                send_whatsapp_message(sender, bot_response)
        return jsonify({"status": "received"})

# Función para enviar mensajes de WhatsApp
def send_whatsapp_message(to, text):
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": PHONE_NUMBER_SAMUEL
            , "type": "text", "text": {"body": str(text)}} # to, PHONE_NUMBER_SAMUEL
    # requests.post(WHATSAPP_API_URL, headers=headers, json=data)
    response = requests.post(WHATSAPP_API_URL, headers=headers, json=data)
    # print("📤 Enviando mensaje a WhatsApp:", data)
    # print("📬 Respuesta de WhatsApp:", response.json())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
