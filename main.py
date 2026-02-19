import os
import asyncio
import csv
import aiosqlite
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DB_FILE = "data.db"

# ---------------- DATABASE ---------------- #

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT,
            date TEXT,
            amount INTEGER,
            description TEXT
        )
        """)
        await db.commit()

# ---------------- ADD / SUBTRACT ---------------- #

@dp.message(F.text.startswith("+") | F.text.startswith("-"))
async def handle_transaction(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        parts = message.text.split(" ", 1)
        amount = int(parts[0])
        description = parts[1] if len(parts) > 1 else ""
    except:
        await message.reply("Use format: +200 bank OR -100 cash")
        return

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        INSERT INTO transactions (group_id, date, amount, description)
        VALUES (?, ?, ?, ?)
        """, (
            str(message.chat.id),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            amount,
            description
        ))
        await db.commit()

    await message.reply("✅ Transaction Recorded")

# ---------------- TOTAL ---------------- #

@dp.message(Command("tt"))
async def total_balance(message: Message):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT SUM(amount) FROM transactions WHERE group_id = ?",
            (str(message.chat.id),)
        )
        result = await cursor.fetchone()

    total = result[0] if result[0] else 0
    await message.reply(f"📊 Current Balance: ₹{total}")

# ---------------- TOTAL TRANSACTIONS ---------------- #

@dp.message(Command("trns"))
async def total_transactions(message: Message):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
        SELECT COUNT(*), SUM(ABS(amount))
        FROM transactions WHERE group_id = ?
        """, (str(message.chat.id),))
        result = await cursor.fetchone()

    count = result[0] if result[0] else 0
    turnover = result[1] if result[1] else 0

    await message.reply(
        f"📈 Total Transactions: {count}\n"
        f"💰 Total Turnover: ₹{turnover}"
    )

# ---------------- HISTORY ---------------- #

@dp.message(Command("his"))
async def history(message: Message):
    args = message.text.split()

    group_id = str(message.chat.id)

    if len(args) == 1:
        # Today
        target_date = datetime.now().strftime("%Y-%m-%d")
        query = "SELECT date, amount, description FROM transactions WHERE group_id=? AND date LIKE ?"
        params = (group_id, target_date + "%")

    else:
        arg = args[1]

        # Format dd/mm
        if "/" in arg:
            try:
                day, month = map(int, arg.split("/"))
                year = datetime.now().year
                target_date = datetime(year, month, day).strftime("%Y-%m-%d")
                query = "SELECT date, amount, description FROM transactions WHERE group_id=? AND date LIKE ?"
                params = (group_id, target_date + "%")
            except:
                await message.reply("Use format: /his dd/mm")
                return

        # Format 3d / 7d
        elif arg.endswith("d"):
            try:
                days = int(arg[:-1])
                start_date = datetime.now() - timedelta(days=days)
                query = "SELECT date, amount, description FROM transactions WHERE group_id=? AND date >= ?"
                params = (group_id, start_date.strftime("%Y-%m-%d"))
            except:
                await message.reply("Use format: /his 3d")
                return
        else:
            await message.reply("Invalid format.")
            return

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

    if not rows:
        await message.reply("No transactions found.")
        return

    text = "📜 Transaction History:\n\n"
    for row in rows:
        date, amount, description = row
        text += f"{date} | {amount} | {description}\n"

    await message.reply(text)

# ---------------- GUIDE ---------------- #

@dp.message(Command("guide"))
async def guide(message: Message):
    text = """
📘 Ledger Bot Guide

➕ Add: +200 bank
➖ Subtract: -100 cash

📊 /tt → Current balance
📈 /trns → Total transactions + turnover
📜 /his → Today history
📜 /his dd/mm → Specific date
📜 /his 3d → Last 3 days
📜 /his 7d → Last 7 days
📁 /export → Download CSV (Admin only)

Only admin can add transactions.
"""
    await message.reply(text)

# ---------------- EXPORT ---------------- #

@dp.message(Command("export"))
async def export_csv(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    file_name = "transactions.csv"

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
        SELECT date, amount, description
        FROM transactions WHERE group_id=?
        ORDER BY id ASC
        """, (str(message.chat.id),))
        rows = await cursor.fetchall()

    with open(file_name, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Date & Time", "+/- Amount", "Description"])
        writer.writerows(rows)

    await message.reply_document(FSInputFile(file_name))

# ---------------- START ---------------- #

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
