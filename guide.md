# Tristar Badminton Academy - Developer & Operator Guide

Welcome to your **Badminton Slot Booking Application**! This web application is built using a modern, lightweight, mobile-first tech stack: **HTML5**, **CSS3 (Vanilla)**, **JavaScript (ES6)**, **Python (Flask)**, and **SQL (SQLite)**.

This guide provides a comprehensive walkthrough of the application architecture, database design, operational routines, and clear instructions on how to run, customize, and extend the code.

---

## 1. Directory Structure

Here is an overview of the code files in your workspace:

```
badminton_app/
│
├── app.py                         # Main Flask server with API endpoints & session routing
├── database.py                    # SQLite connection pool and automatic database seeding
├── schema.sql                     # Full database DDL definitions
├── guide.md                       # Core developer & operator guide (this file)
├── developer_customization_guide.md # Code level details for customizing memberships & slots
├── deployment_guide.md            # Railway hosting, volumes, & backup configuration
├── restore.py                     # Disaster recovery script for restoring database backups
│
├── static/
│   ├── css/
│   │   └── style.css              # Core premium design system, animations, & glassmorphism
│   └── js/
│       ├── main.js                # Dynamic customer calendar, slot checker, & booking modals
│       └── admin.js               # Admin dashboard controllers, slot adjustments, & query replies
│
└── templates/
    ├── base.html                  # Shell layout (responsive sidebar, toasts, & live notifications)
    ├── index.html                 # Academy Landing promotional page
    ├── booking.html               # Customer mobile-first slots picker grid
    ├── login.html                 # Register & Login forms
    ├── admin_login.html           # Separate secure Admin login card
    ├── admin.html                 # Admin operational dashboard panel
    └── profile.html               # Customer history panel & contract downloader
```

---

## 2. Default Test Accounts

To make testing instant out-of-the-box, the database automatically seeds the following credentials upon first startup:

### Customer Account
* **Email**: `user@tristar.com`
* **Password**: `user123`
* **Features**: Live slot grids, booking modal flow, player counts, complaint query center, 30-min pre-session notification bars.

### Administrator Account
* **Email**: `admin@tristar.com`
* **Password**: `Tristar@admin11` (or synced via `ADMIN_PASSWORD` env variable on Railway)
* **Features**: Revenue and occupancy reports (weekly/monthly), dynamic court creation, date-specific or global slot blocking, slot price editing, unified complaints manager, booking logs monitor, and memberships tracking.

---

## 3. How to Run the App Locally

Ensure you have Python installed (Python 3.10+ recommended) and the lightweight Flask library.

### Step 1: Install Dependencies
Open your command line / terminal inside your project directory and run:
```bash
pip install Flask
```

### Step 2: Initialize Database and Launch Server
Run the following command to automatically create the SQLite database (`badminton.db`), compile tables, seed default data, and start the local development server:
```bash
python app.py
```

### Step 3: Access the App
Open your web browser and navigate to:
* **Customer Landing/Portal**: `http://127.0.0.1:5000`
* **Secure Admin Dashboard**: `http://127.0.0.1:5000/admin/login`

---

## 4. Key Architectural Features Explained

### A. Thread-Safe Concurrency & Zero Double-Bookings
When two users hit "Pay & Book Now" at the exact same millisecond, standard databases can crash or register double-bookings. To solve this, **Tristar** uses an isolated database write lock inside `app.py`:

```python
# Starts an isolated IMMEDIATE transaction. 
# Enforces writing locks on sqlite3, serializing incoming parallel connections.
conn.execute("BEGIN IMMEDIATE TRANSACTION;")
```

Under this database-wide write-lock:
1. It queries if a confirmed booking already exists for `(court_id, slot_id, booking_date)`.
2. If it is already booked, the transaction automatically **rolls back**, and the second user receives a clean, non-crashing error message.
3. The first thread commits successfully. Zero collisions.

### B. Long-Term Membership Subscriptions
The application features long-term subscription scheduling:
* **Duration Options**: Players can purchase memberships for 1 Month, 3 Months, 6 Months, or 1 Year.
* **Eligible Slots**: Restricted to specific morning (04:00 to 08:00 AM) and evening/night (04:00 PM, 08:00 PM, 09:00 PM) sessions.
* **Conflict Resolution**: The system verifies that no hourly bookings exist within the date range of the requested subscription before booking it. Likewise, hourly bookings are blocked if they overlap with an active membership block.

### C. HTML5 Canvas Agreement Downloader
On the user profile page, players with active membership subscriptions can download their officially certified agreements.
* Agreements are generated dynamically using **HTML5 Canvas API** inside the client's browser.
* They feature high-fidelity graphics, custom typography, approval seals, and digital signatures.
* Downloads are handled directly as high-resolution PNG images.

### D. Booking Logs Chronological Sorting
To ease operational review, the Admin Dashboard groups all booking records by date. Within each date block, the reservations are sorted in **ascending chronological order** (earliest time slot first). If times are identical, they are sorted alphabetically by court name.

---

## 5. Editing and Customizing the Application

* **Theme Customization**: All colors are controlled via CSS variables at the top of `static/css/style.css`.
* **Membership Customization**: See `developer_customization_guide.md` for instructions on changing eligible membership hours, adjusting conflict rules, or altering UI sorting routines.
* **Deployment & Backups**: See `deployment_guide.md` for information on Railway deployments, volumes, and running the `restore.py` database backup utility.

1. View Table Structure (Columns & Types)
To view the schema details (column names and their data types) of a specific table, run the following:

For users table structure:

powershell-
python -c "import sqlite3; conn = sqlite3.connect('badminton.db'); conn.row_factory = sqlite3.Row; [print(r['name'], r['type']) for r in conn.execute('PRAGMA table_info(users)').fetchall()]"

For bookings table structure:

powershell-
python -c "import sqlite3; conn = sqlite3.connect('badminton.db'); conn.row_factory = sqlite3.Row; [print(r['name'], r['type']) for r in conn.execute('PRAGMA table_info(bookings)').fetchall()]"

(Note: You can replace users or bookings with any other table name like courts, slots, memberships, etc.)

2. View Table Rows & Data Details
To view all the registered records/rows inside a table formatted as a Python dictionary:

View all registered users:

powershell-
python -c "import sqlite3; conn = sqlite3.connect('badminton.db'); conn.row_factory = sqlite3.Row; [print(dict(r)) for r in conn.execute('SELECT * FROM users').fetchall()]"

View all bookings:

powershell-
python -c "import sqlite3; conn = sqlite3.connect('badminton.db'); conn.row_factory = sqlite3.Row; [print(dict(r)) for r in conn.execute('SELECT * FROM bookings').fetchall()]"

View all memberships:

powershell-
python -c "import sqlite3; conn = sqlite3.connect('badminton.db'); conn.row_factory = sqlite3.Row; [print(dict(r)) for r in conn.execute('SELECT * FROM memberships').fetchall()]"

---

## 6. Modern Interactive UPI Payments & Cancellation Log Features

To provide a state-of-the-art booking experience, several premium modules have been integrated:

### A. Inline UPI QR Code Payment Modal & Mobile Preview
- **Inline Modal Layout**: Replaced external redirects with a premium, touch-friendly, glassmorphic modal (`#modal-upi-payment`) matching the exact court rate amount (`50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 750, 1200`).
- **10-Second Verification Timer**: Prompts a 10s countdown upon clicking download to allow payment processing.
- **Mobile Long-Press Overlay**: On mobile devices, a touch-optimized overlay (`#mobile-qr-overlay`) displays, instructing the user to long-press the QR image to save it to their Photos/Gallery.
- **Confirm Payment Prompt**: Once the countdown is complete, a modal prompt asks: *"Did you complete the payment through your UPI app?"*. Clicking **Yes** redirects to `/profile` with a success toast; clicking **No** immediately triggers a background API cancellation call to release the slot and shows a failure notification.

### B. Prevention of Accidental Reloads & State Recovery
- **Navigation Guard**: When the payment modal is open, a browser navigation interceptor (`beforeunload`) warns users about leaving or refreshing the page.
- **State Recovery**: The active payment modal's state (including booking ID, rate, and seconds remaining) is tracked in `sessionStorage`. If the user accidentally refreshes, the app automatically restores the exact state and countdown time they left off.

### C. Cancellation Timestamps in Admin & User Logs
- **Dynamic Database Schema**: Database automatically runs migrations to append the `cancelled_at` text column to both the `bookings` and `memberships` tables.
- **Admin Dashboard**: Under the **Action** column in both the Bookings and Memberships table panels, administrators see the exact date and time of cancellations (e.g. `Cancelled: 2026-06-09 23:30:00`).
- **User Dashboard**: On `/profile`, the booking/membership card footer displays the `Cancelled on: [Date/Time]` stamp on the right-hand side, directly **opposite to the "Booked on" date** on the left.

### D. Cross-Page Toast Flows & Reduced Durations
- **Redirect Session Toasts**: Auth flows (login, registration) save success notifications to `sessionStorage` and redirect immediately, allowing the toast to render on the target page cleanly.
- **Optimized Durations**: To keep alerts fast and non-obtrusive, standard toasts (success/warning/error) are now dismissed after **2.5 seconds** (down from 4s), and action-required toasts (e.g. agreement downloads) show for **5 seconds** (down from 12s).

