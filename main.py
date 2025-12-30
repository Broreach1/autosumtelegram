#!/usr/bin/env python3
import os
import re
import sqlite3
import io
import pandas as pd
from datetime import datetime, time, timedelta

from telegram import Update, ReplyKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ==============================
# ---------- Configuration -----
# ==============================
DB_PATH = "totals.db"
OUTPUT_FILE = "totals_export.xlsx"

BOT_TOKEN = os.getenv("BOT_TOKEN", "8103291457:AAFhfsVKjY05_0-cLFYxTAB71C3i_nsATZg")
ADMINS = {2122623994}

# ==============================
# ---------- Database ----------
# ==============================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS totals (
        chat_id INTEGER,
        date TEXT,
        shift TEXT,
        currency TEXT,
        total REAL,
        invoices INTEGER,
        PRIMARY KEY (chat_id, date, shift, currency)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        datetime TEXT,
        business_date TEXT,
        shift TEXT,
        currency TEXT,
        amount REAL
    )
    """)

    conn.commit()
    conn.close()

# ==============================
# ---------- Shifts ------------
# ==============================
SHIFT1_START = time(6, 0)
SHIFT1_END   = time(14, 0)
SHIFT2_START = time(14, 1)
SHIFT2_END   = time(20, 0)
SHIFT3_START = time(20, 1)
SHIFT3_END   = time(6, 0)

def get_shift_and_business_date(now=None):
    now = now or datetime.now()
    t = now.time()
    today = now.date()

    if SHIFT1_START <= t <= SHIFT1_END:
        return "shift1", today.strftime("%Y-%m-%d")
    if SHIFT2_START <= t <= SHIFT2_END:
        return "shift2", today.strftime("%Y-%m-%d")
    if t >= SHIFT3_START:
        return "shift3", today.strftime("%Y-%m-%d")
    return "shift3", (today - timedelta(days=1)).strftime("%Y-%m-%d")

# ==============================
# ----- Totals Logic -----------
# ==============================
def update_total(chat_id, currency, amount):
    now = datetime.now()
    shift, biz_date = get_shift_and_business_date(now)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO history (chat_id, datetime, business_date, shift, currency, amount)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (chat_id, now.isoformat(sep=" "), biz_date, shift, currency, amount))

    cur.execute("""
        INSERT INTO totals VALUES (?, ?, ?, ?, ?, 1)
        ON CONFLICT(chat_id, date, shift, currency)
        DO UPDATE SET
            total = total + excluded.total,
            invoices = invoices + 1
    """, (chat_id, biz_date, shift, currency, amount))

    conn.commit()
    conn.close()

def get_totals(chat_id, date, shift=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if shift:
        cur.execute("""
            SELECT currency, total, invoices FROM totals
            WHERE chat_id=? AND date=? AND shift=?
        """, (chat_id, date, shift))
    else:
        cur.execute("""
            SELECT currency, SUM(total), SUM(invoices)
            FROM totals WHERE chat_id=? AND date=?
            GROUP BY currency
        """, (chat_id, date))

    rows = cur.fetchall()
    conn.close()

    result = {"USD": {"total": 0, "invoices": 0}, "KHR": {"total": 0, "invoices": 0}}
    for c, t, i in rows:
        result[c] = {"total": t or 0, "invoices": i or 0}
    return result

# ==============================
# --------- Helpers ------------
# ==============================
def keyboard():
    return ReplyKeyboardMarkup(
        [["📊 Total", "📊 Total All"], ["📤 Export"]],
        resize_keyboard=True
    )

def parse_amounts(text):
    text = text.replace(",", "")
    pattern = r"([$៛])\s*(\d+(\.\d+)?)|(\d+(\.\d+)?)\s*(USD|KHR)"
    found = re.findall(pattern, text, re.I)

    results = []
    for f in found:
        if f[0]:
            results.append((float(f[1]), "USD" if f[0] == "$" else "KHR"))
        else:
            results.append((float(f[3]), f[5].upper()))
    return results

# ==============================
# --------- Handlers -----------
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("សួស្តី! Bot Ready ✅", reply_markup=keyboard())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    shift, biz = get_shift_and_business_date()

    if text == "📊 Total":
        t = get_totals(chat_id, biz, shift)
        await update.message.reply_text(str(t), reply_markup=keyboard())
        return

    if text == "📊 Total All":
        t = get_totals(chat_id, biz)
        await update.message.reply_text(str(t), reply_markup=keyboard())
        return

    amounts = parse_amounts(text)
    if not amounts:
        return

    for amt, cur in amounts:
        update_total(chat_id, cur, amt)

    totals = get_totals(chat_id, biz, shift)
    await update.message.reply_text(
        f"USD: {totals['USD']['total']:.2f}$ | KHR: {totals['KHR']['total']:,.0f}៛",
        reply_markup=keyboard()
    )

# ==============================
# ------------ MAIN ------------
# ==============================
def main():
    if not BOT_TOKEN or "PUT_YOUR" in BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing")

    init_db()

    app: Application = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ Bot running on PTB 21.x / Python 3.13")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
