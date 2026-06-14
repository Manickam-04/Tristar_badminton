# 🏸 Tristar Badminton Academy - Court Slot Booking Portal

A high-performance, mobile-first web application for badminton court slot bookings. Built with a sleek dark-theme glassmorphism design system.

## 🚀 Key Features

* **Google OAuth 2.0 Authentication**: Standard users sign in exclusively with Google OAuth. Sessions are kept permanent to prevent auto-logouts.
* **Onboarding & Profile Setup**: A one-time Profile Setup flow immediately prompts new users to configure their Full Name and verified 10-digit Mobile Number.
* **Mobile-First Slot Grid**: Dynamic hourly grid displaying available, booked, and expired court slots in real-time.
* **Pay After Play (Offline Booking)**: Straightforward court booking flow with immediate confirmation and email-based booking record matching.
* **Administrative Portal**: Secure dashboard at `/admin/login` (using traditional credentials) to configure court slots, price overrides, specific date blockages, review user queries, and view booking logs.
* **Auto-Cleanup Daemon**: A background thread that automatically cleans up unconfirmed or pending booking slots after 5 minutes.
* **Cross-Platform Mobile Responsiveness**: Optimizations for mobile browsers, including horizontal scroll logs and custom Sign Out confirmation overlay modals.

## 🛠️ Tech Stack

* **Backend**: Python (Flask)
* **Database**: PostgreSQL (Neon Database)
* **Frontend**: HTML5, CSS3 (Vanilla Glassmorphism Theme), JavaScript (ES6)
* **Hosting / Deployment**: Vercel Serverless Ready

## ⚙️ How to Run Locally

### Step 1: Install Dependencies
Install the required packages from `requirements.txt`:
```bash
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Create a local `.env` file in the root directory:
```env
DATABASE_URL="your-postgresql-url"
GOOGLE_CLIENT_ID="your-google-client-id"
GOOGLE_CLIENT_SECRET="your-google-client-secret"
SECRET_KEY="your-session-secret-key"
```

### Step 3: Start the Server
Start the Flask development server:
```bash
python app.py
```
Access the application at `http://127.0.0.1:5000`.

## 🧑‍💻 Developer

Manicka Vinayagam
