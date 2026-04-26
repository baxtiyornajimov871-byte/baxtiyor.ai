import sqlite3
import os
from datetime import datetime

DATABASE_PATH = os.environ.get('DATABASE_PATH', 'baxtiyor_ai.db')

def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT 'New chat',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            provider TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE SET NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voice_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            transcription TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE SET NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE SET NULL
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_uploaded_files_chat_id ON uploaded_files(chat_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_voice_messages_chat_id ON voice_messages(chat_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_images_chat_id ON images(chat_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)')
    
    conn.commit()
    conn.close()

def create_chat(title='New chat'):
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO chats (title, created_at, updated_at) VALUES (?, ?, ?)',
        (title, now, now)
    )
    chat_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return chat_id

def get_chats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM chats ORDER BY updated_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_chat(chat_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM chats WHERE id = ?', (chat_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_chat_title(chat_id, title):
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE chats SET title = ?, updated_at = ? WHERE id = ?',
        (title, now, chat_id)
    )
    conn.commit()
    conn.close()

def save_message(chat_id, role, content, provider=None):
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO messages (chat_id, role, content, provider, created_at) VALUES (?, ?, ?, ?, ?)',
        (chat_id, role, content, provider, now)
    )
    message_id = cursor.lastrowid
    cursor.execute(
        'UPDATE chats SET updated_at = ? WHERE id = ?',
        (now, chat_id)
    )
    if role == 'user':
        cursor.execute('SELECT title FROM chats WHERE id = ?', (chat_id,))
        row = cursor.fetchone()
        if row and row['title'] == 'New chat':
            auto_title = content.strip()[:60]
            if len(content.strip()) > 60:
                auto_title += '...'
            cursor.execute(
                'UPDATE chats SET title = ? WHERE id = ?',
                (auto_title, chat_id)
            )
    conn.commit()
    conn.close()
    return message_id

def get_messages(chat_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC',
        (chat_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_chat(chat_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM chats WHERE id = ?', (chat_id,))
    conn.commit()
    conn.close()

def save_memory(key, value, category='general'):
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO memories (key, value, category, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value,
           category = excluded.category, updated_at = excluded.updated_at''',
        (key, value, category, now, now)
    )
    conn.commit()
    conn.close()

def get_memories():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM memories ORDER BY category ASC, key ASC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_memory(key):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM memories WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_memory(key):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM memories WHERE key = ?', (key,))
    conn.commit()
    conn.close()

def save_uploaded_file(chat_id, filename, original_name, file_type, file_path):
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO uploaded_files (chat_id, filename, original_name, file_type, file_path, created_at)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (chat_id, filename, original_name, file_type, file_path, now)
    )
    file_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return file_id

def get_uploaded_files(chat_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if chat_id is not None:
        cursor.execute(
            'SELECT * FROM uploaded_files WHERE chat_id = ? ORDER BY created_at DESC',
            (chat_id,)
        )
    else:
        cursor.execute('SELECT * FROM uploaded_files ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def save_voice_message(chat_id, filename, file_path, transcription=None):
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO voice_messages (chat_id, filename, file_path, transcription, created_at)
           VALUES (?, ?, ?, ?, ?)''',
        (chat_id, filename, file_path, transcription, now)
    )
    voice_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return voice_id

def get_voice_messages(chat_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if chat_id is not None:
        cursor.execute(
            'SELECT * FROM voice_messages WHERE chat_id = ? ORDER BY created_at DESC',
            (chat_id,)
        )
    else:
        cursor.execute('SELECT * FROM voice_messages ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def save_image(chat_id, filename, file_path, description=None):
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO images (chat_id, filename, file_path, description, created_at)
           VALUES (?, ?, ?, ?, ?)''',
        (chat_id, filename, file_path, description, now)
    )
    image_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return image_id

def get_images(chat_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if chat_id is not None:
        cursor.execute(
            'SELECT * FROM images WHERE chat_id = ? ORDER BY created_at DESC',
            (chat_id,)
        )
    else:
        cursor.execute('SELECT * FROM images ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
