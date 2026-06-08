# 🚀 PythonAnywhere Deployment Guide

This guide provides step-by-step instructions for deploying your **Tristar Badminton Academy** application on **[PythonAnywhere](https://www.pythonanywhere.com/)**.

PythonAnywhere natively supports persistent file storage in your home directory, making it a great host for lightweight Flask applications utilizing **SQLite** databases.

---

## 🛠️ Step 1: Upload Your Code to GitHub

Before deploying, ensure all latest changes are committed and pushed to your GitHub repository:

1. Open your terminal in the project directory.
2. Stage and commit the files:
   ```bash
   git add app.py database.py restore.py requirements.txt static/ templates/ schema.sql
   git commit -m "Configure application for PythonAnywhere hosting and backups"
   git push origin main
   ```

---

## ☁️ Step 2: Clone the Project on PythonAnywhere

1. Log into your **[PythonAnywhere](https://www.pythonanywhere.com/)** account.
2. Open a **Bash Console** from your dashboard.
3. Clone your GitHub repository:
   ```bash
   git clone https://github.com/Manickam-04/Tristar_badminton.git
   ```
   *(This will clone the code into `/home/manick33/Tristar_badminton/`)*.
   *(Note: Your PythonAnywhere username is `manick33`)*.

---

## 📦 Step 3: Set Up a Virtual Environment & Dependencies

From the same **Bash Console** in PythonAnywhere, configure your environment:

1. Create a virtual environment using Python 3.10 (recommended):
   ```bash
   mkvirtualenv tristar-env --python=python3.10
   ```
   *(This creates and activates a virtual environment located at `/home/manick33/.virtualenvs/tristar-env`)*.
2. Install the application dependencies:
   ```bash
   pip install -r /home/manick33/Tristar_badminton/requirements.txt
   ```

---

## ⚙️ Step 4: Configure Web App & WSGI File

1. Go to the **Web** tab on the PythonAnywhere dashboard and click **Add a new web app**.
2. When prompted:
   - Select **Manual configuration** (do NOT choose the default Flask template—manual configuration is required for custom structures).
   - Select **Python 3.10**.
3. Under the **Virtualenv** section on the Web tab, enter the path to the environment you created:
   `/home/manick33/.virtualenvs/tristar-env`
4. Under the **Code** section, locate the link to your **WSGI configuration file** (it looks like `/var/www/manick33_pythonanywhere_com_wsgi.py`). Click to edit it.
5. Replace the entire contents of the WSGI file with the following script:

```python
import os
import sys

# 1. Add project path to python system paths
project_home = '/home/manick33/Tristar_badminton'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# 2. Inject environment variables for database path, sessions, and credentials
os.environ['DATABASE_PATH'] = '/home/manick33/Tristar_badminton/badminton.db'
os.environ['SECRET_KEY'] = 'hxkyfjmpwqydg304567_tristar_key'  # Custom secure session key
os.environ['FLASK_DEBUG'] = 'False'
os.environ['ADMIN_EMAIL'] = 'admin@tristar.com'
os.environ['ADMIN_PASSWORD'] = 'Tristar@admin11'  # Will automatically sync/seed on startup

# 3. Import and run Flask app object
from app import app as application
```

6. Click **Save**, return to the **Web** tab, and click the green **Reload** button at the top to boot up the web server.

---

## 🔄 Daily Database Backups on PythonAnywhere

Since SQLite databases are stored on PythonAnywhere's persistent disk, we want to perform regular daily backups to protect against database corruption.

### 💾 1. Setting Up Daily Automated Backups
Instead of running a daemon thread (which PythonAnywhere might freeze during periods of inactivity), we utilize PythonAnywhere's **Scheduled Tasks** feature:

1. Navigate to the **Tasks** tab on your PythonAnywhere dashboard.
2. Under **Scheduled Tasks**, set the following configuration:
   - **Time**: Select a daily time (e.g., `02:00` AM UTC).
   - **Command**: Enter the absolute path to your virtual environment's python interpreter and call the database backup command:
     ```bash
     /home/manick33/.virtualenvs/tristar-env/bin/python /home/manick33/Tristar_badminton/database.py backup
     ```
3. Click **Create**. This cron task will run daily, creating copies in `/home/manick33/Tristar_badminton/backups/` and enforcing a 7-day retention limit automatically.

---

## 🛠️ 2. Disaster Recovery Procedure (If Database Corruption Occurs)

If your active database file becomes corrupted or you need to roll back to a previous backup state:

1. Open a **Bash Console** from your PythonAnywhere dashboard.
2. Activate your virtual environment and run the interactive recovery script:
   ```bash
   workon tristar-env
   cd /home/manick33/Tristar_badminton/
   python restore.py
   ```
3. The restore utility will scan your `/backups/` directory and list available snapshots (sorted chronologically).
4. Enter the index number of the backup you wish to restore.
5. Confirm by typing `YES` and hitting Enter.
6. The script will perform a self-integrity validation check on the backup file, copy it onto the active `badminton.db` file, and create a safeguard copy of the pre-restored state (`badminton.db.pre_restore_bak`).
7. Go to the **Web** tab on the PythonAnywhere dashboard and click **Reload** to clear any cached database pools.

---

## 🧹 3. Reset Database (Wipe Clean)
> [!WARNING]
> This command will permanently delete all active user accounts, booking histories, support queries, and backup logs.
1. Open a **Bash Console**.
2. Delete the active database and backup files:
   ```bash
   rm /home/manick33/Tristar_badminton/badminton.db
   rm -rf /home/manick33/Tristar_badminton/backups/
   ```
3. Initialize the database schema completely fresh:
   ```bash
   workon tristar-env
   python /home/manick33/Tristar_badminton/database.py
   ```

---

## 💡 Troubleshooting on PythonAnywhere

* **Checking Server Logs**: If you get a "500 Internal Server Error", look at the **Error Log** linked at the bottom of the Web tab. This displays standard python stack traces for errors occurring inside `app.py`.
* **Static Files not rendering**: By default, uWSGI serves static files efficiently. If styling or images fail to render, configure PythonAnywhere to serve them directly:
  - Go to the **Web** tab.
  - Scroll down to the **Static files** section.
  - Add a path entry:
    - **URL**: `/static/`
    - **Directory**: `/home/manick33/Tristar_badminton/static`
  - Reload the web app.
