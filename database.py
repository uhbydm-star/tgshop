import sqlite3
import time

def get_connection():
    conn = sqlite3.connect('shop.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # 1. ТАБЛИЦА ПОЛЬЗОВАТЕЛЕЙ
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)''')
    c.execute("PRAGMA table_info(users)")
    user_cols = [row['name'] for row in c.fetchall()]
    if 'username' not in user_cols: c.execute("ALTER TABLE users ADD COLUMN username TEXT")
    if 'balance' not in user_cols: c.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0")
    if 'purchases' not in user_cols: c.execute("ALTER TABLE users ADD COLUMN purchases INTEGER DEFAULT 0")
    if 'spent' not in user_cols: c.execute("ALTER TABLE users ADD COLUMN spent REAL DEFAULT 0")
    if 'is_blocked' not in user_cols: c.execute("ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0")
    if 'notifications' not in user_cols: c.execute("ALTER TABLE users ADD COLUMN notifications INTEGER DEFAULT 1")
    if 'accepted_offer' not in user_cols: c.execute("ALTER TABLE users ADD COLUMN accepted_offer INTEGER DEFAULT 0")

    # 2. ПРОМОКОДЫ (Безопасная миграция с UNIQUE)
    c.execute('''CREATE TABLE IF NOT EXISTS promocodes (id INTEGER PRIMARY KEY AUTOINCREMENT)''')
    c.execute("PRAGMA table_info(promocodes)")
    promo_cols = [row['name'] for row in c.fetchall()]
    
    # Если таблицы старого формата, пересоздаем ее правильно
    if 'code' not in promo_cols or 'promo_type' not in promo_cols:
        # Создаем временную правильную таблицу
        c.execute('''CREATE TABLE IF NOT EXISTS promocodes_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code TEXT UNIQUE,
                        promo_type TEXT DEFAULT 'disc_fix',
                        discount REAL,
                        uses_left INTEGER)''')
        
        # Если в старой таблице были данные (discount, uses_left), пытаемся их спасти. 
        # Если там не было колонки code, то старые данные бесполезны, поэтому мы просто удаляем старую таблицу.
        c.execute("DROP TABLE promocodes")
        c.execute("ALTER TABLE promocodes_new RENAME TO promocodes")
        
        # Снова получаем колонки новой таблицы для проверки
        c.execute("PRAGMA table_info(promocodes)")
        promo_cols = [row['name'] for row in c.fetchall()]

    # Авто-миграция старых типов промокодов (если они были)
    try:
        c.execute("UPDATE promocodes SET promo_type = 'disc_fix' WHERE promo_type = 'discount'")
        c.execute("UPDATE promocodes SET promo_type = 'bal_fix' WHERE promo_type = 'balance'")
    except Exception:
        pass # Игнорируем ошибки, если колонки еще не было

    # 3. КАТЕГОРИИ
    c.execute('''CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)''')
    c.execute("PRAGMA table_info(categories)")
    cat_cols = [row['name'] for row in c.fetchall()]
    if 'emoji_id' not in cat_cols: c.execute("ALTER TABLE categories ADD COLUMN emoji_id TEXT")

    # 4. ТОВАРЫ
    c.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, name TEXT, description TEXT, price REAL)''')
    c.execute("PRAGMA table_info(products)")
    prod_cols = [row['name'] for row in c.fetchall()]
    if 'emoji_id' not in prod_cols: c.execute("ALTER TABLE products ADD COLUMN emoji_id TEXT")
    if 'is_infinite' not in prod_cols: c.execute("ALTER TABLE products ADD COLUMN is_infinite INTEGER DEFAULT 0")
    if 'infinite_content' not in prod_cols: c.execute("ALTER TABLE products ADD COLUMN infinite_content TEXT")
    if 'infinite_content_type' not in prod_cols: c.execute("ALTER TABLE products ADD COLUMN infinite_content_type TEXT DEFAULT 'text'")

    # 5. НАСТРОЙКИ UI
    c.execute('''CREATE TABLE IF NOT EXISTS ui_settings (key TEXT PRIMARY KEY, emoji_id TEXT)''')
    defaults = {
        'E_CATALOG': '5368324170671202286', 'E_PROFILE': '5368324170671202286',
        'E_DEPOSIT': '5368324170671202286', 'E_SUPPORT': '5368324170671202286',
        'E_ABOUT': '5368324170671202286', 'E_SUCCESS': '5368324170671202286',
        'E_DANGER': '5368324170671202286', 'E_BACK': '5368324170671202286',
        'E_DEFAULT': '5368324170671202286'
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO ui_settings (key, emoji_id) VALUES (?, ?)", (k, v))

    # 6. СКЛАД ТОВАРОВ
    c.execute('''CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, content TEXT)''')
    c.execute("PRAGMA table_info(items)")
    item_cols = [row['name'] for row in c.fetchall()]
    if 'content_type' not in item_cols: c.execute("ALTER TABLE items ADD COLUMN content_type TEXT DEFAULT 'text'")

    # 7. ЗАКАЗЫ И ПОПОЛНЕНИЯ
    c.execute('''CREATE TABLE IF NOT EXISTS used_promos (user_id INTEGER, promo_id INTEGER, PRIMARY KEY (user_id, promo_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS giveaways (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, target_val REAL, end_time INTEGER, winners_count INTEGER, prize_type TEXT, prize_value REAL, is_active INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS giveaway_participants (giveaway_id INTEGER, user_id INTEGER, UNIQUE(giveaway_id, user_id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_name TEXT, price REAL, content TEXT, date_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute("PRAGMA table_info(orders)")
    order_cols = [row['name'] for row in c.fetchall()]
    if 'content_type' not in order_cols: c.execute("ALTER TABLE orders ADD COLUMN content_type TEXT DEFAULT 'text'")
    
    c.execute('''CREATE TABLE IF NOT EXISTS deposit_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, method TEXT, date_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    conn.commit()
    conn.close()

# --- СТАТИСТИКА АДМИНА ---
def get_statistics():
    conn = get_connection()
    c = conn.cursor()
    stats = {}
    for days in [7, 15, 30]:
        c.execute(f"SELECT SUM(amount) as total FROM deposit_history WHERE date_time >= datetime('now', '-{days} days')")
        dep_total = c.fetchone()['total'] or 0
        c.execute(f"SELECT SUM(price) as total FROM orders WHERE date_time >= datetime('now', '-{days} days')")
        ord_total = c.fetchone()['total'] or 0
        stats[days] = {'deposits': round(dep_total, 2), 'orders': round(ord_total, 2)}
    c.execute("SELECT COUNT(id) as count FROM users")
    stats['users'] = c.fetchone()['count'] or 0
    conn.close()
    return stats

# --- UI ЭМОДЗИ ---
def get_ui():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, emoji_id FROM ui_settings")
    ui = {row['key']: row['emoji_id'] for row in c.fetchall()}
    conn.close()
    return ui

def set_ui(key, emoji_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE ui_settings SET emoji_id = ? WHERE key = ?", (emoji_id, key))
    conn.commit()
    conn.close()

# --- Пользователи ---
def add_user(user_id, username):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

def get_user(user_id=None, username=None):
    conn = get_connection()
    c = conn.cursor()
    if user_id: c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    elif username: c.execute("SELECT * FROM users WHERE username = ?", (username.replace('@', ''),))
    user = c.fetchone()
    conn.close()
    return dict(user) if user else None

def accept_offer(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET accepted_offer = 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

def toggle_notifications(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT notifications FROM users WHERE id = ?", (user_id,))
    new_status = 0 if c.fetchone()['notifications'] == 1 else 1
    c.execute("UPDATE users SET notifications = ? WHERE id = ?", (new_status, user_id))
    conn.commit()
    conn.close()
    return new_status

def update_balance(user_id, amount):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def process_deposit(user_id, amount, method="СБП", promo_id=None):
    conn = get_connection()
    c = conn.cursor()
    
    bonus = 0
    if promo_id and promo_id > 0:
        c.execute("SELECT * FROM promocodes WHERE id = ?", (promo_id,))
        promo = c.fetchone()
        if promo and promo['uses_left'] > 0 and promo['promo_type'] == 'dep_perc':
            c.execute("SELECT 1 FROM used_promos WHERE user_id = ? AND promo_id = ?", (user_id, promo_id))
            if not c.fetchone():
                bonus = amount * (promo['discount'] / 100.0)
                c.execute("UPDATE promocodes SET uses_left = uses_left - 1 WHERE id = ?", (promo_id,))
                c.execute("INSERT INTO used_promos (user_id, promo_id) VALUES (?, ?)", (user_id, promo_id))
                
    total_add = amount + bonus
    c.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (total_add, user_id))
    c.execute("INSERT INTO deposit_history (user_id, amount, method) VALUES (?, ?, ?)", (user_id, amount, method))
    
    c.execute("SELECT id FROM giveaways WHERE type='deposit' AND is_active=1 AND target_val <= ?", (amount,))
    for ga in c.fetchall():
        c.execute("INSERT OR IGNORE INTO giveaway_participants (giveaway_id, user_id) VALUES (?, ?)", (ga['id'], user_id))
        
    conn.commit()
    conn.close()
    return total_add, bonus

def get_user_deposits(user_id, limit=5):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT amount, method, datetime(date_time, 'localtime') as dt FROM deposit_history WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    deps = [dict(row) for row in c.fetchall()]
    conn.close()
    return deps

def get_user_orders(user_id, limit=5):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT product_name, price, content, content_type, datetime(date_time, 'localtime') as dt FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    orders = [dict(row) for row in c.fetchall()]
    conn.close()
    return orders

def set_block_status(user_id, status: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET is_blocked = ? WHERE id = ?", (status, user_id))
    conn.commit()
    conn.close()

# --- Категории ---
def add_category(name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO categories (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()

def get_categories():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM categories")
    cats = [dict(row) for row in c.fetchall()]
    conn.close()
    return cats

def get_category(category_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM categories WHERE id = ?", (category_id,))
    cat = c.fetchone()
    conn.close()
    return dict(cat) if cat else None

def update_category_emoji(category_id, emoji_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE categories SET emoji_id = ? WHERE id = ?", (emoji_id, category_id))
    conn.commit()
    conn.close()

def delete_category(category_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    c.execute("SELECT id FROM products WHERE category_id = ?", (category_id,))
    for p in c.fetchall():
        c.execute("DELETE FROM items WHERE product_id = ?", (p['id'],))
    c.execute("DELETE FROM products WHERE category_id = ?", (category_id,))
    conn.commit()
    conn.close()

# --- Товары ---
def add_product(category_id, name, description, price):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO products (category_id, name, description, price) VALUES (?, ?, ?, ?)", (category_id, name, description, price))
    conn.commit()
    conn.close()

def get_products(category_id=None):
    conn = get_connection()
    c = conn.cursor()
    if category_id:
        c.execute("SELECT p.*, (SELECT COUNT(*) FROM items WHERE product_id = p.id) as stock FROM products p WHERE category_id = ?", (category_id,))
    else:
        c.execute("SELECT p.*, (SELECT COUNT(*) FROM items WHERE product_id = p.id) as stock FROM products p")
    prods = [dict(row) for row in c.fetchall()]
    conn.close()
    return prods

def get_product(product_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT p.*, (SELECT COUNT(*) FROM items WHERE product_id = p.id) as stock FROM products p WHERE id = ?", (product_id,))
    prod = c.fetchone()
    conn.close()
    return dict(prod) if prod else None

def update_product_field(product_id, field, value):
    conn = get_connection()
    c = conn.cursor()
    if field in ['name', 'description', 'price', 'emoji_id', 'is_infinite', 'infinite_content', 'infinite_content_type']:
        c.execute(f"UPDATE products SET {field} = ? WHERE id = ?", (value, product_id))
        conn.commit()
    conn.close()

def toggle_product_infinite(product_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT is_infinite FROM products WHERE id = ?", (product_id,))
    new_val = 0 if c.fetchone()['is_infinite'] == 1 else 1
    c.execute("UPDATE products SET is_infinite = ? WHERE id = ?", (new_val, product_id))
    conn.commit()
    conn.close()
    return new_val

def delete_product(product_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ?", (product_id,))
    c.execute("DELETE FROM items WHERE product_id = ?", (product_id,))
    conn.commit()
    conn.close()

def add_item(product_id, content, content_type='text'):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO items (product_id, content, content_type) VALUES (?, ?, ?)", (product_id, content, content_type))
    conn.commit()
    conn.close()

def buy_item(user_id, product_id, promo_id=None):
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    prod = c.fetchone()
    if not prod: return False, "Товар не найден.", None, [], 0, 0
        
    price = prod['price']
    final_price = price
    
    promo_data = None
    if promo_id and promo_id > 0:
        c.execute("SELECT * FROM promocodes WHERE id = ?", (promo_id,))
        promo_data = c.fetchone()
        if promo_data and promo_data['uses_left'] > 0:
            if promo_data['promo_type'] == 'disc_fix':
                final_price = max(0, price - promo_data['discount'])
            elif promo_data['promo_type'] == 'disc_perc':
                final_price = max(0, price - (price * (promo_data['discount'] / 100.0)))
    
    c.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    if c.fetchone()['balance'] < final_price:
        conn.close()
        return False, f"Недостаточно средств. Цена: {final_price} руб.", None, [], 0, 0
    
    item_content = ""
    item_content_type = "text"

    if prod['is_infinite']:
        if not prod['infinite_content']:
            conn.close()
            return False, "Содержимое не настроено администратором.", None, [], 0, 0
        item_content = prod['infinite_content']
        item_content_type = prod['infinite_content_type']
    else:
        c.execute("SELECT id, content, content_type FROM items WHERE product_id = ? LIMIT 1", (product_id,))
        item = c.fetchone()
        if not item:
            conn.close()
            return False, "Товар закончился.", None, [], 0, 0
        item_content = item['content']
        item_content_type = item['content_type']
        c.execute("DELETE FROM items WHERE id = ?", (item['id'],))
    
    c.execute("UPDATE users SET balance = balance - ?, purchases = purchases + 1, spent = spent + ? WHERE id = ?", (final_price, final_price, user_id))
    
    c.execute("INSERT INTO orders (user_id, product_name, price, content, content_type) VALUES (?, ?, ?, ?, ?)", (user_id, prod['name'], final_price, item_content, item_content_type))
    order_id = c.lastrowid

    if promo_data:
        c.execute("UPDATE promocodes SET uses_left = uses_left - 1 WHERE id = ?", (promo_data['id'],))
        c.execute("INSERT INTO used_promos (user_id, promo_id) VALUES (?, ?)", (user_id, promo_data['id']))
    
    immediate_wins = []
    c.execute("SELECT * FROM giveaways WHERE type='first_buy' AND is_active=1 AND target_val=?", (product_id,))
    first_buy_ga = c.fetchone()
    if first_buy_ga:
        if first_buy_ga['prize_type'] == 'balance':
            c.execute("UPDATE users SET balance = balance + ? WHERE id=?", (first_buy_ga['prize_value'], user_id))
        c.execute("UPDATE giveaways SET is_active=0 WHERE id=?", (first_buy_ga['id'],))
        immediate_wins.append(dict(first_buy_ga))

    c.execute("SELECT id FROM giveaways WHERE type='product' AND is_active=1 AND target_val=?", (product_id,))
    for ga in c.fetchall():
        c.execute("INSERT OR IGNORE INTO giveaway_participants (giveaway_id, user_id) VALUES (?, ?)", (ga['id'], user_id))

    conn.commit()
    conn.close()
    return True, item_content, item_content_type, immediate_wins, final_price, order_id

# --- ПРОМОКОДЫ ---
def add_promocode(code, promo_type, discount, uses):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO promocodes (code, promo_type, discount, uses_left) VALUES (?, ?, ?, ?)", (code, promo_type, discount, uses))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def get_promocodes():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM promocodes")
    codes = [dict(row) for row in c.fetchall()]
    conn.close()
    return codes

def delete_promocode(promo_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM promocodes WHERE id = ?", (promo_id,))
    c.execute("DELETE FROM used_promos WHERE promo_id = ?", (promo_id,)) 
    conn.commit()
    conn.close()

def check_promocode(user_id, code, context='purchase', amount=0):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM promocodes WHERE code = ?", (code,))
    promo = c.fetchone()
    if not promo:
        conn.close()
        return False, 0, "Промокод не найден или введен неверно.", 0
    if promo['uses_left'] <= 0:
        conn.close()
        return False, 0, "Количество активаций этого промокода закончилось.", 0
    
    pt = promo['promo_type']
    val = 0
    if context == 'profile':
        if pt != 'bal_fix':
            conn.close()
            return False, 0, "Этот промокод вводится при покупке или пополнении.", 0
        val = promo['discount']
        
    elif context == 'purchase':
        if pt not in ['disc_fix', 'disc_perc']:
            conn.close()
            return False, 0, "Этот промокод не для скидки на товар.", 0
        val = promo['discount'] if pt == 'disc_fix' else amount * (promo['discount'] / 100.0)
        
    elif context == 'deposit':
        if pt != 'dep_perc':
            conn.close()
            return False, 0, "Этот промокод не является бонусом к пополнению.", 0
        val = amount * (promo['discount'] / 100.0)
    
    c.execute("SELECT 1 FROM used_promos WHERE user_id = ? AND promo_id = ?", (user_id, promo['id']))
    if c.fetchone():
        conn.close()
        return False, 0, "Вы уже использовали этот промокод ранее.", 0
        
    conn.close()
    return True, round(val, 2), "", promo['id']

def use_balance_promocode(user_id, code):
    success, val, err, promo_id = check_promocode(user_id, code, context='profile')
    if not success: return False, err
    
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE promocodes SET uses_left = uses_left - 1 WHERE id = ?", (promo_id,))
    c.execute("INSERT INTO used_promos (user_id, promo_id) VALUES (?, ?)", (user_id, promo_id))
    c.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (val, user_id))
    conn.commit()
    conn.close()
    return True, val

# --- РОЗЫГРЫШИ ---
def create_giveaway(ga_type, target_val, end_time, winners_count, prize_type, prize_value):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO giveaways (type, target_val, end_time, winners_count, prize_type, prize_value)
                 VALUES (?, ?, ?, ?, ?, ?)''', (ga_type, target_val, end_time, winners_count, prize_type, prize_value))
    conn.commit()
    conn.close()

def get_active_giveaways():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM giveaways WHERE is_active=1")
    gas = [dict(row) for row in c.fetchall()]
    conn.close()
    return gas

def get_ended_giveaways(current_timestamp):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM giveaways WHERE is_active=1 AND type != 'first_buy' AND end_time <= ?", (current_timestamp,))
    gas = [dict(row) for row in c.fetchall()]
    conn.close()
    return gas

def finish_giveaway(ga_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE giveaways SET is_active=0 WHERE id=?", (ga_id,))
    conn.commit()
    conn.close()

def get_giveaway_participants(ga_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM giveaway_participants WHERE giveaway_id=?", (ga_id,))
    parts = [dict(row) for row in c.fetchall()]
    conn.close()
    return parts