"""
  telegram_bot.py -- RICHARD como bot de Telegram.

  Interfaz conversacional de RICHARD para Telegram.
  Cada usuario tiene su propio estado de conversación (historial de mensajes).

  Arrancar:
      uv run telegram_bot.py

  Requisitos:
      - TELEGRAM_BOT_TOKEN en .env
      - python-telegram-bot>=20.3 en dependencies
  """

import logging
import sys
import os
import asyncio

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    )
from langchain_core.messages import HumanMessage

from richard.agent import build_graph, get_langfuse_handler


load_dotenv()

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[RICHARD-TG] %(levelname)s: %(message)s",
)

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN no configurado en .env")
    sys.exit(1)

MAX_MESSAGE_LENGTH = 4096


# estado por usuario

user_states: dict[int, dict] = {}

def get_user_state(user_id: int) -> dict:
    if user_id not in user_states:
        user_states[user_id] = {"messages": [], "ultima_imagen": None}
    return user_states[user_id]

def reset_user_state(user_id: int) -> None:
    user_states[user_id] = {"messages": [], "ultima_imagen": None}

def extract_response_text(last_message) -> str:
    """Extrae texto de respuesta del ultimo mensaje LangChain."""
    if hasattr(last_message, "text"):
        return last_message.text
    elif hasattr(last_message, "content"):
        if isinstance(last_message.content, list):
            parts = []
            for block in last_message.content:
                if isinstance(block, dict) and "text" in block:
                    parts.append(block["text"])
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(parts)
        else:
            return last_message.content
    return str(last_message)

def split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Divide mensajes largos para respetar el límite de Telegram"""
    if len(text) <= max_length:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        split_pos = text.rfind("\n", 0, max_length)
        if split_pos == -1 or split_pos < max_length // 2:
            split_pos = max_length
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")
    return chunks


# HANDLERS

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: 
    user_id = update.effective_user.id
    reset_user_state(user_id)
    await update.message.reply_text(
        "Hola buenas! Acá RICHARD, tu asistente de finanzas personales.\n\n"
        "Decime, con qué te ayudo?? Puedo:\n"
        "  - Registrar tus gastos\n"
        "  - Consultar cuánto gastaste\n"
        "  - Generar gráficos de tus gastos\n\n"
        "/reset para reiniciar la conversación.\n"
        "/help para ver los comandos disponibles."


    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: 
    await update.message.reply_text(
        "Comandos disponibles:\n\n"
        "/start - Iniciar y reiniciar el bot\n"
        "/reset - Limpiar historial de conversacion\n"
        "/help  - Mostrar esta ayuda\n\n"
        "O enviame cualquier mensaje relacionado con tus finanzas."
    )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: 
    user_id = update.effective_user.id
    reset_user_state(user_id)
    await update.message.reply_text("Conversacion reiniciada. En qué te ayudo?")


# handler principal de mensajes
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Procesa mensajes de texto -- loop principal de conversacion."""
    user_id = update.effective_user.id
    user_input = update.message.text.strip()

    if not user_input:
        return

    state = get_user_state(user_id)
    state["messages"].append(HumanMessage(content=user_input))

    await update.message.chat.send_action(ChatAction.TYPING)

    graph = context.bot_data["graph"]
    config = {}
    langfuse_handler = get_langfuse_handler()
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: graph.invoke(state, config=config if config else None),
        )

        user_states[user_id] = result

        last_message = result["messages"][-1]
        response_text = extract_response_text(last_message)

        if not response_text or not response_text.strip():
            await update.message.reply_text(
                "No pude generar una respuesta. Intenta reformular tu consulta."
            )
            return

        for chunk in split_message(response_text):
            await update.message.reply_text(chunk)

        if result.get("ultima_imagen"):
            image_path = result["ultima_imagen"]
            try:
                with open(image_path, "rb") as photo:
                    await update.message.reply_photo(photo=photo)
            except FileNotFoundError:
                await update.message.reply_text(
                    f"El grafico se genero pero no se pudo enviar: {image_path}"
                )
            user_states[user_id]["ultima_imagen"] = None

    except Exception as e:
        logger.error("Error processing message for user %s: %s", user_id, e)
        await update.message.reply_text(f"Error: {e}")
        if state["messages"] and isinstance(state["messages"][-1], HumanMessage):
            state["messages"].pop()


# entrypoint

def main() -> None:
    logger.info("Inicializando grafo LangGraph de RICHARD... ")
    graph = build_graph()
    logger.info("Grafo LangGraph listo.")

    logger.info("Iniciando bot de Telegram...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.bot_data["graph"] = graph

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot de Telegram iniciado. Ctrl+C para detener.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()   