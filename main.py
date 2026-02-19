import os
import asyncio
import pandas as pd
import aiosqlite
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram import F
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
            user_id TEXT,
            date TEXT,
            amount INTEGER,
            description TEXT
        )
        """)
        await db.commit()

# ---------------- TRANSACTION HANDLER ---------------- #

@dp.message(F.text.startswith("+") | F.text.startswith("-"))
async def handle_transaction(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        parts = message.text.split(" ", 1)
        amount = int(parts[0])
        description = parts[1] if len(parts) > 1 else "No description"
    except:
        await message.reply("Format: +200 bank or -100 cash")
        return

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        INSERT INTO transactions (group_id, user_id, date, amount, description)
        VALUES (?, ?, ?, ?, ?)
        """, (
            str(message.chat.id),
            str(message.from_user.id),
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
        cursor = await db.execute("""
        SELECT SUM(amount) FROM transactions WHERE group_id = ?
        """, (str(message.chat.id),))
        result = await cursor.fetchone()

    total = result[0] if result[0] else 0
    await message.reply(f"📊 Total Balance: ₹{total}")

# ---------------- EXPORT ---------------- #

@dp.message(Command("export"))
async def export_csv(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
        SELECT date, user_id, amount, description
        FROM transactions WHERE group_id = ?
        """, (str(message.chat.id),))
        rows = await cursor.fetchall()

    df = pd.DataFrame(rows, columns=["Date", "User ID", "Amount", "Description"])
    file_name = "transactions.csv"
    df.to_csv(file_name, index=False)

    await message.reply_document(types.FSInputFile(file_name))

# ---------------- DAILY SUMMARY ---------------- #

async def daily_summary():
    async with aiosqlite.connect(DB_FILE) as db:
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = await db.execute("""
        SELECT SUM(amount) FROM transactions
        WHERE date LIKE ?
        """, (today + "%",))
        result = await cursor.fetchone()

    total_today = result[0] if result[0] else 0

    await bot.send_message(
        ADMIN_ID,
        f"📅 Daily Summary\nTotal Today: ₹{total_today}"
    )

scheduler = AsyncIOScheduler()
scheduler.add_job(daily_summary, "cron", hour=23, minute=59)

# ---------------- START ---------------- #

async def main():
    await init_db()
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
