import sqlite3
import os
from datetime import datetime


# ============================================================
# DATABASE CONFIG
# ============================================================

DATABASE_PATH = os.environ.get("DATABASE_PATH", "baxtiyor_ai.db")


# ============================================================
# CONNECTION
# ============================================================

def get_connection():
    """
    SQLite ulanishini ochadi.
    row_factory dict kabi ishlashga yordam beradi.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def now_iso():
    """Hozirgi vaqtni ISO formatda qaytaradi."""
    return datetime.utcnow().isoformat()


# ============================================================
# DATABASE INIT + SAFE MIGRATION
# ============================================================

def add_column_if_missing(cursor, table, column, definition):
    """
    Agar jadvalda kerakli column yo‘q bo‘lsa, avtomatik qo‘shadi.
    Bu eski database buzilmasligi uchun kerak.
    """
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row["name"] for row in cursor.fetchall()]

    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    """
    Barcha kerakli jadvallarni yaratadi.
    App ishga tushganda avtomatik chaqiriladi.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # ----------------------------
    # CHATS TABLE
    # ChatGPT kabi chap panel chatlari uchun
    # ----------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT 'New chat',
            user_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Eski database bo‘lsa user_id qo‘shish
    add_column_if_missing(cursor, "chats", "user_id", "TEXT")

    # ----------------------------
    # MESSAGES TABLE
    # Ikkala formatni ham qo‘llaydi:
    # 1) chat_id / role / content
    # 2) user_id / user_message / bot_reply
    # ----------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            chat_id INTEGER,
            user_id TEXT,

            role TEXT,
            content TEXT,

            user_message TEXT,
            bot_reply TEXT,

            provider TEXT,

            file_name TEXT,
            file_type TEXT,
            file_text TEXT,

            created_at TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        )
    """)

    # Eski/new database uchun xavfsiz migration
    add_column_if_missing(cursor, "messages", "chat_id", "INTEGER")
    add_column_if_missing(cursor, "messages", "user_id", "TEXT")
    add_column_if_missing(cursor, "messages", "role", "TEXT")
    add_column_if_missing(cursor, "messages", "content", "TEXT")
    add_column_if_missing(cursor, "messages", "user_message", "TEXT")
    add_column_if_missing(cursor, "messages", "bot_reply", "TEXT")
    add_column_if_missing(cursor, "messages", "provider", "TEXT")
    add_column_if_missing(cursor, "messages", "file_name", "TEXT")
    add_column_if_missing(cursor, "messages", "file_type", "TEXT")
    add_column_if_missing(cursor, "messages", "file_text", "TEXT")
    add_column_if_missing(cursor, "messages", "created_at", "TEXT")

    # ----------------------------
    # MEMORIES TABLE
    # Uzoq muddatli xotira uchun:
    # ism, loyiha nomi, til, preference
    # ----------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # ----------------------------
    # UPLOADED FILES TABLE
    # Fayl upload metadata
    # ----------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id TEXT,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            mime_type TEXT,
            size INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE SET NULL
        )
    """)

    add_column_if_missing(cursor, "uploaded_files", "user_id", "TEXT")
    add_column_if_missing(cursor, "uploaded_files", "mime_type", "TEXT")
    add_column_if_missing(cursor, "uploaded_files", "size", "INTEGER")

    # ----------------------------
    # VOICE MESSAGES TABLE
    # Ovozli xabarlar uchun
    # ----------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voice_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id TEXT,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            transcription TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE SET NULL
        )
    """)

    add_column_if_missing(cursor, "voice_messages", "user_id", "TEXT")

    # ----------------------------
    # IMAGES TABLE
    # Rasmlar uchun
    # ----------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id TEXT,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE SET NULL
        )
    """)

    add_column_if_missing(cursor, "images", "user_id", "TEXT")

    # ----------------------------
    # INDEXES
    # Tezroq qidirish uchun
    # ----------------------------
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_user_id ON chats(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON chats(updated_at)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_uploaded_files_chat_id ON uploaded_files(chat_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_uploaded_files_user_id ON uploaded_files(user_id)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_voice_messages_chat_id ON voice_messages(chat_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_voice_messages_user_id ON voice_messages(user_id)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_chat_id ON images(chat_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_user_id ON images(user_id)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)")

    conn.commit()
    conn.close()


# ============================================================
# CHAT FUNCTIONS
# ============================================================

def create_chat(title="New chat", user_id=None):
    """
    Yangi chat yaratadi.
    Sidebar uchun ishlatiladi.
    """
    now = now_iso()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO chats (title, user_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (title, user_id, now, now)
    )

    chat_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return chat_id


def get_chats(user_id=None):
    """
    Chatlar ro‘yxatini qaytaradi.
    Agar user_id berilsa, faqat shu user chatlarini beradi.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if user_id:
        cursor.execute(
            "SELECT * FROM chats WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,)
        )
    else:
        cursor.execute("SELECT * FROM chats ORDER BY updated_at DESC")

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_chat(chat_id):
    """Bitta chatni ID orqali qaytaradi."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM chats WHERE id = ?", (chat_id,))
    row = cursor.fetchone()

    conn.close()
    return dict(row) if row else None


def update_chat_title(chat_id, title):
    """Chat sarlavhasini yangilaydi."""
    now = now_iso()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
        (title, now, chat_id)
    )

    conn.commit()
    conn.close()


def delete_chat(chat_id):
    """Chatni o‘chiradi. Messages ham CASCADE bilan o‘chadi."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))

    conn.commit()
    conn.close()


# ============================================================
# MESSAGE FUNCTIONS
# ============================================================

def save_message(*args, **kwargs):
    """
    Xabarni saqlaydi.

    2 xil ishlashni qo‘llaydi:

    1) Yangi chat format:
       save_message(chat_id, role, content, provider=None)

    2) Sizning hozirgi app_boshlangich.py formatingiz:
       save_message(user_id, user_message, bot_reply, provider, file_name, file_type, file_text)

    Shuning uchun eski kod ham buzilmaydi, yangi kod ham ishlaydi.
    """
    now = now_iso()
    conn = get_connection()
    cursor = conn.cursor()

    # ----------------------------
    # FORMAT 2: legacy / current app format
    # save_message(user_id, message, reply, provider, file_name, file_type, file_text)
    # ----------------------------
    if len(args) >= 7:
        user_id = args[0]
        user_message = args[1]
        bot_reply = args[2]
        provider = args[3]
        file_name = args[4]
        file_type = args[5]
        file_text = args[6]

        cursor.execute("""
            INSERT INTO messages
              (user_id, user_message, bot_reply, provider,
               file_name, file_type, file_text, created_at, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            user_id,
            user_message,
            bot_reply,
            provider,
            file_name,
            file_type,
            file_text,
            now
        ))

        message_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return message_id

    # ----------------------------
    # FORMAT 1: chat-based format
    # save_message(chat_id, role, content, provider=None)
    # ----------------------------
    chat_id = args[0] if len(args) > 0 else kwargs.get("chat_id")
    role = args[1] if len(args) > 1 else kwargs.get("role")
    content = args[2] if len(args) > 2 else kwargs.get("content")
    provider = args[3] if len(args) > 3 else kwargs.get("provider")

    cursor.execute("""
        INSERT INTO messages
          (chat_id, role, content, provider, created_at, timestamp)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (chat_id, role, content, provider, now))

    message_id = cursor.lastrowid

    cursor.execute(
        "UPDATE chats SET updated_at = ? WHERE id = ?",
        (now, chat_id)
    )

    # Birinchi user xabaridan avtomatik title qilish
    if role == "user" and content:
        cursor.execute("SELECT title FROM chats WHERE id = ?", (chat_id,))
        row = cursor.fetchone()

        if row and row["title"] == "New chat":
            auto_title = content.strip()[:60]
            if len(content.strip()) > 60:
                auto_title += "..."

            cursor.execute(
                "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
                (auto_title, now, chat_id)
            )

    conn.commit()
    conn.close()
    return message_id


def get_messages(chat_id, limit=None):
    """
    Bitta chat ichidagi xabarlarni qaytaradi.
    limit berilsa, oxirgi N ta xabarni oladi.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if limit:
        cursor.execute("""
            SELECT * FROM messages
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (chat_id, limit))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in reversed(rows)]

    cursor.execute("""
        SELECT * FROM messages
        WHERE chat_id = ?
        ORDER BY id ASC
    """, (chat_id,))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_db_history(user_id, limit=10):
    """
    Sizning app_boshlangich.py ichidagi memory uchun kerak.

    Bu funksiya oxirgi suhbatlarni OpenAI/Groq formatida qaytaradi:
    [
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": "..."}
    ]
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_message, bot_reply
        FROM messages
        WHERE user_id = ?
          AND (provider IS NULL OR provider != 'system')
        ORDER BY id DESC
        LIMIT ?
    """, (user_id, limit))

    rows = cursor.fetchall()
    conn.close()

    history = []

    for row in reversed(rows):
        if row["user_message"]:
            history.append({
                "role": "user",
                "content": row["user_message"]
            })

        if row["bot_reply"]:
            history.append({
                "role": "assistant",
                "content": row["bot_reply"]
            })

    return history


def get_chat_history_for_ai(chat_id, limit=10):
    """
    Chat session asosidagi history.
    Keyin sidebar qo‘shilganda kerak bo‘ladi.
    """
    messages = get_messages(chat_id, limit=limit)

    history = []

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        if role and content:
            history.append({
                "role": role,
                "content": content
            })

    return history


# ============================================================
# MEMORY FUNCTIONS
# ============================================================

def save_memory(key, value, category="general"):
    """
    Uzoq muddatli xotira saqlaydi.
    Masalan:
    - user_name
    - project_name
    - preferred_language
    """
    now = now_iso()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO memories (key, value, category, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            category = excluded.category,
            updated_at = excluded.updated_at
    """, (key, value, category, now, now))

    conn.commit()
    conn.close()


def get_memories():
    """Barcha memorylarni qaytaradi."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM memories ORDER BY category ASC, key ASC")
    rows = cursor.fetchall()

    conn.close()
    return [dict(row) for row in rows]


def get_memory(key):
    """Bitta memoryni key orqali oladi."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM memories WHERE key = ?", (key,))
    row = cursor.fetchone()

    conn.close()
    return dict(row) if row else None


def delete_memory(key):
    """Memoryni o‘chiradi."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM memories WHERE key = ?", (key,))

    conn.commit()
    conn.close()


# ============================================================
# UPLOADED FILE FUNCTIONS
# ============================================================

def save_uploaded_file(
    chat_id,
    filename,
    original_name,
    file_type,
    file_path,
    user_id=None,
    mime_type=None,
    size=None
):
    """
    Yuklangan fayl metadata saqlaydi.
    Faylning o‘zi uploads folderda bo‘ladi.
    """
    now = now_iso()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO uploaded_files
          (chat_id, user_id, filename, original_name, file_type,
           file_path, mime_type, size, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chat_id,
        user_id,
        filename,
        original_name,
        file_type,
        file_path,
        mime_type,
        size,
        now
    ))

    file_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return file_id


def get_uploaded_files(chat_id=None, user_id=None):
    """
    Fayllarni qaytaradi.
    chat_id yoki user_id bilan filter qilish mumkin.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if chat_id is not None:
        cursor.execute("""
            SELECT * FROM uploaded_files
            WHERE chat_id = ?
            ORDER BY created_at DESC
        """, (chat_id,))
    elif user_id is not None:
        cursor.execute("""
            SELECT * FROM uploaded_files
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
    else:
        cursor.execute("""
            SELECT * FROM uploaded_files
            ORDER BY created_at DESC
        """)

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ============================================================
# VOICE MESSAGE FUNCTIONS
# ============================================================

def save_voice_message(chat_id, filename, file_path, transcription=None, user_id=None):
    """
    Ovozli xabar metadata saqlaydi.
    Transcription keyin qo‘shilishi mumkin.
    """
    now = now_iso()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO voice_messages
          (chat_id, user_id, filename, file_path, transcription, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        chat_id,
        user_id,
        filename,
        file_path,
        transcription,
        now
    ))

    voice_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return voice_id


def get_voice_messages(chat_id=None, user_id=None):
    """Ovozli xabarlarni qaytaradi."""
    conn = get_connection()
    cursor = conn.cursor()

    if chat_id is not None:
        cursor.execute("""
            SELECT * FROM voice_messages
            WHERE chat_id = ?
            ORDER BY created_at DESC
        """, (chat_id,))
    elif user_id is not None:
        cursor.execute("""
            SELECT * FROM voice_messages
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
    else:
        cursor.execute("""
            SELECT * FROM voice_messages
            ORDER BY created_at DESC
        """)

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ============================================================
# IMAGE FUNCTIONS
# ============================================================

def save_image(chat_id, filename, file_path, description=None, user_id=None):
    """
    Rasm metadata saqlaydi.
    description keyin vision model orqali qo‘shilishi mumkin.
    """
    now = now_iso()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO images
          (chat_id, user_id, filename, file_path, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        chat_id,
        user_id,
        filename,
        file_path,
        description,
        now
    ))

    image_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return image_id


def get_images(chat_id=None, user_id=None):
    """Rasmlarni qaytaradi."""
    conn = get_connection()
    cursor = conn.cursor()

    if chat_id is not None:
        cursor.execute("""
            SELECT * FROM images
            WHERE chat_id = ?
            ORDER BY created_at DESC
        """, (chat_id,))
    elif user_id is not None:
        cursor.execute("""
            SELECT * FROM images
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
    else:
        cursor.execute("""
            SELECT * FROM images
            ORDER BY created_at DESC
        """)

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ============================================================
# ADMIN / STATS FUNCTIONS
# ============================================================

def get_message_count():
    """Jami xabarlar sonini qaytaradi."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS total FROM messages")
    row = cursor.fetchone()

    conn.close()
    return row["total"] if row else 0


def get_provider_counts():
    """AI providerlar statistikasi: groq, huggingface, fallback."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT provider, COUNT(*) AS count
        FROM messages
        GROUP BY provider
        ORDER BY count DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return {
        (row["provider"] or "unknown"): row["count"]
        for row in rows
    }


def search_messages(query, limit=50):
    """
    Admin panel uchun xabar qidirish.
    """
    q = f"%{query}%"

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM messages
        WHERE user_message LIKE ?
           OR bot_reply LIKE ?
           OR content LIKE ?
        ORDER BY id DESC
        LIMIT ?
    """, (q, q, q, limit))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


# ============================================================
# AUTO INIT WHEN IMPORTED
# ============================================================

# App import qilganda database tayyor bo‘lsin.
init_db()
