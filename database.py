import sqlite3
import os
from werkzeug.security import generate_password_hash

DATABASE_PATH = os.environ.get('DATABASE_PATH') or os.environ.get('database_path') or os.path.join(os.path.dirname(__file__), 'badminton.db')

# Ensure the directory for the database exists (crucial when using custom paths like Railway volume mounts)
db_dir = os.path.dirname(DATABASE_PATH)
if db_dir and not os.path.exists(db_dir):
    try:
        os.makedirs(db_dir, exist_ok=True)
    except Exception as e:
        print(f"Warning: Could not create directory {db_dir} for database: {e}")

def get_db_connection():
    """
    Establish a thread-safe connection to the SQLite database.
    Enforces foreign keys and returns dictionary-like rows.
    """
    conn = sqlite3.connect(DATABASE_PATH, timeout=10.0) # 10s timeout to handle busy locks under concurrency
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;") # Enable Write-Ahead Logging for high concurrency
    conn.execute("PRAGMA synchronous = NORMAL;") # Optimize disk sync write times while maintaining crash safety
    return conn

def init_db():
    """
    Initializes the database using the schema.sql script.
    Seeds default courts, slots, admin account, and a test user account if they don't exist.
    """
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    
    # Read and execute schema
    with open(schema_path, 'r') as f:
        schema_sql = f.read()
        
    conn = get_db_connection()
    try:
        conn.executescript(schema_sql)
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error during schema execution: {e}")
        raise e

    # Database migration: check if mobile column exists in users table
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        if columns and 'mobile' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN mobile TEXT;")
            cursor.execute("UPDATE users SET mobile = '9876543210' WHERE email = 'admin@tristar.com';")
            cursor.execute("UPDATE users SET mobile = '9876543211' WHERE email = 'user@tristar.com';")
            conn.commit()
            print("Migrated database: added mobile column to users table.")
        
        # Always ensure index is created
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_mobile ON users(mobile);")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_unique_confirmed ON bookings(court_id, slot_id, booking_date) WHERE status = 'confirmed';")
        conn.commit()
    except Exception as e:
        print(f"Migration error: {e}")
    
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
        exists = cursor.execute("SELECT id FROM slots WHERE court_id = ? AND start_time = ? AND end_time = ?", (court_id, "04:00", "05:00")).fetchone()
        if not exists:
            cursor.execute(
                "INSERT INTO slots (court_id, start_time, end_time, default_price) VALUES (?, ?, ?, ?)",
                (court_id, "04:00", "05:00", 50.0)
            )
            conn.commit()
            print("Migrated Database: Added 04:00 - 05:00 slot.")
        
    # 3. Seed Default Accounts
    cursor.execute("SELECT COUNT(*) FROM users")
    users_empty = cursor.fetchone()[0] == 0
    
    # Read admin credentials from environment or fallback
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@tristar.com")
    admin_mobile = os.environ.get("ADMIN_MOBILE", "9876543210")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    
    if not admin_password:
        print("WARNING: ADMIN_PASSWORD environment variable is not set! Defaulting to 'admin123'. PLEASE SET ADMIN_PASSWORD FOR PRODUCTION!")
        admin_password = "admin123"
        
    admin_pw_hash = generate_password_hash(admin_password)

    # Check if admin user already exists
    cursor.execute("SELECT id FROM users WHERE role = 'admin'")
    admin_row = cursor.fetchone()
    
    if not admin_row:
        # Create default admin if users table is empty or admin doesn't exist
        cursor.execute(
            "INSERT INTO users (email, mobile, password_hash, name, role) VALUES (?, ?, ?, ?, ?)",
            (admin_email, admin_mobile, admin_pw_hash, "Academy Admin", "admin")
        )
        conn.commit()
        print(f"Created default admin account: {admin_email}")
    else:
        # Update admin credentials if environment variables changed
        admin_id = admin_row[0]
        cursor.execute(
            "UPDATE users SET email = ?, mobile = ?, password_hash = ? WHERE id = ?",
            (admin_email, admin_mobile, admin_pw_hash, admin_id)
        )
        conn.commit()
        print(f"Synced/updated admin credentials for {admin_email} from environment.")

    # Create default user only if the users table is completely empty
    if users_empty:
        user_email = "user@tristar.com"
        user_mobile = "9876543211"
        user_pw_hash = generate_password_hash("user123")
        cursor.execute(
            "INSERT INTO users (email, mobile, password_hash, name, role) VALUES (?, ?, ?, ?, ?)",
            (user_email, user_mobile, user_pw_hash, "John Doe", "user")
        )
        conn.commit()
        print("Seeded Default User (user@tristar.com).")
        
    conn.close()

def run_auto_backup():
    """
    Perform a daily backup of the database to a 'backups' subdirectory.
    Retains the last 7 daily backups.
    """
    db_dir = os.path.dirname(DATABASE_PATH)
    backup_dir = os.path.join(db_dir, 'backups')
    
    try:
        os.makedirs(backup_dir, exist_ok=True)
    except Exception as e:
        print(f"Error creating backup directory {backup_dir}: {e}")
        return
        
    from datetime import datetime
    today_str = datetime.now().strftime('%Y-%m-%d')
    backup_filename = f"badminton_backup_{today_str}.db"
    backup_path = os.path.join(backup_dir, backup_filename)
    
    if os.path.exists(backup_path):
        return
        
    print(f"Daily backup trigger: '{backup_filename}' does not exist. Starting backup...")
    
    temp_path = backup_path + ".tmp"
    src_conn = None
    dst_conn = None
    try:
        src_conn = get_db_connection()
        dst_conn = sqlite3.connect(temp_path)
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()
        
        os.replace(temp_path, backup_path)
        print(f"Backup saved successfully: {backup_path}")
        
        clean_old_backups(backup_dir, max_backups=7)
    except Exception as e:
        print(f"Error during sqlite3 database backup: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

def clean_old_backups(backup_dir, max_backups=7):
    """Keep only the most recent N backup files."""
    try:
        files = [f for f in os.listdir(backup_dir) if f.startswith("badminton_backup_") and f.endswith(".db")]
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
