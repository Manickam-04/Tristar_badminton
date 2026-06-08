import os
import shutil
import sys
import sqlite3
import database

def list_backups(backup_dir):
    if not os.path.exists(backup_dir):
        return []
    return sorted(
        [f for f in os.listdir(backup_dir) if f.startswith("badminton_backup_") and f.endswith(".db")],
        reverse=True
    )

def main():
    db_path = database.DATABASE_PATH
    db_dir = os.path.dirname(db_path)
    backup_dir = os.path.join(db_dir, 'backups')
    
    print("=== Badminton Database Restore Tool ===")
    print(f"Active database path: {db_path}")
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
        
    # Overwrite active database file
    try:
        print("Verifying backup integrity...")
        # Check if backup file is a valid sqlite db
        temp_conn = sqlite3.connect(backup_path)
        temp_conn.execute("PRAGMA integrity_check;")
        temp_conn.close()
        
        print("Copying backup to active database file...")
        # Make a backup of the current database just in case before overwriting
        if os.path.exists(db_path):
            pre_restore_backup = db_path + ".pre_restore_bak"
            shutil.copy2(db_path, pre_restore_backup)
            print(f"Saved pre-restore backup of the current active database to: {os.path.basename(pre_restore_backup)}")
            
        shutil.copy2(backup_path, db_path)
        
        # If WAL journal mode exists, we should delete WAL files to ensure clean start
        wal_path = db_path + "-wal"
        shm_path = db_path + "-shm"
        if os.path.exists(wal_path):
            try:
                os.remove(wal_path)
            except Exception:
                pass
        if os.path.exists(shm_path):
            try:
                os.remove(shm_path)
            except Exception:
                pass
            
        print("Database restore completed successfully!")
    except Exception as e:
        print(f"Error during restore: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
