import sqlite3
import smtplib
import uuid
import logging
import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext,CallbackQueryHandler
import asyncio
import aiosqlite
import aiosmtplib
import ssl
from email.message import EmailMessage

load_dotenv()

TOKEN = os.environ['TOKEN']
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Convert to integer
SECOND_ADMIN_ID = int(os.getenv("SECOND_ADMIN_ID"))  # Convert to integer
DATABASE = os.getenv("DATABASE")

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

running_tests = {}

def ensure_user_exists(user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (id, balance) VALUES (?, 0)", (user_id,))
    conn.commit()
    conn.close()

command_message = (
        "Available Commands:\n"
        "1. /start -> Welcomes you to the bot, Giving you a brief insight.\n"
        "2. /add_funds -> Enables you to top up your wallet via bitcoin. Eg. /add_funds 40.\n"
        "3. /sendmail -> Enables you to perform SMTP tests to existing SMTPs in the system Eg. /sendmail johndoe@doe.com\n"
        "4. /stop -> interruputs on going smtp tests if you're satisfied with the SMTP test .\n"
        "5. /buy -> Enables you to buy SMTP credentials using a unique order id that is generated when you run /sendmail command  Eg. /buy 04958.\n"
        "6. /verify -> Enables you to verify your payment by sending a screenshot of the payment made.\n"
        "7. /balance -> Enables you to check your current balance.\n"
        "PS: All SMTPs on this bot are $10 each"
    )
async def start(update: Update, context):
    user_id = update.effective_user.id
    ensure_user_exists(user_id)
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    balance = row[0] if row else 0.0
    welcome_message  = (
        f"Welcome to SMTP Bot! Your current balance is 💰 ${balance}. Please use the /add_funds command followed by your amount top up your account. In the meantime you can run /sendmail command followed by your receiving mail to test out SMTPs\n\n"
    )
    await update.message.reply_text(welcome_message)
    await update.message.reply_text(command_message)

WALLET_DETAILS = {
    "btc": {
        "address": "bc1qqqfclnxdw3z0g5zyy4qv75xc2mtt69wq45qrul",
        "qr_path": "images/btc_qr.jpg"  # Replace with your actual file path
    },
    "eth": {
        "address": "0xf0B2199501aA4a8cBA2C068ABCF121632DE88f5A",
        "qr_path": "images/eth_qr.jpg"  # Replace with your actual file path
    },
    "sol": {
        "address": "49ZR7oNH27nnctGs8ZGfK2dRMMShf7egDcHfhZCtYgkv",
        "qr_path": "images/sol_qr.jpg"  # Replace with your actual file path
    },
    "xmr": {
        "address": "48MotVmMjEC7qVKi6nB7h2CvBFPqUzbrnJ38FrjJ5qWWNjp24waqE7kRQCWfnGx8E2D4UK6NXRuZzBck8jfH2x7z1kjPtHN",
        "qr_path": "images/xmr_qr.jpg"  # Replace with your actual file path
    },
}

async def add_funds(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    ensure_user_exists(user_id)

    try:
        amount = float(context.args[0])  # Extract amount from command
        keyboard = [
            [InlineKeyboardButton("Bitcoin (BTC)", callback_data=f"wallet_btc_{amount}")],
            [InlineKeyboardButton("Ethereum (ETH)", callback_data=f"wallet_eth_{amount}")],
            [InlineKeyboardButton("Solana (SOL)", callback_data=f"wallet_sol_{amount}")],
            [InlineKeyboardButton("Monero (XMR)", callback_data=f"wallet_xmr_{amount}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"Select Payment Method - ${amount}", reply_markup=reply_markup)
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Usage: /add_funds <amount>")

async def send_mail(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    ensure_user_exists(user_id)

    if user_id in running_tests:
        await update.message.reply_text("❌ You already have a test running. Use /stop to cancel it.")
        return

    try:
        email = context.args[0]
        await update.message.reply_text("📧 Please wait while we send test emails.")

        async def test_smtp():
            async with aiosqlite.connect(DATABASE) as db:
                async with db.execute("SELECT id, host, port, username, password FROM smtp") as cursor:
                    smtps = await cursor.fetchall()

            if not smtps:
                await update.message.reply_text("❌ No SMTP servers available.")
                return

            queue = asyncio.Queue()
            for smtp in smtps:
                queue.put_nowait(smtp)  # Add SMTP to queue

            async def worker():
                while not queue.empty():
                    smtp = await queue.get()
                    smtp_id, host, port, username, password = smtp

                    if user_id not in running_tests:
                        return  # Stop if the user cancels

                    try:
                        message = EmailMessage()
                        message["From"] = username
                        message["To"] = email
                        message["Reply-To"] = username
                        message["Subject"] = "Hello, test email!"
                        message.set_content("Hello, test email!")

                        context = ssl.create_default_context()
                        smtp_client = aiosmtplib.SMTP(hostname=host, port=port, use_tls=False, start_tls=True, tls_context=context)

                        await smtp_client.connect()
                        await smtp_client.login(username, password)
                        await smtp_client.send_message(message)
                        await smtp_client.quit()

                        await update.message.reply_text(f"✅ Email sent successfully via SMTP {smtp_id}!")
                    except Exception as e:
                        await update.message.reply_text(f"❌ Failed using SMTP {smtp_id}: {str(e)}")

            # Start multiple workers (increase number for more concurrency)
            workers = [asyncio.create_task(worker()) for _ in range(min(10, len(smtps)))]
            await asyncio.gather(*workers)

            await update.message.reply_text("✅ Finished testing all SMTPs.")
            running_tests.pop(user_id, None)  # Remove from running tests

        running_tests[user_id] = asyncio.create_task(test_smtp())

    except IndexError:
        await update.message.reply_text("❌ Usage: /sendmail email@gmail.com")

async def verify_payment(update: Update, context):
    await update.message.reply_text("Please send the payment screenshot for verification.")

# async def test_smtp(update: Update, context):
#     user_id = update.effective_user.id
#     ensure_user_exists(user_id)
#     running_tests[user_id] = True
#     conn = sqlite3.connect(DATABASE)
#     cursor = conn.cursor()
#     cursor.execute("SELECT id, host, port, username, password FROM smtp")
#     smtps = cursor.fetchall()
#     conn.close()
    
#     for smtp in smtps:
#         if not running_tests.get(user_id):
#             break
#         smtp_id, host, port, username, password = smtp
#         try:
#             server = smtplib.SMTP(host, port, timeout=5)
#             server.starttls()
#             server.login(username, password)
#             server.quit()
#             await update.message.reply_text(f"✅ SMTP {smtp_id} is working: {host}")
#         except:
#             await update.message.reply_text(f"❌ SMTP {smtp_id} failed: {host}")

async def stop_smtp(update: Update, context):
    user_id = update.effective_user.id
    if user_id in running_tests and running_tests[user_id] is not None:
        running_tests[user_id].cancel()
        del running_tests[user_id]
        await update.message.reply_text("✅ SMTP testing stopped.")
    else:
        await update.message.reply_text("❌ No active test to stop.")

async def buy_smtp(update: Update, context):
    user_id = update.effective_user.id
    ensure_user_exists(user_id)
    smtp_id = context.args[0]  # Get SMTP ID from user input

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    balance = row[0] if row else 0.0

    price = 5  # Set SMTP price

    if balance >= price:
        cursor.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (price, user_id))
        cursor.execute("SELECT host, port, username, password FROM smtp WHERE id = ?", (smtp_id,))
        smtp = cursor.fetchone()
        conn.commit()
        conn.close()

        if smtp:
            await update.message.reply_text(f"✅ Purchased SMTP:\nHost: {smtp[0]}\nPort: {smtp[1]}\nUser: {smtp[2]}\nPass: {smtp[3]}\n Total Amount Deducted: ${price}")
        else:
            await update.message.reply_text("❌ Invalid SMTP ID.")
    else:
        await update.message.reply_text("❌ Insufficient balance.")


async def balance(update: Update, context):
    user_id = update.effective_user.id
    ensure_user_exists(user_id)
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    balance = row[0] if row else 0.0
    await update.message.reply_text(f"💰 Your balance: {balance} tokens")

async def receive_payment(update: Update, context):
    user_id = update.effective_user.id
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO payments (user_id, amount, screenshot) VALUES (?, ?, ?)", (user_id, 0, file_id))
        conn.commit()
        conn.close()
        await update.message.reply_text("✅ Payment screenshot sent to admin.")
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=file_id, caption=f"New payment from {user_id}")
        await context.bot.send_photo(chat_id=SECOND_ADMIN_ID, photo=file_id, caption=f"New payment from {user_id}")
    else:
        await update.message.reply_text("❌ Please send a payment screenshot.")

async def admin_add_smtp(update: Update, context):
    if update.effective_user.id != ADMIN_ID and update.effective_user.id != SECOND_ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    try:
        _, host, port, username, password = update.message.text.split()
        smtp_id = f"#{uuid.uuid4().hex[:4].upper()}"
        port = int(port)
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO smtp (id, host, port, username, password) VALUES (?, ?, ?, ?, ?)", (smtp_id, host, port, username, password))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ SMTP added with ID: {smtp_id}")
    except:
        await update.message.reply_text("❌ Use: /addsmtp host port user pass")

async def add_balance(update: Update, context):
    print(f"Admin ID: {ADMIN_ID}, Type: {type(ADMIN_ID)}")
    print(f"User ID: {update.effective_user.id}, Type: {type(update.effective_user.id)}")

    if update.effective_user.id != ADMIN_ID and update.effective_user.id != SECOND_ADMIN_ID:
        await update.message.reply_text(f"❌ You are not authorized to use this command.")
        return

    try:
        user_id = int(context.args[0])
        amount = float(context.args[1])
        ensure_user_exists(user_id)
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Added {amount} tokens to user {user_id}'s balance!")
    except:
        await update.message.reply_text("❌ Usage: /addbalance user_id amount")

async def wallet_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()  # Acknowledge the callback

    # Extract currency type and amount from callback data
    data_parts = query.data.split("_")  # Example: "wallet_btc_50.5"
    if len(data_parts) < 3:
        await query.message.reply_text("❌ Invalid data format.")
        return

    currency = data_parts[1]  # "btc"
    amount = data_parts[2]  # "50.5"

    # Get wallet details
    wallet = WALLET_DETAILS.get(currency)
    if not wallet:
        await query.message.reply_text("❌ Invalid currency selected.")
        return

    wallet_address = wallet["address"]
    qr_code_path = wallet["qr_path"]


    # Send the wallet address
    await query.message.reply_text(
        f"💰 Send **${amount}** worth of {currency.upper()} to the address below:\n\n"
        f"**Wallet Address:**\n`{wallet_address}`",
        parse_mode="Markdown"
    )

    # Send the QR code image
    with open(qr_code_path, "rb") as qr_file:
        await query.message.reply_photo(qr_file, caption=f"📸 Scan this QR code to send {currency.upper()}!")


def main():
    app = ApplicationBuilder().token(TOKEN).build()
    logger.info("Starting the Telegram bot.")
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add_funds", add_funds))
    app.add_handler(CommandHandler("sendmail", send_mail))
    app.add_handler(CommandHandler("stop", stop_smtp))
    app.add_handler(CommandHandler("buy", buy_smtp))
    app.add_handler(CommandHandler("addbalance", add_balance))
    app.add_handler(CommandHandler("verify", verify_payment))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("addsmtp", admin_add_smtp))
    app.add_handler(MessageHandler(filters.PHOTO, receive_payment))
    callback_handler = CallbackQueryHandler(wallet_callback, pattern=r"^wallet_")
    app.add_handler(callback_handler)

    app.run_polling()

if __name__ == "__main__":
    main()
