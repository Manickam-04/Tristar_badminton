# 🚀 Vercel Serverless Deployment Guide

This guide provides step-by-step instructions for deploying your **Tristar Badminton Academy** application on **Vercel** with a **Neon PostgreSQL** database.

Vercel hosts Python applications using serverless functions, and all persistent data is securely stored in your cloud PostgreSQL database.

---

## 🛠️ Step 1: Commit and Push Your Code to GitHub

First, commit the new Vercel configuration files, database wrappers, and schema adjustments.

1. Open your terminal in the project directory.
2. Run the following Git commands to commit and push the project code:
   ```bash
   git add vercel.json .gitignore requirements.txt database.py app.py restore.py schema.sql
   git commit -m "Configure database wrapper and serverless config for Vercel deployment"
   git push origin main
   ```

---

## ☁️ Step 2: Import Project in Vercel

1. Log into your **[Vercel](https://vercel.com/)** dashboard.
2. Click **Add New** -> **Project**.
3. Import your GitHub repository (`Tristar_badminton`).
4. Keep the default Project Name, Framework Preset (**Other**), and Root Directory (**./**).

---

## 🔑 Step 3: Configure Environment Variables

Before clicking "Deploy", scroll down to the **Environment Variables** section and add the following keys:

| Key | Value (Example) | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql://neondb_owner:xyz...` | Your Neon PostgreSQL connection string. |
| `ADMIN_EMAIL` | `admin@tristar.com` | Email address for your academy admin account. |
| `ADMIN_PASSWORD` | `Tristar@admin11` | Secure password for the admin account (automatically seeded on startup). |
| `ADMIN_MOBILE` | `9876543210` | Mobile number for your admin. |
| `SECRET_KEY` | `hxkyfjmpwqydg304567_tristar_key` | Custom secure session key. |

---

## 🚀 Step 4: Deploy

1. Click the **Deploy** button.
2. Vercel will install the dependencies from your `requirements.txt`, build the serverless routing, run database seeding/migrations on startup, and provide a live URL (e.g. `https://tristar-badminton.vercel.app`).

---

## 🔄 Daily Database Backups (Vercel Cron)

Since Vercel is a serverless environment, standard background threads (which sleep for 3600 seconds) will be suspended by Vercel when the page is inactive. 

To automate daily database backups, we use **Vercel Cron Jobs**:

1. Vercel automatically reads the `"crons"` block inside [vercel.json](file:///c:/Programming%20lang%20files/Local_Project/badminton_application_deploy/vercel.json), which triggers the `/api/cron/backup` endpoint every day at midnight UTC.
2. **Secure the backup endpoint (Recommended)**:
   - Go to your Vercel Project Settings -> **Environment Variables**.
   - Vercel automatically exposes a system variable named `CRON_SECRET` when cron is configured. If you'd like to ensure only Vercel can trigger backups, copy that key.
   - The `/api/cron/backup` endpoint in `app.py` automatically checks for the presence of this header token.

---

## 🛠️ Step 5: Disaster Recovery (Restoring Backups)

To restore your database to a previous backup state:

1. Open your terminal in your local workspace.
2. Ensure you have the corresponding `.sql` backup file inside your `backups/` directory (if you want to restore a production backup, download it from your production backups folder to your local `backups/` directory).
3. Ensure the `DATABASE_URL` in your local `.env` is set to the correct PostgreSQL server.
4. Run:
   ```bash
   python restore.py
   ```
5. Choose the backup file index, confirm by typing `YES`, and the restore tool will drop tables, recreate them, and restore all rows in a single secure transaction.
