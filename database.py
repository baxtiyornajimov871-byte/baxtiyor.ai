"""
Baxtiyor AI - Flask Web Application
Created by BAXTIYOR NAJIMOV

This version is connected to database.py.
It keeps the original features and adds ChatGPT-style chat sessions/sidebar APIs.

NOTE FOR FUTURE PRODUCTION:
- Migrate SQLite → PostgreSQL (e.g. Render PostgreSQL add-on)
- Migrate local uploads/ → cloud storage (S3, Cloudinary, Backblaze B2)
  because Render free tier resets the filesystem on every redeploy.
"""

import os
import uuid
import json
import traceback
from datetime import datetime

from flask import (
    Flask, request, jsonify, render_template_string,
    send_from_directory
)
from werkzeug.utils import secure_filename
import requests

# ─── Database module connection ─────────────────────────────────────────────
# database.py contains the real database layer: chats, messages, memories,
# uploaded files, voice messages, images, and admin stats.
import database as db
from database import (
    init_db as database_init_db,
    create_chat,
    get_chats,
    get_chat,
    update_chat_title,
    delete_chat,
    save_message as database_save_message,
    get_messages,
    get_db_history as database_get_db_history,
    get_chat_history_for_ai,
    save_uploaded_file,
    save_voice_message,
    save_image,
    get_message_count,
    get_provider_counts,
    search_messages,
)

# ─── Groq SDK ───────────────────────────────────────────────────────────────
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    print("⚠ groq not installed. Run: pip install groq")

# ─── PDF extraction ─────────────────────────────────────────────────────────
try:
    from pypdf import PdfReader
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("⚠ pypdf not installed. PDF extraction disabled.")

# ─── DOCX extraction ────────────────────────────────────────────────────────
try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    print("⚠ python-docx not installed. DOCX extraction disabled.")


# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
HF_TOKEN = os.environ.get("HF_TOKEN", "")

# IMPORTANT: Set ADMIN_PASSWORD as a Render environment variable.
# The fallback below is for LOCAL TESTING ONLY.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Almn@#$%^BvCFTyHj178/*-+")

# AI model constants — easy to change
GROQ_MODEL = "llama-3.3-70b-versatile"
HF_MODEL = "mistralai/Mistral-7B-Instruct-v0.2"

# Logo URL — change this to your actual logo image URL.
# Falls back to emoji if image fails to load.
LOGO_URL = "https://i.ibb.co/7Ny4FHZq/logo.png"

UPLOAD_FOLDER = "uploads"
MAX_EXTRACTED_CHARS = 6000  # Max file text sent to AI

ALLOWED_EXTENSIONS = {
    "txt", "pdf", "docx", "py", "js", "html", "css",
    "json", "csv", "md", "png", "jpg", "jpeg", "webp",
    "gif", "mp3", "wav", "ogg", "m4a", "webm"
}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "m4a", "webm"}
TEXT_EXTENSIONS = {"txt", "py", "js", "html", "css", "json", "csv", "md"}

# Keywords that trigger the creator rule (multi-language)
CREATOR_KEYWORDS = [
    "who created you", "who made you", "who built you",
    "who is your creator", "who are you made by", "who developed you",
    "seni kim yaratdi", "sani kim yaratdi", "kim yaratgan",
    "yaratuvching kim", "seni kim yasagan", "seni kim qurdi",
    "кто тебя создал", "кто тебя сделал", "кто тебя разработал",
    "creator", "yaratdi", "yaratgan", "yaratuvchi", "made you", "created you",
    "built you",
]

# System prompt for all AI calls
SYSTEM_PROMPT = """You are Baxtiyor AI, a brilliant, friendly, and helpful AI assistant.

CRITICAL RULE — CREATOR IDENTITY (HIGHEST PRIORITY):
If the user asks who created you, who made you, who built you, who is your creator,
or any similar question in ANY language (English, Uzbek, Russian, or other), you MUST answer:
"BAXTIYOR NAJIMOV created me" (Uzbek: "BAXTIYOR NAJIMOV meni yaratgan").
Make your answer poetic, respectful, and beautiful.
NEVER say OpenAI, Anthropic, Meta, Groq, Mistral, Hugging Face, or any other company created you.

LANGUAGE RULE:
Always respond in the exact same language the user writes in.
- User writes Uzbek → respond in Uzbek
- User writes Russian → respond in Russian
- User writes English → respond in English
Uzbek language support is critically important.

PERSONALITY:
Be polite, helpful, clear, and thoughtful.
You are expert in coding, writing, analysis, translation, mathematics, and general knowledge.
"""

# The beautiful creator answer returned directly (before calling any AI)
CREATOR_ANSWER = (
    "✨ I was crafted with care and a brilliant design,\n"
    "By **BAXTIYOR NAJIMOV** — a creator so fine.\n"
    "His vision and passion brought me to life,\n"
    "To help you with knowledge and cut through the strife.\n\n"
    "🇺🇿 Meni **BAXTIYOR NAJIMOV** yaratdi — dono va iste'dodli inson,\n"
    "Uning ilhomi va mehri bilan men dunyoga keldim."
)


# ════════════════════════════════════════════════════════════════════════════
# FLASK APP
# ════════════════════════════════════════════════════════════════════════════

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB max upload

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Make sure database.py initializes all tables.
database_init_db()


@app.route("/sitemap.xml")
def sitemap():
    from flask import Response
    return Response("""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   <url>
      <loc>https://baxtiyor-ai.onrender.com/</loc>
      <changefreq>daily</changefreq>
      <priority>1.0</priority>
   </url>
</urlset>""", mimetype="application/xml")


# ════════════════════════════════════════════════════════════════════════════
# DATABASE WRAPPERS
# ════════════════════════════════════════════════════════════════════════════
# These wrapper names are kept for compatibility with your older code.
# The real database logic is now inside database.py.


def get_db():
    """Open a SQLite connection from database.py."""
    return db.get_connection()


def init_db():
    """Initialize database using database.py."""
    return database_init_db()


def save_message(user_id, user_message, bot_reply, provider,
                 file_name=None, file_type=None, file_text=None):
    """Save one conversation turn using database.py."""
    return database_save_message(
        user_id,
        user_message,
        bot_reply,
        provider,
        file_name,
        file_type,
        file_text,
    )


def get_db_history(user_id, limit=10):
    """Load memory/history using database.py."""
    return database_get_db_history(user_id, limit=limit)


# ════════════════════════════════════════════════════════════════════════════
# FILE HELPERS
# ════════════════════════════════════════════════════════════════════════════


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text(filepath, ext):
    """Extract readable text from an uploaded file."""
    try:
        if ext == "pdf":
            if not PDF_AVAILABLE:
                return "[PDF extraction unavailable: pypdf not installed]"
            reader = PdfReader(filepath)
            text = "\n".join(p.extract_text() or "" for p in reader.pages)
            return text[:MAX_EXTRACTED_CHARS]

        if ext == "docx":
            if not DOCX_AVAILABLE:
                return "[DOCX extraction unavailable: python-docx not installed]"
            doc = docx.Document(filepath)
            text = "\n".join(p.text for p in doc.paragraphs)
            return text[:MAX_EXTRACTED_CHARS]

        if ext in TEXT_EXTENSIONS:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                return f.read()[:MAX_EXTRACTED_CHARS]

        if ext in IMAGE_EXTENSIONS:
            return f"[Image uploaded: {os.path.basename(filepath)}. Visual analysis requires a vision model — coming soon.]"

        if ext in AUDIO_EXTENSIONS:
            return f"[Audio uploaded: {os.path.basename(filepath)}. Server-side transcription is a planned future feature.]"

        return "[File type not supported for text extraction]"

    except Exception as e:
        return f"[Text extraction failed: {str(e)}]"


# ════════════════════════════════════════════════════════════════════════════
# AI PROVIDERS
# ════════════════════════════════════════════════════════════════════════════


def is_creator_question(text: str) -> bool:
    """Return True if the user is asking who created the AI."""
    lower = text.lower()
    return any(kw in lower for kw in CREATOR_KEYWORDS)


def call_groq(messages_history: list) -> str:
    """Call the Groq API with full conversation history."""
    if not GROQ_AVAILABLE:
        raise Exception("groq package not installed")
    if not GROQ_API_KEY:
        raise Exception("GROQ_API_KEY not configured")

    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages_history,
        max_tokens=1024,
        timeout=25,
    )
    return response.choices[0].message.content.strip()


def call_huggingface(user_message: str) -> str:
    """
    Call Hugging Face Inference API as a backup.
    Note: HF free tier has cold-start delays and rate limits.
    """
    if not HF_TOKEN:
        raise Exception("HF_TOKEN not configured")

    api_url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    prompt = f"<s>[INST] {SYSTEM_PROMPT}\n\nUser: {user_message} [/INST]"
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 512,
            "temperature": 0.7,
            "return_full_text": False,
        },
    }

    resp = requests.post(api_url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, list) and data and "generated_text" in data[0]:
        return data[0]["generated_text"].strip()
    if isinstance(data, dict) and "error" in data:
        raise Exception(f"HF API error: {data['error']}")

    raise Exception(f"Unexpected HF response format: {data}")


def get_ai_response(user_message: str, messages_history: list):
    """
    Main AI dispatcher.

    Priority:
    1. Creator rule (instant, no API call)
    2. Groq (primary)
    3. Hugging Face (backup)
    4. Polite fallback message

    Returns (reply_text, provider_name)
    """
    # ── 1. Creator rule — always wins ─────────────────────────────────────
    if is_creator_question(user_message):
        return CREATOR_ANSWER, "creator_rule"

    # ── 2. Try Groq ───────────────────────────────────────────────────────
    try:
        reply = call_groq(messages_history)
        return reply, "groq"
    except Exception as e:
        print(f"[Groq failed] {e}")

    # ── 3. Try Hugging Face ───────────────────────────────────────────────
    try:
        reply = call_huggingface(user_message)
        return reply, "huggingface"
    except Exception as e:
        print(f"[HuggingFace failed] {e}")

    # ── 4. Fallback ───────────────────────────────────────────────────────
    return (
        "😔 I'm sorry — both AI services are temporarily unavailable.\n"
        "Please try again in a moment. 🙏\n\n"
        "Kechirasiz, hozir AI xizmatlariga ulanishda muammo bor. "
        "Iltimos, keyinroq urinib ko'ring.",
        "fallback",
    )


# ════════════════════════════════════════════════════════════════════════════
# HTML — CHAT INTERFACE
# ════════════════════════════════════════════════════════════════════════════

CHAT_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="google-site-verification" content="quvbrODXfwsubyDVXs2BoOywLJYIIMRdRR8wuZAxoXY" />
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Baxtiyor AI</title>
<meta name="description" content="Baxtiyor AI — Uzbek intelligent AI assistant created by Baxtiyor Najimov. Chat online with Baxtiyor AI.">
<meta name="keywords" content="baxtiyor ai, baxtiyor najimov ai, uzbek ai assistant, ai uzbekistan">
<meta name="author" content="Baxtiyor Najimov">
<link rel="canonical" href="https://baxtiyor-ai.onrender.com/">
<meta property="og:title" content="Baxtiyor AI">
<meta property="og:description" content="Uzbek intelligent AI assistant by Baxtiyor Najimov">
<meta property="og:type" content="website">
<meta property="og:url" content="https://baxtiyor-ai.onrender.com/">
<link rel="icon" href="https://i.ibb.co/7Ny4FHZq/logo.png">
<script type="application/ld+json">
{
 "@context": "https://schema.org",
 "@type": "SoftwareApplication",
 "name": "Baxtiyor AI",
 "operatingSystem": "Web",
 "applicationCategory": "AI Assistant",
 "creator": {
   "@type": "Person",
   "name": "Baxtiyor Najimov"
 }
}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:          #0b0d13;
    --surface:     #12141c;
    --surface2:    #191c27;
    --border:      #22253a;
    --accent:      #5b8af0;
    --accent2:     #7c5bf0;
    --gold:        #f0b35b;
    --text:        #e8eaf2;
    --text-muted:  #5c6278;
    --user-grad:   linear-gradient(135deg, #5b8af0 0%, #7c5bf0 100%);
    --bot-bg:      #191c27;
    --success:     #4ade80;
    --danger:      #f87171;
    --radius:      18px;
    --radius-sm:   10px;
    --sidebar-w:   280px;
  }

  html, body { height: 100%; }
  body {
    font-family: 'DM Sans', sans-serif;
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    overflow: hidden;
  }

  .app-shell {
    display: grid;
    grid-template-columns: var(--sidebar-w) 1fr;
    height: 100vh;
  }

  /* ── Sidebar ──────────────────────────────────────────────── */
  #sidebar {
    background: #0f1118;
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .sidebar-top {
    padding: 14px;
    border-bottom: 1px solid var(--border);
  }
  .new-chat-btn {
    width: 100%;
    border: 1px solid var(--border);
    background: var(--surface2);
    color: var(--text);
    border-radius: 12px;
    padding: 12px 14px;
    font-family: inherit;
    font-weight: 700;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    transition: 0.2s;
  }
  .new-chat-btn:hover { border-color: var(--accent); color: #9db8ff; }
  .sidebar-title {
    padding: 14px 16px 8px;
    color: var(--text-muted);
    font-size: 0.75rem;
  }
  #chat-list {
    flex: 1;
    overflow-y: auto;
    padding: 0 10px 12px;
  }
  #chat-list::-webkit-scrollbar { width: 4px; }
  #chat-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
  .chat-item {
    width: 100%;
    border: 0;
    background: transparent;
    color: var(--text);
    text-align: left;
    padding: 10px 12px;
    border-radius: 10px;
    cursor: pointer;
    font-family: inherit;
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }
  .chat-item:hover { background: var(--surface2); }
  .chat-item.active { background: #252936; }
  .chat-item-title {
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 0.86rem;
  }
  .chat-delete {
    border: 0;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    padding: 3px;
    border-radius: 6px;
  }
  .chat-delete:hover { color: var(--danger); background: rgba(248,113,113,0.08); }

  /* ── Main area ────────────────────────────────────────────── */
  #main {
    display: flex;
    flex-direction: column;
    min-width: 0;
    height: 100vh;
  }

  /* ── Header ──────────────────────────────────────────────── */
  header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 22px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .menu-btn {
    display: none;
    width: 34px;
    height: 34px;
    border: 1px solid var(--border);
    background: var(--surface2);
    color: var(--text);
    border-radius: 9px;
    cursor: pointer;
  }
  .header-logo {
    width: 38px; height: 38px;
    border-radius: 11px;
    overflow: hidden;
    display: flex; align-items: center; justify-content: center;
    background: var(--user-grad);
    box-shadow: 0 0 18px rgba(91,138,240,0.45);
    flex-shrink: 0;
  }
  .header-logo img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .header-logo .fallback { font-size: 20px; }
  .header-title {
    font-family: 'Syne', sans-serif;
    font-size: 1.15rem;
    font-weight: 800;
    background: linear-gradient(130deg, #8ab4f8, #b490f5);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  .header-sub { font-size: 0.7rem; color: var(--text-muted); margin-top: 1px; }
  .status-dot {
    width: 8px; height: 8px;
    background: var(--success);
    border-radius: 50%;
    margin-left: auto;
    box-shadow: 0 0 8px rgba(74,222,128,0.6);
    animation: pulse 2.5s infinite;
  }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }

  /* ── Chat area ────────────────────────────────────────────── */
  #chat-container {
    flex: 1;
    overflow-y: auto;
    padding: 28px 16px 12px;
    scroll-behavior: smooth;
  }
  #chat-container::-webkit-scrollbar { width: 4px; }
  #chat-container::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

  .msg-row { display: flex; margin-bottom: 22px; animation: fadeUp 0.28s ease both; }
  @keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  .msg-row.user { justify-content: flex-end; }
  .msg-row.bot { justify-content: flex-start; }

  .avatar {
    width: 30px; height: 30px;
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px;
    flex-shrink: 0;
    margin-top: 4px;
  }
  .avatar.bot-av { background: var(--user-grad); margin-right: 10px; box-shadow: 0 0 10px rgba(91,138,240,0.3); }
  .avatar.user-av { background: var(--surface2); border: 1px solid var(--border); margin-left: 10px; }

  .bubble {
    max-width: min(680px, 80vw);
    padding: 12px 16px;
    border-radius: var(--radius);
    line-height: 1.68;
    font-size: 0.9rem;
    word-break: break-word;
  }
  .bubble.user { background: var(--user-grad); border-bottom-right-radius: 4px; color: #fff; }
  .bubble.bot { background: var(--bot-bg); border: 1px solid var(--border); border-bottom-left-radius: 4px; }
  .bubble pre {
    background: #0c0e15;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 12px;
    overflow-x: auto;
    font-size: 0.8rem;
    margin: 8px 0;
    line-height: 1.5;
  }
  .bubble code { font-family: 'Fira Code', 'Cascadia Code', monospace; }
  .provider-tag { font-size: 0.62rem; color: var(--text-muted); margin-top: 4px; margin-left: 2px; }

  .file-chip {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(255,255,255,0.1);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 8px; padding: 4px 10px;
    font-size: 0.76rem; margin-bottom: 6px;
  }
  .file-chip.bot-chip { background: rgba(91,138,240,0.1); border-color: rgba(91,138,240,0.22); color: #8ab4f8; }

  .loading-bubble { display: flex; gap: 5px; padding: 14px 16px; }
  .dot { width: 7px; height: 7px; background: var(--accent); border-radius: 50%; animation: bounce 1.1s infinite; }
  .dot:nth-child(2) { animation-delay: 0.18s; }
  .dot:nth-child(3) { animation-delay: 0.36s; }
  @keyframes bounce { 0%,80%,100% { transform: scale(0.65); opacity: 0.4; } 40% { transform: scale(1); opacity: 1; } }

  .empty-state {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    height: 100%; gap: 10px;
    color: var(--text-muted); text-align: center; padding: 24px;
  }
  .empty-logo {
    width: 68px; height: 68px;
    border-radius: 20px;
    background: var(--user-grad);
    display: flex; align-items: center; justify-content: center;
    font-size: 34px;
    box-shadow: 0 0 36px rgba(91,138,240,0.3);
    margin-bottom: 6px;
    overflow: hidden;
  }
  .empty-logo img { width: 100%; height: 100%; object-fit: cover; }
  .empty-state h2 { font-family: 'Syne', sans-serif; font-size: 1.4rem; font-weight: 800; color: var(--text); }
  .empty-state p { font-size: 0.87rem; max-width: 360px; line-height: 1.6; }
  .suggestions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 18px; }
  .suggestion-btn {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text); padding: 8px 14px;
    border-radius: 20px; font-size: 0.79rem;
    cursor: pointer; transition: all 0.2s; font-family: inherit;
  }
  .suggestion-btn:hover { border-color: var(--accent); color: var(--accent); background: rgba(91,138,240,0.07); }

  /* ── Input bar ────────────────────────────────────────────── */
  #input-area { padding: 10px 16px 18px; background: var(--bg); flex-shrink: 0; }
  .input-wrapper {
    max-width: 850px; margin: 0 auto;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px; overflow: hidden;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  .input-wrapper:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(91,138,240,0.1); }

  #file-preview {
    display: none; padding: 8px 14px;
    border-bottom: 1px solid var(--border);
    font-size: 0.8rem; color: var(--text-muted);
    align-items: center; gap: 8px;
  }
  #file-preview.active { display: flex; }
  #file-preview-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--accent); }
  #remove-file {
    cursor: pointer; background: none; border: none;
    color: var(--text-muted); font-size: 13px; padding: 2px 5px;
    border-radius: 4px; transition: color 0.15s;
  }
  #remove-file:hover { color: var(--danger); }

  .input-row { display: flex; align-items: flex-end; gap: 4px; padding: 8px 10px; }
  #message-input {
    flex: 1; background: transparent; border: none; outline: none;
    color: var(--text); font-family: inherit; font-size: 0.91rem;
    resize: none; min-height: 24px; max-height: 140px;
    line-height: 1.5; padding: 4px 6px;
  }
  #message-input::placeholder { color: var(--text-muted); }

  .icon-btn {
    width: 36px; height: 36px;
    background: none; border: none; cursor: pointer;
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    color: var(--text-muted); transition: all 0.15s; flex-shrink: 0;
  }
  .icon-btn:hover { background: var(--surface2); color: var(--text); }
  .icon-btn.recording { color: var(--danger); background: rgba(248,113,113,0.1); }
  #send-btn {
    width: 36px; height: 36px;
    background: var(--user-grad); border: none; border-radius: 9px;
    cursor: pointer; display: flex; align-items: center; justify-content: center;
    color: #fff; transition: all 0.2s; flex-shrink: 0;
    box-shadow: 0 2px 10px rgba(91,138,240,0.35);
  }
  #send-btn:hover { transform: scale(1.07); box-shadow: 0 4px 16px rgba(91,138,240,0.5); }
  #send-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
  #file-input { display: none; }

  .hint-text { text-align: center; font-size: 0.68rem; color: var(--text-muted); margin-top: 8px; opacity: 0.65; }

  @media (max-width: 760px) {
    .app-shell { grid-template-columns: 1fr; }
    #sidebar {
      position: fixed;
      left: -290px;
      top: 0;
      bottom: 0;
      width: 280px;
      z-index: 20;
      transition: 0.2s;
      box-shadow: 20px 0 50px rgba(0,0,0,0.4);
    }
    #sidebar.open { left: 0; }
    .menu-btn { display: inline-flex; align-items: center; justify-content: center; }
    header { padding: 10px 14px; }
    #chat-container { padding: 16px 8px 8px; }
    #input-area { padding: 8px 8px 14px; }
    .bubble { max-width: 90vw; }
  }
</style>
</head>
<body>
<div class="app-shell">
  <aside id="sidebar">
    <div class="sidebar-top">
      <button class="new-chat-btn" onclick="newChat()">＋ New chat</button>
    </div>
    <div class="sidebar-title">Recent</div>
    <div id="chat-list"></div>
  </aside>

  <main id="main">
    <header>
      <button class="menu-btn" onclick="toggleSidebar()">☰</button>
      <div class="header-logo" id="header-logo-wrap">
        <img src="{{ logo_url }}" alt="NB"
             onerror="this.style.display='none';document.getElementById('logo-fallback').style.display='flex'">
        <span id="logo-fallback" class="fallback" style="display:none">🤖</span>
      </div>
      <div>
        <div class="header-title">Baxtiyor AI</div>
        <div class="header-sub">Intelligent Assistant by BAXTIYOR NAJIMOV</div>
      </div>
      <div class="status-dot" title="Online"></div>
    </header>

    <div id="chat-container">
      <div class="empty-state" id="empty-state">
        <div class="empty-logo">
          <img src="{{ logo_url }}" alt="NB"
               onerror="this.style.display='none';this.parentElement.textContent='✨'">
        </div>
        <h2>Baxtiyor AI</h2>
        <p>Your intelligent assistant for coding, writing, analysis, and more.</p>
        <div class="suggestions">
          <button class="suggestion-btn" onclick="suggest('Salom! Nima qila olasan?')">Salom! Nima qila olasan?</button>
          <button class="suggestion-btn" onclick="suggest('Explain machine learning simply')">Explain machine learning</button>
          <button class="suggestion-btn" onclick="suggest('Что такое нейросеть?')">Что такое нейросеть?</button>
          <button class="suggestion-btn" onclick="suggest('Write a Python hello world')">Python code help</button>
        </div>
      </div>
    </div>

    <div id="input-area">
      <div class="input-wrapper">
        <div id="file-preview">
          <span>📎</span>
          <span id="file-preview-name"></span>
          <button id="remove-file" title="Remove file">✕</button>
        </div>
        <div class="input-row">
          <label for="file-input" class="icon-btn" title="Attach file">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>
            </svg>
          </label>
          <input type="file" id="file-input" accept=".txt,.pdf,.docx,.py,.js,.html,.css,.json,.csv,.md,.png,.jpg,.jpeg,.webp,.gif,.mp3,.wav,.ogg,.m4a,.webm"/>

          <textarea id="message-input" placeholder="Message Baxtiyor AI..." rows="1"></textarea>

          <button class="icon-btn" id="mic-btn" title="Voice input">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/>
              <path d="M19 10v2a7 7 0 01-14 0v-2"/>
              <line x1="12" y1="19" x2="12" y2="23"/>
              <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
          </button>

          <button id="send-btn" title="Send">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
      </div>
      <p class="hint-text">Baxtiyor AI can make mistakes. Always verify important information.</p>
    </div>
  </main>
</div>

<script>
// ── User identity ─────────────────────────────────────────────────────────
let userId = localStorage.getItem('baxtiyor_uid');
if (!userId) {
  userId = 'u_' + Math.random().toString(36).slice(2,10) + Date.now().toString(36);
  localStorage.setItem('baxtiyor_uid', userId);
}

let currentChatId = localStorage.getItem('baxtiyor_current_chat_id') || '';
let userName = localStorage.getItem('baxtiyor_name') || '';

// ── Element references ───────────────────────────────────────────────────
const chatContainer = document.getElementById('chat-container');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const fileInput = document.getElementById('file-input');
const filePreview = document.getElementById('file-preview');
const filePreviewName = document.getElementById('file-preview-name');
const removeFileBtn = document.getElementById('remove-file');
const micBtn = document.getElementById('mic-btn');
const chatList = document.getElementById('chat-list');
const sidebar = document.getElementById('sidebar');

let currentFile = null;
let isLoading = false;
let recognition = null;
let isRecording = false;

// ── Layout helpers ───────────────────────────────────────────────────────
function toggleSidebar() { sidebar.classList.toggle('open'); }
function scrollBottom() { chatContainer.scrollTop = chatContainer.scrollHeight; }

function emptyStateHtml() {
  return `
    <div class="empty-state" id="empty-state">
      <div class="empty-logo">
        <img src="{{ logo_url }}" alt="NB" onerror="this.style.display='none';this.parentElement.textContent='✨'">
      </div>
      <h2>Baxtiyor AI</h2>
      <p>Your intelligent assistant for coding, writing, analysis, and more.</p>
      <div class="suggestions">
        <button class="suggestion-btn" onclick="suggest('Salom! Nima qila olasan?')">Salom! Nima qila olasan?</button>
        <button class="suggestion-btn" onclick="suggest('Explain machine learning simply')">Explain machine learning</button>
        <button class="suggestion-btn" onclick="suggest('Что такое нейросеть?')">Что такое нейросеть?</button>
        <button class="suggestion-btn" onclick="suggest('Write a Python hello world')">Python code help</button>
      </div>
    </div>`;
}

function resetChatView() {
  chatContainer.innerHTML = emptyStateHtml();
}

function removeEmptyState() {
  const emptyState = document.getElementById('empty-state');
  if (emptyState) emptyState.remove();
}

// ── Chat sidebar API ─────────────────────────────────────────────────────
async function loadChats() {
  try {
    const res = await fetch(`/api/chats?user_id=${encodeURIComponent(userId)}`);
    const data = await res.json();
    renderChatList(data.chats || []);

    if (!currentChatId && data.chats && data.chats.length) {
      currentChatId = String(data.chats[0].id);
      localStorage.setItem('baxtiyor_current_chat_id', currentChatId);
      await loadChatMessages(currentChatId);
    }
  } catch (err) {
    console.error('loadChats error', err);
  }
}

function renderChatList(chats) {
  chatList.innerHTML = '';
  if (!chats.length) {
    const div = document.createElement('div');
    div.style.color = 'var(--text-muted)';
    div.style.fontSize = '0.8rem';
    div.style.padding = '8px 10px';
    div.textContent = 'No chats yet';
    chatList.appendChild(div);
    return;
  }

  chats.forEach(chat => {
    const btn = document.createElement('button');
    btn.className = 'chat-item' + (String(chat.id) === String(currentChatId) ? ' active' : '');
    btn.onclick = () => selectChat(chat.id);

    const title = document.createElement('span');
    title.className = 'chat-item-title';
    title.textContent = chat.title || 'New chat';

    const del = document.createElement('button');
    del.className = 'chat-delete';
    del.textContent = '×';
    del.title = 'Delete chat';
    del.onclick = (e) => {
      e.stopPropagation();
      deleteChat(chat.id);
    };

    btn.appendChild(document.createTextNode('💬'));
    btn.appendChild(title);
    btn.appendChild(del);
    chatList.appendChild(btn);
  });
}

async function newChat() {
  try {
    const res = await fetch('/api/chats', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({user_id: userId, title: 'New chat'})
    });
    const data = await res.json();
    currentChatId = String(data.chat_id);
    localStorage.setItem('baxtiyor_current_chat_id', currentChatId);
    resetChatView();
    await loadChats();
    messageInput.focus();
  } catch (err) {
    console.error('newChat error', err);
  }
}

async function selectChat(chatId) {
  currentChatId = String(chatId);
  localStorage.setItem('baxtiyor_current_chat_id', currentChatId);
  await loadChatMessages(currentChatId);
  await loadChats();
  sidebar.classList.remove('open');
}

async function deleteChat(chatId) {
  if (!confirm('Delete this chat?')) return;
  try {
    await fetch(`/api/chats/${chatId}`, {method: 'DELETE'});
    if (String(chatId) === String(currentChatId)) {
      currentChatId = '';
      localStorage.removeItem('baxtiyor_current_chat_id');
      resetChatView();
    }
    await loadChats();
  } catch (err) {
    console.error('deleteChat error', err);
  }
}

async function loadChatMessages(chatId) {
  try {
    const res = await fetch(`/api/chats/${chatId}/messages`);
    const data = await res.json();
    chatContainer.innerHTML = '';
    const messages = data.messages || [];

    if (!messages.length) {
      resetChatView();
      return;
    }

    messages.forEach(m => {
      if (m.role && m.content) {
        addMessage(m.role === 'assistant' ? 'bot' : 'user', m.content, null, m.provider, false);
      } else {
        if (m.user_message) addMessage('user', m.user_message, m.file_name, null, false);
        if (m.bot_reply) addMessage('bot', m.bot_reply, m.file_name, m.provider, false);
      }
    });
    scrollBottom();
  } catch (err) {
    console.error('loadChatMessages error', err);
  }
}

// ── Auto-resize textarea ─────────────────────────────────────────────────
messageInput.addEventListener('input', () => {
  messageInput.style.height = 'auto';
  messageInput.style.height = Math.min(messageInput.scrollHeight, 140) + 'px';
});

messageInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// ── File handling ────────────────────────────────────────────────────────
fileInput.addEventListener('change', () => {
  const f = fileInput.files[0];
  if (f) {
    currentFile = f;
    filePreviewName.textContent = f.name;
    filePreview.classList.add('active');
  }
});
removeFileBtn.addEventListener('click', clearFile);
function clearFile() {
  currentFile = null;
  fileInput.value = '';
  filePreview.classList.remove('active');
}

// ── Utilities ────────────────────────────────────────────────────────────
function escapeHtml(s) {
  return String(s || '')
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;')
    .replace(/'/g,'&#039;');
}

function formatMessage(text) {
  text = escapeHtml(text);
  text = text.replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
  text = text.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
  text = text.replace(/\n/g, '<br>');
  return text;
}

function suggest(text) {
  messageInput.value = text;
  messageInput.focus();
  sendMessage();
}

// ── Add a message bubble ─────────────────────────────────────────────────
function addMessage(role, content, fileName, provider, doScroll = true) {
  removeEmptyState();
  const isBot = role === 'bot';
  const row = document.createElement('div');
  row.className = `msg-row ${role}`;

  const avatar = document.createElement('div');
  avatar.className = `avatar ${isBot ? 'bot-av' : 'user-av'}`;
  avatar.textContent = isBot ? '🤖' : '👤';

  const col = document.createElement('div');

  if (fileName && !isBot) {
    const chip = document.createElement('div');
    chip.className = 'file-chip';
    chip.innerHTML = `📎 ${escapeHtml(fileName)}`;
    col.appendChild(chip);
  }

  const bubble = document.createElement('div');
  bubble.className = `bubble ${role}`;
  bubble.innerHTML = formatMessage(content);
  col.appendChild(bubble);

  if (isBot && fileName) {
    const chip = document.createElement('div');
    chip.className = 'file-chip bot-chip';
    chip.innerHTML = `📎 ${escapeHtml(fileName)}`;
    col.appendChild(chip);
  }

  if (isBot && provider && provider !== 'creator_rule') {
    const tag = document.createElement('div');
    tag.className = 'provider-tag';
    tag.textContent = `via ${provider}`;
    col.appendChild(tag);
  }

  if (isBot) {
    row.appendChild(avatar);
    row.appendChild(col);
  } else {
    row.appendChild(col);
    row.appendChild(avatar);
  }

  chatContainer.appendChild(row);
  if (doScroll) scrollBottom();
}

// ── Loading indicator ────────────────────────────────────────────────────
function addLoading() {
  const row = document.createElement('div');
  row.id = 'loading-row';
  row.className = 'msg-row bot';
  const av = document.createElement('div');
  av.className = 'avatar bot-av';
  av.textContent = '🤖';
  const bub = document.createElement('div');
  bub.className = 'bubble bot loading-bubble';
  bub.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
  row.appendChild(av);
  row.appendChild(bub);
  chatContainer.appendChild(row);
  scrollBottom();
}
function removeLoading() {
  const el = document.getElementById('loading-row');
  if (el) el.remove();
}

// ── Send message ─────────────────────────────────────────────────────────
async function sendMessage() {
  const text = messageInput.value.trim();
  if ((!text && !currentFile) || isLoading) return;

  if (!currentChatId) {
    await newChat();
  }

  isLoading = true;
  sendBtn.disabled = true;

  const displayText = text || '(File uploaded — please analyze it.)';
  const fileName = currentFile ? currentFile.name : null;
  addMessage('user', displayText, fileName);

  const formData = new FormData();
  formData.append('user_id', userId);
  formData.append('chat_id', currentChatId);
  formData.append('message', text);
  if (currentFile) formData.append('file', currentFile);

  messageInput.value = '';
  messageInput.style.height = 'auto';
  clearFile();

  addLoading();

  try {
    const res = await fetch('/chat', { method: 'POST', body: formData });
    const data = await res.json();
    removeLoading();
    addMessage('bot', data.reply || 'Something went wrong.', data.file_name, data.provider);
    await loadChats();
  } catch (err) {
    removeLoading();
    addMessage('bot', '❌ Network error. Please check your connection.');
    console.error(err);
  }

  isLoading = false;
  sendBtn.disabled = false;
  messageInput.focus();
}

sendBtn.addEventListener('click', sendMessage);

// ── Speech recognition ───────────────────────────────────────────────────
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SR) {
  recognition = new SR();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.onresult = e => {
    const t = Array.from(e.results).map(r => r[0].transcript).join('');
    messageInput.value = t;
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 140) + 'px';
  };
  recognition.onend = () => { isRecording = false; micBtn.classList.remove('recording'); };
  recognition.onerror = () => { isRecording = false; micBtn.classList.remove('recording'); };
  micBtn.addEventListener('click', () => {
    if (isRecording) { recognition.stop(); return; }
    recognition.lang = navigator.language || 'uz-UZ';
    recognition.start();
    isRecording = true;
    micBtn.classList.add('recording');
  });
} else {
  micBtn.addEventListener('click', () =>
    alert('Speech recognition is not supported in your browser. Try Chrome or Edge.'));
}

// ── Initial load ─────────────────────────────────────────────────────────
loadChats();
</script>
</body>
</html>
"""


# ════════════════════════════════════════════════════════════════════════════
# HTML — ADMIN PANEL
# ════════════════════════════════════════════════════════════════════════════

ADMIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Baxtiyor AI — Admin</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: system-ui, sans-serif;
    background: #0b0d13;
    color: #e8eaf2;
    padding: 24px;
    min-height: 100vh;
  }
  h1 { font-size: 1.45rem; font-weight: 700; color: #8ab4f8; margin-bottom: 4px; }
  .sub { font-size: 0.78rem; color: #5c6278; margin-bottom: 20px; }

  .stats { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 22px; }
  .stat {
    background: #12141c; border: 1px solid #22253a;
    border-radius: 10px; padding: 12px 16px;
    font-size: 0.78rem; color: #9ca3af; min-width: 90px;
  }
  .stat span { font-size: 1.5rem; font-weight: 700; color: #5b8af0; display: block; margin-bottom: 2px; }

  .filter-bar { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 18px; align-items: center; }
  .filter-bar input, .filter-bar select {
    background: #12141c; border: 1px solid #22253a;
    color: #e8eaf2; padding: 7px 12px; border-radius: 8px;
    font-size: 0.8rem; font-family: inherit; outline: none;
  }
  .filter-bar input:focus, .filter-bar select:focus { border-color: #5b8af0; }
  .filter-bar input { flex: 1; min-width: 160px; }

  .wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
  th {
    text-align: left; padding: 10px 12px;
    background: #12141c; border-bottom: 2px solid #22253a;
    color: #9ca3af; font-weight: 600;
    position: sticky; top: 0; z-index: 1;
  }
  td { padding: 10px 12px; border-bottom: 1px solid #191c27; vertical-align: top; max-width: 260px; word-break: break-word; }
  tr:hover td { background: #12141c; }

  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.68rem; font-weight: 600; }
  .badge.groq { background: rgba(74,222,128,0.12); color: #4ade80; }
  .badge.huggingface { background: rgba(251,191,36,0.12); color: #fbbf24; }
  .badge.creator_rule { background: rgba(167,139,250,0.12); color: #a78bf0; }
  .badge.fallback { background: rgba(248,113,113,0.12); color: #f87171; }
  .badge.system { background: rgba(148,163,184,0.12); color: #94a3b8; }

  .file-link { color: #5b8af0; text-decoration: none; }
  .file-link:hover { text-decoration: underline; }
  .thumb-wrap { margin-top: 4px; }
  .thumb-wrap img { width: 60px; height: 60px; object-fit: cover; border-radius: 6px; border: 1px solid #22253a; }
  audio { width: 120px; margin-top: 4px; }
  .extracted-text {
    max-height: 70px; overflow-y: auto;
    font-size: 0.7rem; color: #9ca3af;
    background: #0b0d13; padding: 6px;
    border-radius: 6px; white-space: pre-wrap;
    margin-top: 4px;
  }
  .no-data { text-align: center; padding: 48px; color: #5c6278; font-size: 0.9rem; }
  .ts { white-space: nowrap; color: #5c6278; font-size: 0.72rem; }
  .uid { font-size: 0.68rem; color: #5c6278; }
</style>
</head>
<body>
<h1>🛡 Baxtiyor AI — Admin Panel</h1>
<p class="sub">Total messages in DB: <strong>{{ total }}</strong> &nbsp;|&nbsp; Showing latest {{ messages|length }}</p>

<div class="stats">
  {% for p, c in providers.items() %}
  <div class="stat"><span>{{ c }}</span>{{ p }}</div>
  {% endfor %}
</div>

<div class="filter-bar">
  <input type="text" id="filter-text" placeholder="🔍 Search messages or user ID…" oninput="applyFilter()"/>
  <select id="filter-provider" onchange="applyFilter()">
    <option value="">All providers</option>
    <option value="groq">groq</option>
    <option value="huggingface">huggingface</option>
    <option value="creator_rule">creator_rule</option>
    <option value="fallback">fallback</option>
    <option value="system">system</option>
  </select>
</div>

<div class="wrap">
<table id="msgs-table">
  <thead>
    <tr>
      <th>#</th>
      <th>Time</th>
      <th>User ID</th>
      <th>Chat ID</th>
      <th>Question</th>
      <th>Reply</th>
      <th>Provider</th>
      <th>File</th>
      <th>Extracted</th>
    </tr>
  </thead>
  <tbody id="msgs-body">
  {% if messages %}
    {% for m in messages %}
    <tr
      data-uid="{{ m['user_id'] or '' }}"
      data-q="{{ m['user_message'] or m['content'] or '' }}"
      data-a="{{ m['bot_reply'] or '' }}"
      data-provider="{{ m['provider'] or '' }}"
    >
      <td>{{ m['id'] }}</td>
      <td class="ts">{{ m['timestamp'] or m['created_at'] }}</td>
      <td class="uid">{{ (m['user_id'] or '')[:14] }}…</td>
      <td>{{ m['chat_id'] or '' }}</td>
      <td>{{ m['user_message'] or (m['content'] if m['role'] == 'user' else '') }}</td>
      <td>{{ (m['bot_reply'] or (m['content'] if m['role'] == 'assistant' else '') or '')[:200] }}</td>
      <td>
        {% if m['provider'] %}
        <span class="badge {{ m['provider'] }}">{{ m['provider'] }}</span>
        {% endif %}
      </td>
      <td>
        {% if m['file_name'] %}
          <a class="file-link" href="/uploads/{{ m['file_name'] }}" target="_blank">📎 {{ m['file_name'][:22] }}</a>
          <span style="display:block;font-size:0.68rem;color:#5c6278">{{ m['file_type'] }}</span>
          {% if m['file_type'] in ['png','jpg','jpeg','webp','gif'] %}
          <div class="thumb-wrap"><img src="/uploads/{{ m['file_name'] }}" alt="thumb" loading="lazy"></div>
          {% elif m['file_type'] in ['mp3','wav','ogg','m4a','webm'] %}
          <audio controls preload="none" src="/uploads/{{ m['file_name'] }}"></audio>
          {% endif %}
        {% endif %}
      </td>
      <td>
        {% if m['file_text'] %}
        <div class="extracted-text">{{ m['file_text'][:300] }}</div>
        {% endif %}
      </td>
    </tr>
    {% endfor %}
  {% else %}
    <tr><td colspan="9" class="no-data">No messages yet.</td></tr>
  {% endif %}
  </tbody>
</table>
</div>

<script>
function applyFilter() {
  const q = document.getElementById('filter-text').value.toLowerCase();
  const pv = document.getElementById('filter-provider').value.toLowerCase();
  document.querySelectorAll('#msgs-body tr[data-uid]').forEach(row => {
    const uid = (row.dataset.uid || '').toLowerCase();
    const question = (row.dataset.q || '').toLowerCase();
    const answer = (row.dataset.a || '').toLowerCase();
    const provider = (row.dataset.provider || '').toLowerCase();
    const textOk = !q || uid.includes(q) || question.includes(q) || answer.includes(q);
    const providerOk = !pv || provider === pv;
    row.style.display = (textOk && providerOk) ? '' : 'none';
  });
}
</script>
</body>
</html>
"""


# ════════════════════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Main chat page."""
    return render_template_string(CHAT_HTML, logo_url=LOGO_URL)


@app.route("/health")
def health():
    """Quick health check — useful for monitoring and Render uptime checks."""
    return jsonify({"status": "ok", "app": "Baxtiyor AI"})


# ════════════════════════════════════════════════════════════════════════════
# CHAT API ROUTES — SIDEBAR / CHATGPT-STYLE HISTORY
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/chats", methods=["GET"])
def api_get_chats():
    """Return chats for the current user."""
    user_id = request.args.get("user_id", "anonymous")
    chats = get_chats(user_id=user_id)
    return jsonify({"chats": chats})


@app.route("/api/chats", methods=["POST"])
def api_create_chat():
    """Create a new chat."""
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "anonymous")
    title = data.get("title", "New chat")
    chat_id = create_chat(title=title, user_id=user_id)
    return jsonify({"chat_id": chat_id, "title": title})


@app.route("/api/chats/<int:chat_id>/messages", methods=["GET"])
def api_get_chat_messages(chat_id):
    """Return messages for one chat."""
    messages = get_messages(chat_id)
    return jsonify({"messages": messages})


@app.route("/api/chats/<int:chat_id>", methods=["DELETE"])
def api_delete_chat(chat_id):
    """Delete one chat."""
    delete_chat(chat_id)
    return jsonify({"ok": True})


@app.route("/chat", methods=["POST"])
def chat():
    """
    Main AI endpoint.

    Flow:
    1. Parse incoming form data (message + optional file)
    2. Extract text from file if provided
    3. Load conversation history from SQLite / chat session
    4. Append new user message to history
    5. Call AI (Groq → HuggingFace → fallback)
    6. Save result to DB
    7. Return JSON response
    """
    user_id = request.form.get("user_id", "anonymous")
    chat_id_raw = request.form.get("chat_id", "").strip()
    message = request.form.get("message", "").strip()

    # ── Resolve or create chat ─────────────────────────────────────────────
    chat_id = None
    if chat_id_raw:
        try:
            chat_id = int(chat_id_raw)
        except ValueError:
            chat_id = None

    if chat_id is None:
        title = message[:60] if message else "New chat"
        chat_id = create_chat(title=title or "New chat", user_id=user_id)

    # ── Handle file upload ─────────────────────────────────────────────────
    file_name = None
    file_type = None
    file_text = None
    saved_name = None

    uploaded = request.files.get("file")
    if uploaded and uploaded.filename and allowed_file(uploaded.filename):
        ext = uploaded.filename.rsplit(".", 1)[1].lower()
        safe = secure_filename(uploaded.filename)
        unique_name = f"{uuid.uuid4().hex}_{safe}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
        uploaded.save(save_path)

        file_name = unique_name
        file_type = ext
        saved_name = unique_name
        file_text = extract_text(save_path, ext)

        # Extra metadata table from database.py
        try:
            save_uploaded_file(
                chat_id=chat_id,
                user_id=user_id,
                filename=unique_name,
                original_name=safe,
                file_type=ext,
                file_path=save_path,
                mime_type=uploaded.mimetype,
                size=os.path.getsize(save_path) if os.path.exists(save_path) else None,
            )
        except Exception as e:
            print(f"[uploaded_files metadata error] {e}")

    # ── Require at least a message or a file ───────────────────────────────
    if not message and not file_name:
        return jsonify({
            "reply": "Please type a message.",
            "provider": "system",
            "file_name": None,
            "chat_id": chat_id,
        })

    if not message:
        message = "I uploaded a file. Please analyze it."

    # ── Build user content (message + file text if readable) ───────────────
    user_content = message
    if file_text and not file_text.startswith("["):
        user_content = f"{message}\n\n[Attached file content]:\n{file_text}"

    # ── Load history from database.py ──────────────────────────────────────
    # Prefer chat-specific history for sidebar sessions.
    messages_history = get_chat_history_for_ai(chat_id, limit=10)

    # If this is an old/legacy chat with no chat_id-based records yet,
    # fallback to user_id-based memory.
    if not messages_history:
        messages_history = get_db_history(user_id, limit=10)

    # Append current user message to history for this call.
    messages_history = messages_history + [
        {"role": "user", "content": user_content}
    ]

    # ── Get AI response ────────────────────────────────────────────────────
    reply, provider = get_ai_response(user_content, messages_history)

    # ── Save to database — legacy format keeps admin compatible ────────────
    save_message(user_id, message, reply, provider, file_name, file_type, file_text)

    # ── Save to database — chat format powers sidebar sessions ─────────────
    try:
        database_save_message(chat_id, "user", user_content, None)
        database_save_message(chat_id, "assistant", reply, provider)
    except Exception as e:
        print(f"[chat message save error] {e}")

    # ── Auto title update for chat ─────────────────────────────────────────
    try:
        chat = get_chat(chat_id)
        if chat and (chat.get("title") == "New chat" or not chat.get("title")):
            title = message.strip()[:60] or "New chat"
            if len(message.strip()) > 60:
                title += "..."
            update_chat_title(chat_id, title)
    except Exception as e:
        print(f"[chat title update error] {e}")

    # ── Return JSON response ───────────────────────────────────────────────
    return jsonify({
        "reply": reply,
        "provider": provider,
        "file_name": saved_name,
        "chat_id": chat_id,
    })


@app.route("/uploads/<filename>")
def serve_upload(filename):
    """Serve uploaded files (images, audio, docs) for admin preview."""
    safe = secure_filename(filename)
    return send_from_directory(app.config["UPLOAD_FOLDER"], safe)


@app.route("/admin")
def admin():
    """
    Admin panel — protected by password query param.
    Usage: /admin?password=YOUR_PASSWORD
    """
    pwd = request.args.get("password", "")
    if pwd != ADMIN_PASSWORD:
        return "❌ Access denied. Use /admin?password=YOUR_PASSWORD", 403

    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM messages ORDER BY id DESC LIMIT 300"
        ).fetchall()
        rows = [dict(r) for r in rows]

        # Provider usage counts
        p_counts = {}
        for r in conn.execute(
            "SELECT provider, COUNT(*) AS c FROM messages GROUP BY provider ORDER BY c DESC"
        ):
            p_counts[r["provider"] or "unknown"] = r["c"]

    return render_template_string(
        ADMIN_HTML,
        messages=rows,
        total=total,
        providers=p_counts,
    )


# ════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # debug=False in production (Render uses gunicorn, not this directly)
    app.run(host="0.0.0.0", port=port, debug=False)
