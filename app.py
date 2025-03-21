import os
from flask import Flask, request, jsonify
import requests
from openai import OpenAI
import datetime
import pandas as pd
import re
import firebase_admin
from firebase_admin import credentials, firestore
import base64

# Firestore
firebase_credentials_base64 = os.getenv('FIREBASE_CREDENTIALS_BASE64')

# Decodificar el JSON desde base64
firebase_credentials_json = base64.b64decode(firebase_credentials_base64).decode('utf-8')
firebase_credentials = json.loads(firebase_credentials_json)

# Inicializar Firebase con las credenciales
cred = credentials.Certificate(firebase_credentials)
firebase_admin.initialize_app(cred)

# Obtener una referencia a Firestore
db = firestore.client()

# Configuración de DeepSeek API
api_key = os.getenv('DEEPSEEK_API_KEY') # 'sk-e33494f4827746be9d784b126b5b5623'
api_base = os.getenv('DEEPSEEK_API_BASE', 'https://api.deepseek.com')
client = OpenAI(api_key=api_key, base_url=api_base)

# Training data for chatbot
chatbot_train_data = os.getenv('CHATBOT_TRAIN_DATA_PATH', 'german_train_data.txt')
with open(chatbot_train_data, 'r', encoding='utf-8') as file:
    business_info = file.read().strip()

# Configuración de WhatsApp Cloud API
TU_PHONE_NUMBER_IDz = os.getenv('WHATSAPP_PHONE_NUMBER_ID') # 592229297297867 (wa_chatbot)
WHATSAPP_API_URL = f"https://graph.facebook.com/v22.0/{TU_PHONE_NUMBER_IDz}/messages"
ACCESS_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN')

app = Flask(__name__)

conversaciones = {}

# Función para interactuar con DeepSeek
def chat_with_deepseek(prompt, historial):
    # Crear la lista de mensajes para DeepSeek
    mensajes = [{"role": "system", "content": business_info}]

    # Agregar el historial de conversaciones
    for mensaje in historial:
        if mensaje["remitente"] == "usuario":
            mensajes.append({"role": "user", "content": mensaje["texto"]})
        elif mensaje["remitente"] == "bot":
            mensajes.append({"role": "assistant", "content": mensaje["texto"]})

    # Agregar el mensaje actual del usuario
    mensajes.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=mensajes,
        stream=False
    )

    respuesta_bot = str(response.choices[0].message.content.strip())

    return respuesta_bot


def almacenar_conversacion(usuario_id, mensaje_usuario, respuesta_bot):
    conversaciones_ref = db.collection('conversaciones').document(usuario_id)

    # Obtener el historial de conversaciones (si existe)
    conversacion_data = conversaciones_ref.get()

    if conversacion_data.exists:
        conversaciones = conversacion_data.to_dict().get('mensajes', [])
    else:
        conversaciones = []

    # Agregar el mensaje del usuario y la respuesta del bot
    conversaciones.append({
        'texto': str(mensaje_usuario),
        'remitente': 'usuario',
        'fecha': datetime.datetime.now().isoformat()  # Convertir datetime a string
    })
    conversaciones.append({
        'texto': str(respuesta_bot),
        'remitente': 'bot',
        'fecha': datetime.datetime.now().isoformat()  # Convertir datetime a string
    })

    # Mantener solo los últimos 10 mensajes
    if len(conversaciones) > 20:
        conversaciones = conversaciones[-20:]

    # Guardar la conversación en Firestore
    conversaciones_ref.set({
        'mensajes': conversaciones
    }, merge=True)

def guardar_info_cliente(usuario_id, nombre, correo):

    # Referencia a la colección de clientes en Firestore
    cliente_ref = db.collection('clientes').document(usuario_id)

    # Guardar la información del cliente
    cliente_ref.set({
        'nombre': nombre,
        'correo': correo,
        'fecha_registro': datetime.datetime.now().isoformat()
    }, merge=True)


def extract_name_and_email(respuesta_bot):
    # Expresiones regulares para extraer el nombre y el correo
    nombre_pattern = r"name:\s*([^\n]+)"
    correo_pattern = r"email:\s*([^\n]+)"

    nombre = re.search(nombre_pattern, respuesta_bot)
    correo = re.search(correo_pattern, respuesta_bot)

    nombre = nombre.group(1).strip() if nombre else None
    correo = correo.group(1).strip() if correo else None

    return nombre, correo


def obtener_historial(usuario_id):
    # Referencia al documento del usuario en la colección 'conversaciones'
    conversaciones_ref = db.collection('conversaciones').document(usuario_id)

    # Obtener el historial de conversaciones (si existe)
    conversacion_data = conversaciones_ref.get()

    if conversacion_data.exists:
        return conversacion_data.to_dict().get('mensajes', [])
    else:
        return []

mensajes_procesados = set()
# Endpoint para recibir mensajes de WhatsApp
VERIFY_TOKEN = '123456'
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":  # Validación del Webhook
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if token == VERIFY_TOKEN:
            return challenge  # Responde con el challenge que espera Meta
        return "Token inválido", 403

    elif request.method == "POST":  # Manejo de mensajes
        data = request.get_json()
        print("📩 Webhook recibido:", data)
        data = request.get_json()
        if data and "entry" in data:
            for entry in data["entry"]:
                for change in entry["changes"]:
                    if "messages" in change["value"]:
                        for message in change["value"]["messages"]:
                            message_id = message.get("id")
                            if message_id in mensajes_procesados:
                                # print(f"⚠️ Mensaje ya procesado: {message_id}")
                                continue  # Ignorar el mensaje
                        
                            mensajes_procesados.add(message_id)
                        
                            if "text" in message:
                                user_text = message["text"]["body"]
                                sender = message["from"]
                                # print(f"👤 Usuario: {sender}, 📩 Mensaje: {user_text}")
                                
                                historial = obtener_historial(sender)
                                bot_response = chat_with_deepseek(user_text, historial)
                                nombre, correo = extract_name_and_email(bot_response)
                                
                                if nombre and correo:
                                    formato_interno = f"- name: [{nombre}] - email: [{correo}]"
                                    print("Formato interno:", formato_interno)  # Para depuración

                                    # Almacenar la información del cliente
                                    guardar_info_cliente(sender, nombre, correo)

                                    prompt = f"The customer has provided his name and email address. \
                                                Dont return the email and name, format. Just continue with the conversation."
                                    bot_response = chat_with_deepseek(prompt, historial)
                                
                
                                almacenar_conversacion(sender, user_text, bot_response)
                                # print(f"🤖 Respuesta del bot: {bot_response}")
                                send_whatsapp_message(sender, bot_response)
                    else:
                        print("Ignorando actualización de estado:", change["value"])
        return jsonify({"status": "received"})

# Función para enviar mensajes de WhatsApp
def send_whatsapp_message(to, text):
    if to.startswith('52'):
        to = to[0:2] + to[3:]
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": str(text)}} # to
    response = requests.post(WHATSAPP_API_URL, headers=headers, json=data)
    # print("📤 Enviando mensaje a WhatsApp:", data)
    # print("📬 Respuesta de WhatsApp:", response.json())  # Verifica errores aquí


@app.route("/conversaciones", methods=["GET"])
def ver_conversaciones():
    # Convertir el diccionario de conversaciones a un formato JSON serializable
    conversaciones_serializables = {}
    for usuario_id, mensajes in conversaciones.items():
        conversaciones_serializables[usuario_id] = mensajes  # Los mensajes ya tienen fechas como strings
    return jsonify(conversaciones_serializables)
    

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
