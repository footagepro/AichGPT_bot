from typing import Optional
import telebot
import openai
from openai import OpenAI
from dotenv import load_dotenv
import json
import os
from datetime import datetime, timedelta
import time
from pydub import AudioSegment
from telebot.util import extract_arguments, extract_command
from telebot import types
import base64
import requests
import threading
import schedule
from yookassa import Configuration, Payment, Webhook
from flask import Flask, request, jsonify
import hmac
import hashlib

# ===================== PAYMENT INTEGRATION =====================
PAYMENTS_FILE = "payments.json"
payments = {}

def load_payments():
    if os.path.exists(PAYMENTS_FILE):
        with open(PAYMENTS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_payments():
    with open(PAYMENTS_FILE, "w") as f:
        json.dump(payments, f, indent=4)

def run_webhook_server():
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting webhook server on port {port}")
    bot.send_message(ADMIN_ID, f"🌐 Webhook server started on port {port}")
    app.run(host='0.0.0.0', port=port)

def payment_check_scheduler():
    schedule.every(10).minutes.do(check_pending_payments)
    while True:
        schedule.run_pending()
        time.sleep(60)

def check_pending_payments():
    for payment_id, payment_data in list(payments.items()):
        if payment_data["status"] == "pending":
            payment = Payment.find_one(payment_id)
            if payment.status == "succeeded":
                process_successful_payment(payment_id)

def process_successful_payment(payment_id):
    if payment_id not in payments:
        print(f"Payment {payment_id} not found in local database")
        return

    payment_data = payments[payment_id]  # Fix: payment_data was undefined
    user_id = payment_data["user_id"]
    if not is_user_exists(user_id):
        print(f"User {user_id} not found for payment {payment_id}")
        return

    if 'premium_tokens' in tariff:
        if "premium_balance" not in data[user_id]:
            data[user_id]["premium_balance"] = 0
        data[user_id]["premium_balance"] += tariff["premium_tokens"]

    if 'images' in tariff:
        if "image_balance" not in data[user_id]:
            data[user_id]["image_balance"] = 0
        data[user_id]["image_balance"] += tariff["images"]

    update_json_file(data)
    payments[payment_id]["status"] = "completed"
    save_payments()

    bot.send_message(user_id, f"✅ Оплата прошла успешно! Баланс пополнен по тарифу {tariff['name']}")

# Flask app for webhooks
app = Flask(__name__)

@app.route('/health')
def health_check():
    return jsonify({"status": "ok"}), 200

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    event_json = request.json
    try:
        # Verify signature
        signature = request.headers.get('Yookassa-Signature')
        secret_key = os.getenv("WEBHOOK_SECRET_KEY").encode('utf-8')
        digest = hmac.new(secret_key, request.data, hashlib.sha256).hexdigest()

        if signature != digest:
            print("Invalid signature")
            return jsonify({"status": "invalid signature"}), 403

        payment = event_json['object']
        if event_json['event'] == 'payment.succeeded':
            process_successful_payment(payment['id'])
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 400
# ================== END PAYMENT INTEGRATION ==================

DEFAULT_MODEL = "gpt-3.5-turbo-0125"  # 16k
PREMIUM_MODEL = "gpt-4o"  # 128k tokens context window
MAX_REQUEST_TOKENS = 4000  # max output tokens for one request (not including input tokens)
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant named Alexa."

# Актуальные цены можно взять с сайта https://openai.com/pricing
PRICE_1K = 0.0015  # price per 1k tokens in USD
PREMIUM_PRICE_1K = 0.015  # price per 1k tokens in USD for premium model
IMAGE_PRICE = 0.08  # price per generated image in USD
WHISPER_MIN_PRICE = 0.006  # price per 1 minute of audio transcription in USD

DATE_FORMAT = "%d.%m.%Y %H:%M:%S"  # date format for logging
UTC_HOURS_DELTA = 3  # time difference between server and local time in hours (UTC +3)

NEW_USER_BALANCE = 30000  # balance for new users
REFERRAL_BONUS = 20000  # bonus for inviting a new user
FAVOR_AMOUNT = 30000  # amount of tokens per granted favor
FAVOR_MIN_LIMIT = 10000  # minimum balance to ask for a favor

# Позволяет боту "помнить" поледние n символов диалога с пользователем за счет увеличенного расхода токенов (округляется вниз до целого сообщения)
DEFAULT_CHAT_CONTEXT_LENGTH = 5000  # default max length of chat context in characters.
CHAT_CONTEXT_FOLDER = "chat_context/"

# load .env file with secrets
load_dotenv()

# Load OpenAI API credentials from .env file
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Create a new Telebot instance
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))  # Fixed bot initialization
