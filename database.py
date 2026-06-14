import os
import psycopg2
import datetime
from werkzeug.security import generate_password_hash

# Helper to load .env file locally if present
def load_env_file():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    os.environ[key] = value

load_env_file()

DATABASE_URL = os.environ.get('DATABASE_URL') or os.environ.get('database_url')

class DictRow:
    def __init__(self, cursor, row_tuple):
        self._keys = [desc[0] for desc in cursor.description]
        # Convert any datetime/date objects to string to match SQLite behavior exactly
        self._values = tuple(
            val.strftime('%Y-%m-%d %H:%M:%S') if isinstance(val, datetime.datetime)
            else val.strftime('%Y-%m-%d') if isinstance(val, datetime.date)
            else val for val in row_tuple
        )
        self._dict = dict(zip(self._keys, self._values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._dict[key]

    def keys(self):
        return self._keys

    def __len__(self):
        return len(self._values)

    def __iter__(self):
        return iter(self._values)

    def __repr__(self):
        return f"Row {self._dict}"


class PostgresCursorWrapper:
    def __init__(self, real_cursor):
        self.cursor = real_cursor
        self.lastrowid = None

    def execute(self, query, parameters=None):
        # 1. Ignore SQLite-specific PRAGMAs
        if query.strip().upper().startswith("PRAGMA"):
            return self

        # 2. Ignore SQLite transaction control keywords (since psycopg2 manages transactions implicitly)
        clean_query = query.strip().rstrip(';').upper()
        if clean_query in ("BEGIN IMMEDIATE TRANSACTION", "BEGIN TRANSACTION", "BEGIN"):
            return self

        # 3. Translate query placeholders from '?' to '%s'
        query_processed = query.replace('?', '%s')

        # 4. Handle INSERT lastrowid by appending RETURNING id (unless already returning something)
        is_insert = query_processed.strip().upper().startswith("INSERT")
        if is_insert and "RETURNING" not in query_processed.upper():
            query_processed = query_processed.rstrip().rstrip(';') + " RETURNING id;"
            
            if parameters:
                self.cursor.execute(query_processed, parameters)
            else:
                self.cursor.execute(query_processed)
                
            try:
                row = self.cursor.fetchone()
                if row:
                    self.lastrowid = row[0]
            except Exception:
                self.lastrowid = None
        else:
            if parameters:
                self.cursor.execute(query_processed, parameters)
            else:
                self.cursor.execute(query_processed)
            self.lastrowid = None
            
        return self

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        return DictRow(self.cursor, row)

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [DictRow(self.cursor, r) for r in rows]

    def close(self):
        self.cursor.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __getattr__(self, name):
        return getattr(self.cursor, name)


class PostgresConnectionWrapper:
    def __init__(self, real_conn):
        self.conn = real_conn

    def cursor(self):
        return PostgresCursorWrapper(self.conn.cursor())

    def execute(self, query, parameters=None):
        cursor = self.cursor()
        cursor.execute(query, parameters)
        return cursor

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        self.close()

    def __getattr__(self, name):
        return getattr(self.conn, name)


def get_db_connection():
    """
    Establish a connection to the PostgreSQL database.
    Returns a custom wrapped connection providing SQLite-like API compatibility.
    """
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set!")
    conn = psycopg2.connect(DATABASE_URL)
    return PostgresConnectionWrapper(conn)


def init_db():
    """
    Initializes the database using the schema.sql script.
    Seeds default courts, slots, admin account, and a test user account if they don't exist.
    """
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    
    with open(schema_path, 'r') as f:
        schema_sql = f.read()
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # In psycopg2 we can execute multiple commands separated by semicolons in one execute()
        cursor.execute(schema_sql)
        conn.commit()
        print("Initialized PostgreSQL database tables.")
        
        # Check and apply migrations (add missing columns to existing tables if they already existed)
        def column_exists(c, tbl, col):
            c.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
                );
                """, (tbl, col)
            )
            return c.fetchone()[0]
            
        cursor = conn.cursor()
        
        # 1. users table: mobile
        if not column_exists(cursor, 'users', 'mobile'):
            cursor.execute("ALTER TABLE users ADD COLUMN mobile VARCHAR(50);")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_mobile ON users(mobile);")
            cursor.execute("UPDATE users SET mobile = '9876543210' WHERE email = 'admin@tristar.com';")
            cursor.execute("UPDATE users SET mobile = '9876543211' WHERE email = 'user@tristar.com';")
            conn.commit()
            print("Migration: Added mobile column to users table.")

        # 2. bookings table: cancelled_at
        if not column_exists(cursor, 'bookings', 'cancelled_at'):
            cursor.execute("ALTER TABLE bookings ADD COLUMN cancelled_at VARCHAR(50);")
            conn.commit()
            print("Migration: Added cancelled_at column to bookings table.")

        # 3. memberships table: cancelled_at
        if not column_exists(cursor, 'memberships', 'cancelled_at'):
            cursor.execute("ALTER TABLE memberships ADD COLUMN cancelled_at VARCHAR(50);")
            conn.commit()
            print("Migration: Added cancelled_at column to memberships table.")

        # 4. bookings table: payment_method
        if not column_exists(cursor, 'bookings', 'payment_method'):
            cursor.execute("ALTER TABLE bookings ADD COLUMN payment_method VARCHAR(50) DEFAULT 'online';")
            conn.commit()
            print("Migration: Added payment_method column to bookings table.")
            
        # 5. users table: google_sub
        if not column_exists(cursor, 'users', 'google_sub'):
            cursor.execute("ALTER TABLE users ADD COLUMN google_sub VARCHAR(255);")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub);")
            conn.commit()
            print("Migration: Added google_sub column to users table.")

        # 6. users table: drop NOT NULL constraints
        cursor.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;")
        cursor.execute("ALTER TABLE users ALTER COLUMN mobile DROP NOT NULL;")
        conn.commit()
        print("Migration: Dropped NOT NULL constraints on password_hash and mobile in users table.")
            
    except Exception as e:
        conn.rollback()
        print(f"Error during schema execution: {e}")
        raise e
    
    # Seeding Default Data
    cursor = conn.cursor()
    
    # 1. Seed Court 1
    cursor.execute("SELECT COUNT(*) FROM courts")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO courts (name, description, image_url, is_active) VALUES (?, ?, ?, ?)",
            ("Tristar Premier Court", "Premium synthetic court with professional lighting and non-marking mats.", "/static/images/court1.jpg", 1)
        )
        conn.commit()
        print("Seeded Default Court 1.")
        
    # Get Court 1 ID
    cursor.execute("SELECT id FROM courts WHERE name = ?", ("Tristar Premier Court",))
    court_id = cursor.fetchone()[0]
    
    # 2. Seed Slots (06:00 to 22:00 hourly)
    cursor.execute("SELECT COUNT(*) FROM slots WHERE court_id = ?", (court_id,))
    if cursor.fetchone()[0] == 0:
        hourly_slots = [
            ("04:00", "05:00", 50.0),
            ("05:00", "06:00", 50.0),
            ("06:00", "07:00", 50.0),
            ("07:00", "08:00", 50.0),
            ("08:00", "09:00", 50.0),
            ("09:00", "10:00", 50.0),
            ("10:00", "11:00", 50.0),
            ("11:00", "12:00", 50.0),
            ("12:00", "13:00", 50.0),
            ("13:00", "14:00", 50.0),
            ("14:00", "15:00", 50.0),
            ("15:00", "16:00", 50.0),
            ("16:00", "17:00", 50.0),
            ("17:00", "18:00", 50.0),
            ("18:00", "19:00", 50.0),
            ("19:00", "20:00", 50.0),
            ("20:00", "21:00", 50.0),
            ("21:00", "22:00", 50.0),
            ("22:00", "23:00", 50.0)
        ]
        
        for start, end, price in hourly_slots:
            cursor.execute(
                "INSERT INTO slots (court_id, start_time, end_time, default_price) VALUES (?, ?, ?, ?)",
                (court_id, start, end, price)
            )
        conn.commit()
        print("Seeded Default Slots for Court 1.")
    else:
        # Migration check: make sure 04:00 - 05:00 slot exists
        cursor.execute("SELECT id FROM slots WHERE court_id = ? AND start_time = ? AND end_time = ?", (court_id, "04:00", "05:00"))
        exists = cursor.fetchone()
        if not exists:
            cursor.execute(
                "INSERT INTO slots (court_id, start_time, end_time, default_price) VALUES (?, ?, ?, ?)",
                (court_id, "04:00", "05:00", 50.0)
            )
            conn.commit()
            print("Added 04:00 - 05:00 slot.")
        
    # Seeding Default Accounts
    cursor.execute("SELECT COUNT(*) FROM users")
    
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@tristar.com")
    admin_mobile = os.environ.get("ADMIN_MOBILE", "9876543210")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    
    if not admin_password:
        print("WARNING: ADMIN_PASSWORD environment variable is not set! Defaulting to 'admin123'.")
        admin_password = "admin123"
        
    admin_pw_hash = generate_password_hash(admin_password)

    cursor.execute("SELECT id FROM users WHERE role = 'admin'")
    admin_row = cursor.fetchone()
    
    if not admin_row:
        cursor.execute(
            "INSERT INTO users (email, mobile, password_hash, name, role) VALUES (?, ?, ?, ?, 'admin')",
            (admin_email, admin_mobile, admin_pw_hash, "Academy Admin")
        )
        conn.commit()
        print(f"Created default admin account: {admin_email}")
    else:
        admin_id = admin_row[0]
        cursor.execute(
            "UPDATE users SET email = ?, mobile = ?, password_hash = ? WHERE id = ?",
            (admin_email, admin_mobile, admin_pw_hash, admin_id)
        )
        conn.commit()
        print(f"Synced/updated admin credentials for {admin_email} from environment.")
        
    conn.close()


def run_auto_backup():
    """
    Perform a daily backup of the database. Generates a self-contained SQL file
    containing schema truncate statements and row insertions to be independent of pg_dump.
    Retains the last 7 backups.
    """
    db_dir = os.path.dirname(__file__)
    backup_dir = os.path.join(db_dir, 'backups')
    
    try:
        os.makedirs(backup_dir, exist_ok=True)
    except Exception as e:
        print(f"Error creating backup directory {backup_dir}: {e}")
        return
        
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    backup_filename = f"badminton_backup_{today_str}.sql"
    backup_path = os.path.join(backup_dir, backup_filename)
    
    if os.path.exists(backup_path):
        return
        
    print(f"Daily backup trigger: '{backup_filename}' does not exist. Starting backup...")
    
    temp_path = backup_path + ".tmp"
    try:
        tables = ['users', 'courts', 'slots', 'bookings', 'pricing_overrides', 'slot_blocks', 'queries', 'memberships']
        conn = get_db_connection()
        
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write("-- Badminton PostgreSQL Backup\n")
            f.write(f"-- Created: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Disable foreign key and trigger checks to allow clean table truncation/inserts
            f.write("SET session_replication_role = 'replica';\n\n")
            
            cursor = conn.cursor()
            for table in tables:
                # Check if table exists in public schema
                cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s);", (table,))
                if not cursor.fetchone()[0]:
                    continue
                    
                f.write(f"-- Table: {table}\n")
                f.write(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;\n")
                
                # Fetch columns
                cursor.execute(f"SELECT * FROM {table} LIMIT 0;")
                columns = [desc[0] for desc in cursor.description]
                
                # Fetch data
                cursor.execute(f"SELECT * FROM {table};")
                rows = cursor.fetchall()
                
                if rows:
                    col_names = ", ".join(columns)
                    f.write(f"INSERT INTO {table} ({col_names}) VALUES\n")
                    
                    value_strs = []
                    for row in rows:
                        row_vals = []
                        for val in row:
                            if val is None:
                                row_vals.append("NULL")
                            elif isinstance(val, (int, float)):
                                row_vals.append(str(val))
                            elif isinstance(val, bool):
                                row_vals.append("TRUE" if val else "FALSE")
                            else:
                                escaped_val = str(val).replace("'", "''")
                                row_vals.append(f"'{escaped_val}'")
                        value_strs.append(f"({', '.join(row_vals)})")
                    
                    f.write(",\n".join(value_strs) + ";\n")
                f.write("\n")
                
            f.write("SET session_replication_role = 'origin';\n")
            
        conn.close()
        os.replace(temp_path, backup_path)
        print(f"Backup saved successfully: {backup_path}")
        
        clean_old_backups(backup_dir, max_backups=7)
    except Exception as e:
        print(f"Error during database backup: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def clean_old_backups(backup_dir, max_backups=7):
    """Keep only the most recent N backup files."""
    try:
        files = [f for f in os.listdir(backup_dir) if f.startswith("badminton_backup_") and f.endswith(".sql")]
        files.sort()
        
        if len(files) > max_backups:
            to_delete = files[:-max_backups]
            for f in to_delete:
                path = os.path.join(backup_dir, f)
                try:
                    os.remove(path)
                    print(f"Backup retention policy: Deleted old backup {f}")
                except Exception as ex:
                    print(f"Error deleting old backup {f}: {ex}")
    except Exception as e:
        print(f"Error applying backup retention: {e}")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'backup':
        run_auto_backup()
    else:
        init_db()
