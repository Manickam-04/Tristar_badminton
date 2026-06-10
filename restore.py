import os
import sys
import psycopg2
import database

def list_backups(backup_dir):
    if not os.path.exists(backup_dir):
        return []
    return sorted(
        [f for f in os.listdir(backup_dir) if f.startswith("badminton_backup_") and f.endswith(".sql")],
        reverse=True
    )

def main():
    if not database.DATABASE_URL:
        print("Error: DATABASE_URL environment variable is not set!")
        sys.exit(1)
        
    db_dir = os.path.dirname(__file__)
    backup_dir = os.path.join(db_dir, 'backups')
    
    print("=== Badminton Database Restore Tool (PostgreSQL) ===")
    print(f"Target Database URL: {database.DATABASE_URL[:30]}...")
    print(f"Backup directory: {backup_dir}")
    
    backups = list_backups(backup_dir)
    if not backups:
        print("Error: No backups found in the backup directory.")
        sys.exit(1)
        
    print("\nAvailable backups (newest first):")
    for idx, b in enumerate(backups):
        b_path = os.path.join(backup_dir, b)
        size_kb = os.path.getsize(b_path) / 1024
        print(f"[{idx}] {b} ({size_kb:.2f} KB)")
        
    if len(sys.argv) > 1:
        choice_str = sys.argv[1]
    else:
        try:
            choice_str = input("\nSelect a backup index to restore (or 'q' to quit): ").strip()
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            sys.exit(0)
            
    if choice_str.lower() == 'q':
        print("Operation cancelled.")
        sys.exit(0)
        
    try:
        choice_idx = int(choice_str)
        if choice_idx < 0 or choice_idx >= len(backups):
            raise ValueError
    except ValueError:
        print("Invalid selection.")
        sys.exit(1)
        
    selected_backup = backups[choice_idx]
    backup_path = os.path.join(backup_dir, selected_backup)
    
    print(f"\nCRITICAL: You are about to overwrite the active database with:\n{selected_backup}")
    try:
        confirm = input("Are you sure? This will overwrite the current live database. Type 'YES' to confirm: ")
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        sys.exit(0)
        
    if confirm != 'YES':
        print("Confirmation failed. Restore cancelled.")
        sys.exit(0)
        
    # Read backup file content
    try:
        print("Reading backup file...")
        with open(backup_path, 'r', encoding='utf-8') as f:
            sql_script = f.read()
    except Exception as e:
        print(f"Error reading backup file: {e}")
        sys.exit(1)
        
    # Execute restore script in a transaction
    try:
        print("Connecting to database and executing restore script...")
        # Get standard raw psycopg2 connection to run restore directly
        conn = psycopg2.connect(database.DATABASE_URL)
        cursor = conn.cursor()
        
        # Execute the entire script
        cursor.execute(sql_script)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("\nDatabase restore completed successfully!")
    except Exception as e:
        print(f"\nError during restore execution: {e}")
        print("Transaction has been rolled back. Database remains in its previous state.")
        sys.exit(1)

if __name__ == '__main__':
    main()
