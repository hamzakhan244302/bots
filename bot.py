import logging
import pymysql
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
import random, string, datetime, os

# ── CONFIG ──
BOT_TOKEN   = os.getenv("BOT_TOKEN", "8667412702:AAFj3kzCwHbn4gorKtQEW5LtGC79KwbctsM")
DB_HOST     = os.getenv("DB_HOST", "live.hostserverdns.in")
DB_NAME     = os.getenv("DB_NAME", "battleg1_main")
DB_USER     = os.getenv("DB_USER", "battleg1_main")
DB_PASS     = os.getenv("DB_PASS", "battleg1_main")
PANEL_URL   = os.getenv("PANEL_URL", "https://kartooselite.shop")

# Conversation states
SET_LEVEL, SET_BALANCE, GEN_DURATION, GEN_DEVICES = range(4)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── DATABASE ──
def get_db():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASS,
        database=DB_NAME, charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=10,
        write_timeout=10
    )

def get_user(chat_id):
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT * FROM bot_users WHERE chat_id=%s", (chat_id,))
            return cur.fetchone()
    except: return None
    finally:
        try: db.close()
        except: pass

def get_panel_user(username):
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE username=%s", (username,))
            return cur.fetchone()
    except: return None
    finally:
        try: db.close()
        except: pass

def ensure_bot_table():
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS `bot_users` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `chat_id` BIGINT NOT NULL UNIQUE,
                    `username` VARCHAR(100),
                    `level` INT DEFAULT 0,
                    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        db.commit()
    except Exception as e:
        logger.error(f"Table error: {e}")
    finally:
        try: db.close()
        except: pass

def register_user(chat_id, username, level):
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("""
                INSERT INTO bot_users (chat_id, username, level)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE username=%s, level=%s
            """, (chat_id, username, level, username, level))
        db.commit()
        return True
    except: return False
    finally:
        try: db.close()
        except: pass

def get_level_name(level):
    return {1: "Owner", 2: "Admin", 3: "Reseller", 0: "No Access"}.get(level, "No Access")

def gen_key(length=16):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ── MENUS ──
def main_menu(level):
    kb = []
    if level >= 1:
        kb.append([
            InlineKeyboardButton("📊 Panel Status", callback_data="status"),
            InlineKeyboardButton("🔑 My Keys", callback_data="keys")
        ])
        kb.append([
            InlineKeyboardButton("👥 Users Info", callback_data="users"),
            InlineKeyboardButton("💰 Balance", callback_data="balance_menu")
        ])
        kb.append([
            InlineKeyboardButton("⚡ Generate Key", callback_data="generate")
        ])
    if level == 1:
        kb.append([
            InlineKeyboardButton("🛡 Set User Level", callback_data="set_level"),
            InlineKeyboardButton("💵 Add Balance", callback_data="add_balance")
        ])
        kb.append([
            InlineKeyboardButton("🚫 Block User", callback_data="block_user"),
            InlineKeyboardButton("✅ Unblock User", callback_data="unblock_user")
        ])
    return InlineKeyboardMarkup(kb)

# ── HANDLERS ──
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if user and user['level'] > 0:
        name = get_level_name(user['level'])
        await update.message.reply_text(
            f" Welcome back *{user['username']}*!\n"
            f"Level: {name}\n\n"
            f"Choose an option:",
            parse_mode='Markdown',
            reply_markup=main_menu(user['level'])
        )
    else:
        await update.message.reply_text(
            f"*Kartoos Elite Bot*\n\n"
            f"*Your Chat ID:* `{chat_id}`\n"
            "Send this ID to the Owner to get access.",
            parse_mode='Markdown'
        )

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user or user['level'] == 0:
        await update.callback_query.answer("❌ No access!", show_alert=True)
        return
    try:
        r = requests.get(PANEL_URL, timeout=5)
        status_txt = " Online" if r.status_code == 200 else " Error"
    except:
        status_txt = " Offline"
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) as c FROM keys_code")
            total_keys = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM keys_code WHERE status=1 AND (expired_date IS NULL OR expired_date>NOW())")
            active_keys = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM users")
            total_users = cur.fetchone()['c']
    except:
        total_keys = active_keys = total_users = "N/A"
    finally:
        try: db.close()
        except: pass

    text = (
        f" *Panel Status*\n\n"
        f" Panel: {status_txt}\n"
        f" Total Keys: `{total_keys}`\n"
        f"✅ Active Keys: `{active_keys}`\n"
        f" Total Users: `{total_users}`\n"
        f" Domain: `{PANEL_URL}`"
    )
    await update.callback_query.edit_message_text(text, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back")]]))

async def keys_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user or user['level'] == 0:
        await update.callback_query.answer("❌ No access!", show_alert=True)
        return
    try:
        db = get_db()
        with db.cursor() as cur:
            if user['level'] == 1:
                cur.execute("SELECT COUNT(*) as c FROM keys_code")
                total = cur.fetchone()['c']
                cur.execute("SELECT COUNT(*) as c FROM keys_code WHERE status=1 AND (expired_date IS NULL OR expired_date>NOW())")
                active = cur.fetchone()['c']
                cur.execute("SELECT COUNT(*) as c FROM keys_code WHERE status=0")
                blocked = cur.fetchone()['c']
                cur.execute("SELECT COUNT(*) as c FROM keys_code WHERE expired_date IS NOT NULL AND expired_date<NOW()")
                expired = cur.fetchone()['c']
            else:
                cur.execute("SELECT COUNT(*) as c FROM keys_code WHERE registrator=%s", (user['username'],))
                total = cur.fetchone()['c']
                cur.execute("SELECT COUNT(*) as c FROM keys_code WHERE registrator=%s AND status=1 AND (expired_date IS NULL OR expired_date>NOW())", (user['username'],))
                active = cur.fetchone()['c']
                cur.execute("SELECT COUNT(*) as c FROM keys_code WHERE registrator=%s AND status=0", (user['username'],))
                blocked = cur.fetchone()['c']
                cur.execute("SELECT COUNT(*) as c FROM keys_code WHERE registrator=%s AND expired_date IS NOT NULL AND expired_date<NOW()", (user['username'],))
                expired = cur.fetchone()['c']
    except:
        total = active = blocked = expired = "N/A"
    finally:
        try: db.close()
        except: pass

    text = (
        f" *Keys Info*\n\n"
        f" Total: `{total}`\n"
        f"✅ Active: `{active}`\n"
        f" Blocked: `{blocked}`\n"
        f"⏰ Expired: `{expired}`"
    )
    await update.callback_query.edit_message_text(text, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back")]]))

async def users_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user or user['level'] == 0:
        await update.callback_query.answer("❌ No access!", show_alert=True)
        return
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) as c FROM users WHERE level=1")
            owners = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM users WHERE level=2")
            admins = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM users WHERE level=3")
            resellers = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM users WHERE status=0")
            banned = cur.fetchone()['c']
    except:
        owners = admins = resellers = banned = "N/A"
    finally:
        try: db.close()
        except: pass

    text = (
        f" *Users Info*\n\n"
        f" Owners: `{owners}`\n"
        f"⚡ Admins: `{admins}`\n"
        f" Resellers: `{resellers}`\n"
        f" Banned: `{banned}`"
    )
    await update.callback_query.edit_message_text(text, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back")]]))

async def balance_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user or user['level'] == 0:
        await update.callback_query.answer("❌ No access!", show_alert=True)
        return
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT balance FROM users WHERE username=%s", (user['username'],))
            row = cur.fetchone()
            bal = row['balance'] if row else 0
            if user['level'] == 1:
                cur.execute("SELECT COALESCE(SUM(balance),0) as t FROM users")
                total = cur.fetchone()['t']
            else:
                total = None
    except:
        bal = total = "N/A"
    finally:
        try: db.close()
        except: pass

    text = f" *Balance Info*\n\n Your Balance: `₹{bal}`"
    if total is not None:
        text += f"\n Total Balance (All): `₹{total}`"

    await update.callback_query.edit_message_text(text, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back")]]))

async def generate_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user or user['level'] == 0:
        await update.callback_query.answer("❌ No access!", show_alert=True)
        return ConversationHandler.END

    kb = [
        [InlineKeyboardButton("1 Hour", callback_data="dur_1"),
         InlineKeyboardButton("6 Hours", callback_data="dur_6")],
        [InlineKeyboardButton("12 Hours", callback_data="dur_12"),
         InlineKeyboardButton("1 Day", callback_data="dur_24")],
        [InlineKeyboardButton("3 Days", callback_data="dur_72"),
         InlineKeyboardButton("7 Days", callback_data="dur_168")],
        [InlineKeyboardButton("15 Days", callback_data="dur_360"),
         InlineKeyboardButton("30 Days", callback_data="dur_720")],
        [InlineKeyboardButton("Cancel", callback_data="back")]
    ]
    await update.callback_query.edit_message_text(
        "⚡ *Generate Key*\n\nSelect duration:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return GEN_DURATION

async def generate_duration(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    dur = int(update.callback_query.data.split("_")[1])
    ctx.user_data['gen_duration'] = dur
    kb = [
        [InlineKeyboardButton("1 Device", callback_data="dev_1"),
         InlineKeyboardButton("2 Devices", callback_data="dev_2")],
        [InlineKeyboardButton("3 Devices", callback_data="dev_3"),
         InlineKeyboardButton("5 Devices", callback_data="dev_5")],
        [InlineKeyboardButton("Cancel", callback_data="back")]
    ]
    await update.callback_query.edit_message_text(
        " Select max devices:",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return GEN_DEVICES

async def generate_devices(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    devices = int(update.callback_query.data.split("_")[1])
    duration = ctx.user_data.get('gen_duration', 24)

    key = gen_key()
    expiry = datetime.datetime.now() + datetime.timedelta(hours=duration)
    expiry_str = expiry.strftime('%Y-%m-%d %H:%M:%S')

    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("""
                INSERT INTO keys_code (user_key, game, duration, max_devices, device_count, status, registrator, expired_date, created_at)
                VALUES (%s, 'PUBG', %s, %s, 0, 1, %s, %s, NOW())
            """, (key, duration, devices, user['username'], expiry_str))
        db.commit()

        dur_label = {1:"1 Hour",6:"6 Hours",12:"12 Hours",24:"1 Day",72:"3 Days",168:"7 Days",360:"15 Days",720:"30 Days"}.get(duration, f"{duration}h")
        text = (
            f"✅ *Key Generated!*\n\n"
            f" Key: `{key}`\n"
            f"⏱ Duration: `{dur_label}`\n"
            f" Max Devices: `{devices}`\n"
            f" Expires: `{expiry_str}`\n"
            f" By: `{user['username']}`"
        )
    except Exception as e:
        text = f"❌ Error generating key: {e}"
    finally:
        try: db.close()
        except: pass

    await update.callback_query.edit_message_text(text, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Menu", callback_data="back")]]))
    return ConversationHandler.END

async def set_level_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user or user['level'] != 1:
        await update.callback_query.answer("❌ Owner only!", show_alert=True)
        return ConversationHandler.END
    await update.callback_query.edit_message_text(
        " *Set User Level*\n\nSend: `username level chatid`\n\nExample:\n`HARSH 3 123456789`\n\nLevels: 1=Owner, 2=Admin, 3=Reseller",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back")]])
    )
    return SET_LEVEL

async def set_level_process(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user or user['level'] != 1:
        return ConversationHandler.END
    try:
        parts = update.message.text.strip().split()
        target_user = parts[0]
        level = int(parts[1])
        target_chat_id = int(parts[2])

        if level not in [1, 2, 3]:
            await update.message.reply_text("❌ Level must be 1, 2 or 3!")
            return ConversationHandler.END

        register_user(target_chat_id, target_user, level)
        level_name = get_level_name(level)

        await update.message.reply_text(
            f"✅ *Level Set!*\n\n"
            f" User: `{target_user}`\n"
            f" Level: {level_name}\n"
            f" Chat ID: `{target_chat_id}`",
            parse_mode='Markdown'
        )
        try:
            await ctx.bot.send_message(
                chat_id=target_chat_id,
                text=f"✅ *Access Granted!*\n\nYou have been assigned: {level_name}\n\nSend /start to begin.",
                parse_mode='Markdown'
            )
        except: pass
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}\n\nFormat: `username level chatid`", parse_mode='Markdown')

    return ConversationHandler.END

async def add_balance_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user or user['level'] != 1:
        await update.callback_query.answer("❌ Owner only!", show_alert=True)
        return ConversationHandler.END
    await update.callback_query.edit_message_text(
        " *Add Balance*\n\nSend: `username amount`\n\nExample:\n`HARSH 500`",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back")]])
    )
    return SET_BALANCE

async def add_balance_process(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user or user['level'] != 1:
        return ConversationHandler.END
    try:
        parts = update.message.text.strip().split()
        target_user = parts[0]
        amount = float(parts[1])

        db = get_db()
        with db.cursor() as cur:
            cur.execute("UPDATE users SET balance=balance+%s WHERE username=%s", (amount, target_user))
            if cur.rowcount == 0:
                await update.message.reply_text(f"❌ User `{target_user}` not found!", parse_mode='Markdown')
                return ConversationHandler.END
            cur.execute("SELECT balance FROM users WHERE username=%s", (target_user,))
            new_bal = cur.fetchone()['balance']
        db.commit()

        await update.message.reply_text(
            f"✅ *Balance Added!*\n\n"
            f" User: `{target_user}`\n"
            f"➕ Added: `₹{amount}`\n"
            f" New Balance: `₹{new_bal}`",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}", parse_mode='Markdown')
    finally:
        try: db.close()
        except: pass
    return ConversationHandler.END

async def block_user_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user or user['level'] != 1:
        await update.callback_query.answer("❌ Owner only!", show_alert=True)
        return ConversationHandler.END
    await update.callback_query.edit_message_text(
        " *Block User*\n\nSend username to block:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back")]])
    )
    ctx.user_data['action'] = 'block'
    return SET_LEVEL

async def unblock_user_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user or user['level'] != 1:
        await update.callback_query.answer("❌ Owner only!", show_alert=True)
        return ConversationHandler.END
    await update.callback_query.edit_message_text(
        "✅ *Unblock User*\n\nSend username to unblock:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back")]])
    )
    ctx.user_data['action'] = 'unblock'
    return SET_LEVEL

async def block_unblock_process(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user or user['level'] != 1:
        return ConversationHandler.END
    action = ctx.user_data.get('action', 'block')
    target = update.message.text.strip()
    new_status = 0 if action == 'block' else 1
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("UPDATE users SET status=%s WHERE username=%s", (new_status, target))
            if cur.rowcount == 0:
                await update.message.reply_text(f"❌ User `{target}` not found!", parse_mode='Markdown')
                return ConversationHandler.END
        db.commit()
        emoji = "" if action == 'block' else "✅"
        word = "Blocked" if action == 'block' else "Unblocked"
        await update.message.reply_text(f"{emoji} User `{target}` {word}!", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}", parse_mode='Markdown')
    finally:
        try: db.close()
        except: pass
    return ConversationHandler.END

async def back_to_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user or user['level'] == 0:
        await update.callback_query.edit_message_text(
            f"❌ No access!\nYour Chat ID: `{chat_id}`",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    name = get_level_name(user['level'])
    await update.callback_query.edit_message_text(
        f" *Kartoos Elite Bot*\n\n"
        f" User: `{user['username']}`\n"
        f" Level: {name}\n\n"
        f"Choose an option:",
        parse_mode='Markdown',
        reply_markup=main_menu(user['level'])
    )
    return ConversationHandler.END

async def my_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f" Your Chat ID: `{chat_id}`",
        parse_mode='Markdown'
    )

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if user and user['level'] > 0:
        await update.message.reply_text("✅ Cancelled.", reply_markup=main_menu(user['level']))
    return ConversationHandler.END

# ── MAIN ──
def main():
    ensure_bot_table()

    # Register owner automatically
    register_user(7182189844, "hamzakhan24", 1)

    app = Application.builder().token(BOT_TOKEN).build()

    # Generate key conversation
    gen_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(generate_start, pattern="^generate$")],
        states={
            GEN_DURATION: [CallbackQueryHandler(generate_duration, pattern="^dur_"),
                           CallbackQueryHandler(back_to_menu, pattern="^back$")],
            GEN_DEVICES:  [CallbackQueryHandler(generate_devices, pattern="^dev_"),
                           CallbackQueryHandler(back_to_menu, pattern="^back$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )

    # Set level conversation
    level_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_level_start, pattern="^set_level$"),
                      CallbackQueryHandler(block_user_start, pattern="^block_user$"),
                      CallbackQueryHandler(unblock_user_start, pattern="^unblock_user$")],
        states={
            SET_LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_level_process),
                        MessageHandler(filters.TEXT & ~filters.COMMAND, block_unblock_process)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(back_to_menu, pattern="^back$")],
        per_message=False
    )

    # Balance conversation
    bal_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_balance_start, pattern="^add_balance$")],
        states={
            SET_BALANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_balance_process)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(back_to_menu, pattern="^back$")],
        per_message=False
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(gen_conv)
    app.add_handler(level_conv)
    app.add_handler(bal_conv)
    app.add_handler(CallbackQueryHandler(status, pattern="^status$"))
    app.add_handler(CallbackQueryHandler(keys_info, pattern="^keys$"))
    app.add_handler(CallbackQueryHandler(users_info, pattern="^users$"))
    app.add_handler(CallbackQueryHandler(balance_menu, pattern="^balance_menu$"))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back$"))

    logger.info("Bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
