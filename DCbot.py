import discord
from discord import app_commands
import google.generativeai as genai
import os
import asyncio
import re
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ALLOWED_CHANNEL_IDS = [1373992192175247481, 1362259535380877436, 1127235433252786199, 1326922231682568368]

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "Bot is running!", 200

def run_flask():
    app.run(host="0.0.0.0", port=10000)

@client.event
async def on_ready():
    await tree.sync()
    print(f"Bot is ready. Logged in as {client.user}")

genai.configure(api_key=GEMINI_API_KEY)

user_settings = {}

LANGUAGE_CHOICES = [
    ("Auto Detect", "auto"),
    ("English", "English"),
    ("Japanese", "Japanese"),
    ("Chinese", "Chinese"),
    ("Korean", "Korean"),
    ("French", "French"),
    ("German", "German"),
    ("Spanish", "Spanish")
]

def split_text(text, limit=2000):
    chunks = []
    while len(text) > limit:
        split_at = text.rfind('\n', 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    chunks.append(text)
    return chunks

async def translate_with_gemini(text, source_lang, target_lang):
    if source_lang == "auto":
        prompt = f"""You are a professional translator.

Please translate the following text into {target_lang}.
If the translation requires context or has multiple possible meanings, list all plausible translations and include the relevant interpretation in square brackets.
Do not add unrelated commentary.

Text:
{text}
"""
    else:
        prompt = f"""You are a professional translator.

Please translate the following text from {source_lang} to {target_lang}.
If the translation requires context or has multiple possible meanings, list all plausible translations and include the relevant interpretation in square brackets.
Do not add unrelated commentary.

Text:
{text}
"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"翻訳に失敗しました: {e}"


@tree.command(name="translate", description="翻訳の元言語と翻訳先言語を設定します")
@app_commands.describe(source="元の言語", target="翻訳先の言語")
@app_commands.choices(
    source=[app_commands.Choice(name=label, value=value) for label, value in LANGUAGE_CHOICES],
    target=[app_commands.Choice(name=label, value=value) for label, value in LANGUAGE_CHOICES if value != "auto"]
)
async def set_language(interaction: discord.Interaction, source: app_commands.Choice[str], target: app_commands.Choice[str]):
    user_settings[interaction.user.id] = {"source": source.value, "target": target.value}
    await interaction.response.send_message(f"翻訳設定を更新しました：{source.name} → {target.name}", ephemeral=True)

@tree.command(name="stop", description="自分の翻訳設定を解除します")
async def stop_translation(interaction: discord.Interaction):
    if user_settings.pop(interaction.user.id, None) is not None:
        try:
            # 直近のBotのephemeralレスポンスを削除（ただし実際の実装では履歴を保持しないと厳しい）
            await interaction.response.send_message("翻訳を解除しました。", ephemeral=True)
        except Exception as e:
            print(f"削除失敗: {e}")
    else:
        await interaction.response.send_message("現在、翻訳設定はありません。", ephemeral=True)


@tree.command(name="switchlanguage", description="元の言語と翻訳先の言語を入れ替えます")
async def switch_language(interaction: discord.Interaction):
    settings = user_settings.get(interaction.user.id)
    if settings is None:
        await interaction.response.send_message("翻訳設定が見つかりません。まず /translate で言語を設定してください。", ephemeral=True)
        return

    source = settings["source"]
    target = settings["target"]
    settings["source"], settings["target"] = target, source
    user_settings[interaction.user.id] = settings

    await interaction.response.send_message(f"翻訳設定を入れ替えました：{source} → {target} → {target} → {source}", ephemeral=True)



@client.event
async def on_message(message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.Thread):
        parent_channel = message.channel.parent
        if parent_channel and parent_channel.id not in ALLOWED_CHANNEL_IDS:
            return
    elif message.channel.id not in ALLOWED_CHANNEL_IDS:
        return

    content = message.content.strip() or message.clean_content.strip()

    if not content:
        await message.channel.send("翻訳対象のテキストが空です。テキストを送ってください。")
        return

    settings = user_settings.get(message.author.id)
    if not settings:
        return

    translated = await translate_with_gemini(content, settings["source"], settings["target"])
    chunks = split_text(translated)
    for chunk in chunks:
        await message.channel.send(chunk)

if __name__ == '__main__':
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    client.run(DISCORD_TOKEN)
