import os
import urllib.request
import urllib.parse
import json
import secrets
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash
import database

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tristar_badminton_secret_key_super_secure')
app.permanent_session_lifetime = timedelta(days=30)

# Session configurations for maximum mobile browser compatibility
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False, # Set to False to ensure compatibility on both HTTP and HTTPS
    SESSION_REFRESH_EACH_REQUEST=True
)

# Initialize database on startup
database.init_db()

# --- Background Database Backup Scheduler ---
def start_backup_scheduler():
    import threading
    import time
    def backup_worker():
        # Sleep a short period to allow the process to boot fully
        time.sleep(10)
        while True:
            try:
                database.run_auto_backup()
            except Exception as e:
                print(f"Error in auto-backup scheduler thread: {e}")
            # Check every hour
            time.sleep(3600)
    
    thread = threading.Thread(target=backup_worker, daemon=True)
    thread.start()

start_backup_scheduler()

# --- Background Unpaid Booking Cleanup Scheduler ---
def start_booking_cleanup_scheduler():
    import threading
    import time
    def cleanup_worker():
        # Sleep a short period to allow the process to boot fully
        time.sleep(15)
        while True:
            try:
                conn = database.get_db_connection()
                # Delete bookings in 'pending_payment' status that haven't sent a heartbeat/ping in the last 10 seconds
                conn.execute(
                    "DELETE FROM bookings WHERE status = 'pending_payment' AND created_at < NOW() - INTERVAL '10 seconds'"
                )
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Error in booking cleanup scheduler thread: {e}")
            # Check every 3 seconds
            time.sleep(3)
            
    thread = threading.Thread(target=cleanup_worker, daemon=True)
    thread.start()

start_booking_cleanup_scheduler()

@app.route('/api/cron/backup')
def api_cron_backup():
    """Secure endpoint triggered by Vercel Cron to run database backups."""
    auth_header = request.headers.get('Authorization')
    vercel_cron_secret = os.environ.get('CRON_SECRET')
    
    # If a CRON_SECRET environment variable is configured in Vercel, enforce authorization
    if vercel_cron_secret and auth_header != f"Bearer {vercel_cron_secret}":
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        database.run_auto_backup()
        return jsonify({'success': True, 'message': 'Cron backup completed successfully.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Cron backup error: {str(e)}'}), 500

# --- Timezone Helpers (Indian Standard Time: UTC+5:30) ---
LOCAL_TZ = timezone(timedelta(hours=5, minutes=30))

def get_local_now():
    """Returns the current timezone-naive datetime in IST."""
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)

def get_local_today():
    """Returns the current date in IST."""
    return get_local_now().date()

# --- Helper Functions ---
def get_current_user():
    """Retrieve current logged in user details from session."""
    if 'user_id' not in session:
        return None
        
    # Verify the user actually exists in the database (handles post-reset stale sessions)
    conn = database.get_db_connection()
    db_user = conn.execute("SELECT id, email, name, role, mobile FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    conn.close()
    
    if not db_user:
        session.clear()
        return None
        
    return {
        'id': db_user['id'],
        'email': db_user['email'],
        'name': db_user['name'],
        'role': db_user['role'],
        'mobile': db_user['mobile']
    }


def login_required(role=None):
    """Decorator-like check for endpoints."""
    user = get_current_user()
    if not user:
        return False, "Authentication required"
    if role and user['role'] != role:
        return False, f"Unauthorized. {role.capitalize()} access required."
    return True, user

@app.before_request
def enforce_https():
    """Redirect HTTP traffic to HTTPS in production environment."""
    if not app.debug:
        # Only redirect if the request explicitly went through an HTTP proxy
        # (This prevents breaking local development runs where the header is missing)
        if request.headers.get('X-Forwarded-Proto') == 'http':
            url = request.url.replace('http://', 'https://', 1)
            return redirect(url, code=301)

@app.before_request
def ensure_session_permanence():
    """Ensure that active sessions are always kept permanent."""
    if 'user_id' in session:
        session.permanent = True

@app.before_request
def check_profile_setup():
    """Ensure that standard users with incomplete profiles (no mobile) are redirect-guarded."""
    if request.path.startswith('/static') or request.path in ('/profile-setup', '/api/auth/profile-setup', '/logout', '/login/google', '/api/auth/callback'):
        return
        
    user = get_current_user()
    if user and user['role'] == 'user' and not user['mobile']:
        session['pending_google_user'] = {
            'email': user['email'],
            'name': user['name'],
            'sub': session.get('google_sub')
        }
        session.pop('user_id', None)
        return redirect(url_for('profile_setup_page'))

# --- Page Render Routes ---
@app.route('/')
def home():
    user = get_current_user()
    return render_template('index.html', user=user)

@app.route('/booking')
def booking_page():
    user = get_current_user()
    if not user:
        return redirect(url_for('login_page', next=request.path))
    
    # Retrieve active court count and listing
    conn = database.get_db_connection()
    courts = conn.execute("SELECT * FROM courts WHERE is_active = 1").fetchall()
    conn.close()
    
    return render_template('booking.html', user=user, courts=courts)

@app.route('/login', methods=['GET'])
def login_page():
    if get_current_user():
        next_url = request.args.get('next', url_for('home'))
        return redirect(next_url)
        
    next_param = request.args.get('next')
    if next_param:
        session['next_url'] = next_param
    else:
        session.pop('next_url', None)
        
    return render_template('login.html')

@app.route('/privacy-policy')
def privacy_policy_page():
    user = get_current_user()
    return render_template('privacy_policy.html', user=user)

@app.route('/terms-and-conditions')
def terms_page():
    user = get_current_user()
    return render_template('terms.html', user=user)

# --- GOOGLE OAUTH ROUTES ---
@app.route('/login/google')
def login_google():
    if get_current_user():
        return redirect(url_for('home'))
        
    client_id = (os.environ.get('GOOGLE_CLIENT_ID') or '').strip('\'" \t\r\n')
    if not client_id:
        return redirect(url_for('login_page', error="Google Client ID is not configured in environment variables. Please set GOOGLE_CLIENT_ID on Vercel."))
        
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    
    redirect_uri = url_for('api_auth_callback', _external=True)
    if 'localhost' in redirect_uri:
        redirect_uri = redirect_uri.replace('localhost', '127.0.0.1')
    
    # Respect the protocol forwarded by reverse proxies (like Vercel)
    proto = request.headers.get('X-Forwarded-Proto')
    if proto:
        if redirect_uri.startswith('http://') and proto == 'https':
            redirect_uri = redirect_uri.replace('http://', 'https://', 1)
    else:
        # Local development (no proxy): enforce http scheme if request is not secure
        if not request.is_secure and redirect_uri.startswith('https://'):
            redirect_uri = redirect_uri.replace('https://', 'http://', 1)
        
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'prompt': 'select_account'
    }
    auth_url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(params)
    return redirect(auth_url)

@app.route('/api/auth/callback')
def api_auth_callback():
    error = request.args.get('error')
    if error:
        return redirect(url_for('login_page', error=f"Google Error: {error}"))
        
    state = request.args.get('state')
    saved_state = session.pop('oauth_state', None)
    if not state or state != saved_state:
        return redirect(url_for('login_page', error="Invalid state token (CSRF protection failed)."))
        
    code = request.args.get('code')
    if not code:
        return redirect(url_for('login_page', error="No authorization code returned."))
        
    redirect_uri = url_for('api_auth_callback', _external=True)
    if 'localhost' in redirect_uri:
        redirect_uri = redirect_uri.replace('localhost', '127.0.0.1')
    
    # Respect the protocol forwarded by reverse proxies (like Vercel)
    proto = request.headers.get('X-Forwarded-Proto')
    if proto:
        if redirect_uri.startswith('http://') and proto == 'https':
            redirect_uri = redirect_uri.replace('http://', 'https://', 1)
    else:
        # Local development (no proxy): enforce http scheme if request is not secure
        if not request.is_secure and redirect_uri.startswith('https://'):
            redirect_uri = redirect_uri.replace('https://', 'http://', 1)
        
    client_id = (os.environ.get('GOOGLE_CLIENT_ID') or '').strip('\'" \t\r\n')
    client_secret = (os.environ.get('GOOGLE_CLIENT_SECRET') or '').strip('\'" \t\r\n')
    
    payload = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }
    
    try:
        data = urllib.parse.urlencode(payload).encode('utf-8')
        req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data, method='POST')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        
        with urllib.request.urlopen(req) as response:
            token_data = json.loads(response.read().decode('utf-8'))
            
        access_token = token_data.get('access_token')
        if not access_token:
            return redirect(url_for('login_page', error="Failed to retrieve access token."))
            
        info_req = urllib.request.Request('https://www.googleapis.com/oauth2/v3/userinfo')
        info_req.add_header('Authorization', f"Bearer {access_token}")
        
        with urllib.request.urlopen(info_req) as response:
            user_info = json.loads(response.read().decode('utf-8'))
            
        sub = user_info.get('sub')
        email = user_info.get('email')
        name = user_info.get('name', 'Google User')
        
        if not email or not sub:
            return redirect(url_for('login_page', error="Failed to retrieve unique user info from Google."))
            
        conn = database.get_db_connection()
        
        # Check by google_sub
        db_user = conn.execute("SELECT * FROM users WHERE google_sub = ?", (sub,)).fetchone()
        
        if not db_user:
            # Check by email
            db_user = conn.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email.lower(),)).fetchone()
            if db_user:
                # Merge sub ID
                conn.execute("UPDATE users SET google_sub = ? WHERE id = ?", (sub, db_user['id']))
                conn.commit()
                db_user = conn.execute("SELECT * FROM users WHERE id = ?", (db_user['id'],)).fetchone()
                
        conn.close()
        
        if db_user and db_user['mobile']:
            session['user_id'] = db_user['id']
            session['email'] = db_user['email']
            session['name'] = db_user['name']
            session['role'] = db_user['role']
            session.permanent = True
            
            next_url = session.pop('next_url', url_for('home'))
            return redirect(next_url)
        else:
            session['pending_google_user'] = {
                'email': email,
                'name': name,
                'sub': sub
            }
            return redirect(url_for('profile_setup_page'))
            
    except Exception as e:
        print(f"OAuth error: {e}")
        return redirect(url_for('login_page', error=f"Authentication failed: {str(e)}"))

@app.route('/profile-setup', methods=['GET'])
def profile_setup_page():
    if 'pending_google_user' not in session:
        if get_current_user():
            return redirect(url_for('home'))
        return redirect(url_for('login_page'))
        
    return render_template('profile_setup.html', name=session['pending_google_user']['name'])

@app.route('/api/auth/profile-setup', methods=['POST'])
def api_auth_profile_setup():
    if 'pending_google_user' not in session:
        return jsonify({'success': False, 'message': 'Session expired. Please sign in with Google again.'}), 401
        
    pending = session['pending_google_user']
    
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    mobile = data.get('mobile', '').strip()
    
    if not name or not mobile:
        return jsonify({'success': False, 'message': 'Name and Mobile number are required.'}), 400
        
    if not mobile.isdigit() or len(mobile) != 10:
        return jsonify({'success': False, 'message': 'Invalid mobile number. It must be exactly 10 digits.'}), 400
        
    conn = database.get_db_connection()
    try:
        existing_email_user = conn.execute("SELECT id, email FROM users WHERE LOWER(email) = ?", (pending['email'].lower(),)).fetchone()
        
        check_query = "SELECT id FROM users WHERE mobile = ?"
        check_params = [mobile]
        if existing_email_user:
            check_query += " AND id != ?"
            check_params.append(existing_email_user['id'])
            
        duplicate_mobile = conn.execute(check_query, tuple(check_params)).fetchone()
        if duplicate_mobile:
            return jsonify({'success': False, 'message': 'Mobile number already registered by another account.'}), 400
            
        if existing_email_user:
            conn.execute(
                "UPDATE users SET name = ?, mobile = ?, google_sub = ? WHERE id = ?",
                (name, mobile, pending['sub'], existing_email_user['id'])
            )
            user_id = existing_email_user['id']
            user_role = 'user'
        else:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (email, mobile, google_sub, name, role) VALUES (?, ?, ?, ?, 'user')",
                (pending['email'], mobile, pending['sub'], name)
            )
            user_id = cursor.lastrowid
            if not user_id:
                row = conn.execute("SELECT id FROM users WHERE google_sub = ?", (pending['sub'],)).fetchone()
                user_id = row['id']
            user_role = 'user'
            
        conn.commit()
        
        session['user_id'] = user_id
        session['email'] = pending['email']
        session['name'] = name
        session['role'] = user_role
        session.permanent = True
        
        session.pop('pending_google_user', None)
        
        next_url = session.pop('next_url', url_for('booking_page'))
        return jsonify({'success': True, 'message': 'Profile setup completed successfully!', 'next': next_url})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/profile')
def profile_page():
    user = get_current_user()
    if not user:
        return redirect(url_for('login_page', next=request.path))
    
    conn = database.get_db_connection()
    db_user = conn.execute("SELECT name, email, mobile, role FROM users WHERE id = ?", (user['id'],)).fetchone()
    conn.close()
    
    if not db_user:
        return redirect(url_for('login_page', next=request.path))
        
    user_data = {
        'id': user['id'],
        'name': db_user['name'],
        'email': db_user['email'],
        'mobile': db_user['mobile'],
        'role': db_user['role']
    }
    return render_template('profile.html', user=user_data)

@app.route('/admin')
def admin_page():
    user = get_current_user()
    if not user or user['role'] != 'admin':
        return redirect(url_for('admin_login_page'))
    return render_template('admin.html', user=user)

@app.route('/admin/login')
def admin_login_page():
    if get_current_user() and get_current_user()['role'] == 'admin':
        return redirect(url_for('admin_page'))
    return render_template('admin_login.html')

# --- AUTHENTICATION API ---
@app.route('/api/register', methods=['POST'])
def api_register():
    return jsonify({'success': False, 'message': 'Registration via email and password has been disabled. Please sign in with Google.'}), 403

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    identity = data.get('email', '').strip() # Accept email or mobile
    password = data.get('password', '')
    as_role = data.get('role', 'user') # 'user' or 'admin'
    remember = data.get('remember', False)
    
    if as_role == 'user':
        return jsonify({'success': False, 'message': 'Password login has been disabled for standard users. Please sign in with Google.'}), 403
        
    if not identity or not password:
        return jsonify({'success': False, 'message': 'Email/Mobile and password are required.'}), 400
        
    conn = database.get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE LOWER(email) = ? OR mobile = ?", (identity.lower(), identity)).fetchone()
    conn.close()
    
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'success': False, 'message': 'Invalid credentials.'}), 401
        
    if as_role == 'admin' and user['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized. Admin credentials required.'}), 403
        
    session['user_id'] = user['id']
    session['email'] = user['email']
    session['name'] = user['name']
    session['role'] = user['role']
    if remember or as_role == 'admin':
        session.permanent = True
    
    return jsonify({'success': True, 'message': 'Login successful!', 'role': user['role']})


@app.route('/api/forgot-password', methods=['POST'])
def api_forgot_password():
    return jsonify({'success': False, 'message': 'Password reset is disabled.'}), 403

@app.route('/api/profile/update', methods=['POST'])
def api_profile_update():
    authorized, user = login_required()
    if not authorized:
        return jsonify({'success': False, 'message': user}), 401
        
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    mobile = data.get('mobile', '').strip()
    
    if not name or not mobile:
        return jsonify({'success': False, 'message': 'Name and Mobile number are required.'}), 400
        
    conn = database.get_db_connection()
    try:
        # Check if mobile is used by another user
        other_user = conn.execute("SELECT id FROM users WHERE mobile = ? AND id != ?", (mobile, user['id'])).fetchone()
        if other_user:
            return jsonify({'success': False, 'message': 'Mobile number already registered by another account.'}), 400
            
        conn.execute("UPDATE users SET name = ?, mobile = ? WHERE id = ?", (name, mobile, user['id']))
        conn.commit()
        
        # Update session
        session['name'] = name
        
        return jsonify({'success': True, 'message': 'Profile updated successfully!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


# --- COURTS API ---
@app.route('/api/courts', methods=['GET'])
def api_get_courts():
    conn = database.get_db_connection()
    try:
        courts = conn.execute("SELECT * FROM courts WHERE is_active = 1").fetchall()
        return jsonify({'success': True, 'courts': [{'id': c['id'], 'name': c['name'], 'description': c['description']} for c in courts]})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()


# --- BOOKING & SLOTS API ---
@app.route('/api/slots', methods=['GET'])
def api_get_slots():
    authorized, user_or_err = login_required()
    if not authorized:
        return jsonify({'success': False, 'message': user_or_err}), 401
        
    date_str = request.args.get('date')
    court_id = request.args.get('court_id')
    
    if not date_str:
        date_str = get_local_now().strftime('%Y-%m-%d')
        
    conn = database.get_db_connection()
    try:
        # Delete stale pending_payment bookings immediately to ensure accurate real-time availability grid
        conn.execute(
            "DELETE FROM bookings WHERE status = 'pending_payment' AND created_at < NOW() - INTERVAL '10 seconds'"
        )
        conn.commit()

        # Check if requested date is a weekend (5 = Saturday, 6 = Sunday)
        try:
            booking_dt = datetime.strptime(date_str, '%Y-%m-%d').date()
            is_weekend = (booking_dt.weekday() == 5 or booking_dt.weekday() == 6)
        except ValueError:
            is_weekend = False

        # Fetch active court if no court_id is supplied
        if not court_id:
            court = conn.execute("SELECT id FROM courts WHERE is_active = 1 LIMIT 1").fetchone()
            if not court:
                return jsonify({'success': False, 'slots': []})
            court_id = court['id']
            
        # Fetch all slot templates for this court (sorted chronologically)
        slots = conn.execute("SELECT * FROM slots WHERE court_id = ? ORDER BY start_time ASC", (court_id,)).fetchall()
        
        # Fetch confirmed or pending_payment bookings for this date and court
        bookings_rows = conn.execute(
            "SELECT * FROM bookings WHERE court_id = ? AND booking_date = ? AND status IN ('confirmed', 'pending_payment')",
            (court_id, date_str)
        ).fetchall()
        bookings_dict = {b['slot_id']: b for b in bookings_rows}
        
        # Fetch active memberships for this court covering this date
        memberships_rows = conn.execute(
            """
            SELECT * FROM memberships 
            WHERE court_id = ? AND status = 'confirmed'
            AND ? BETWEEN start_date AND end_date
            """, (court_id, date_str)
        ).fetchall()
        memberships_dict = {m['slot_id']: m for m in memberships_rows}
        
        # Fetch manual specific slot blocks for this date
        blocks_rows = conn.execute(
            "SELECT slot_id, reason FROM slot_blocks WHERE block_date = ?",
            (date_str,)
        ).fetchall()
        blocks_dict = {blk['slot_id']: blk['reason'] for blk in blocks_rows}
        
        # Fetch price overrides for this date
        overrides_rows = conn.execute(
            "SELECT slot_id, price FROM pricing_overrides WHERE override_date = ?",
            (date_str,)
        ).fetchall()
        overrides_dict = {ovr['slot_id']: ovr['price'] for ovr in overrides_rows}
        
        formatted_slots = []
        for s in slots:
            slot_id = s['id']
            
            # Pricing logic: Weekend flat 300.0, else Override > Default
            if is_weekend:
                price = 300.0
            else:
                price = overrides_dict.get(slot_id, s['default_price'])
            
            # Blocking logic: global block or specific date block
            is_blocked = s['is_blocked']
            block_reason = s['blocked_reason']
            if slot_id in blocks_dict:
                is_blocked = 1
                block_reason = blocks_dict[slot_id]
                
            # Booking logic
            status = 'available'
            booked_by_user = None
            booking_id = None
            num_members = 0
            
            if is_blocked:
                status = 'blocked'
            elif slot_id in bookings_dict:
                booking = bookings_dict[slot_id]
                booking_id = booking['id']
                num_members = booking['num_members']
                booker_id = booking['user_id']
                
                if booking['status'] == 'pending_payment':
                    status = 'booked'
                elif user_or_err and booker_id == user_or_err['id']:
                    status = 'booked_by_me'
                else:
                    status = 'booked'
                
                # We can load booker details if user is admin
                if user_or_err and user_or_err['role'] == 'admin':
                    booker = conn.execute("SELECT name, email FROM users WHERE id = ?", (booker_id,)).fetchone()
                    if booker:
                        booked_by_user = {'name': booker['name'], 'email': booker['email']}
            elif slot_id in memberships_dict:
                membership = memberships_dict[slot_id]
                booking_id = 1000000 + membership['id']
                num_members = 1
                
                # Membership booking is always displayed as 'booked' in the hourly booking grid
                status = 'booked'
                
                # We can load booker details if user is admin
                if user_or_err and user_or_err['role'] == 'admin':
                    booker_id = membership['user_id']
                    booker = conn.execute("SELECT name, email FROM users WHERE id = ?", (booker_id,)).fetchone()
                    if booker:
                        booked_by_user = {'name': f"{booker['name']} (Member)", 'email': booker['email']}
            
            # Expiration logic: if slot is available but the end time has passed, mark as expired
            if status == 'available':
                try:
                    start_dt = datetime.strptime(f"{date_str} {s['start_time']}", "%Y-%m-%d %H:%M")
                    end_dt = datetime.strptime(f"{date_str} {s['end_time']}", "%Y-%m-%d %H:%M")
                    if end_dt <= start_dt:
                        end_dt += timedelta(days=1)
                    if get_local_now() >= end_dt:
                        status = 'expired'
                except Exception:
                    pass
            
            formatted_slots.append({
                'slot_id': slot_id,
                'court_id': court_id,
                'start_time': s['start_time'],
                'end_time': s['end_time'],
                'price': price,
                'status': status,
                'booking_id': booking_id,
                'num_members': num_members,
                'block_reason': block_reason,
                'booked_by': booked_by_user
            })
            
        return jsonify({'success': True, 'slots': formatted_slots, 'date': date_str})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/api/book', methods=['POST'])
def api_book_slot():
    """
    Highly secure, concurrent-safe booking handler.
    Starts an isolated IMMEDIATE transaction to lock database writes,
    preventing double bookings at the same millisecond.
    """
    authorized, user = login_required()
    if not authorized:
        return jsonify({'success': False, 'message': user}), 401
        
    data = request.get_json() or {}
    court_id = data.get('court_id')
    slot_id = data.get('slot_id')
    date_str = data.get('date', '').strip()
    num_members = int(data.get('num_members', 1))
    payment_method = 'offline'
    
    if not court_id or not slot_id or not date_str:
        return jsonify({'success': False, 'message': 'Court ID, Slot ID, and Date are required.'}), 400
        
    # Validate date
    try:
        booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        if booking_date < get_local_today():
            return jsonify({'success': False, 'message': 'Cannot book slots in the past.'}), 400
        if booking_date > get_local_today() + timedelta(days=4):
            return jsonify({'success': False, 'message': 'Cannot book slots more than 4 days in advance.'}), 400
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid date format.'}), 400
        
    conn = database.get_db_connection()
    try:
        # Start isolated immediate lock
        conn.execute("BEGIN IMMEDIATE TRANSACTION;")
        
        # 1. Verify if slot is globally or specifically blocked (lock row for concurrency safety)
        slot = conn.execute("SELECT * FROM slots WHERE id = ? AND court_id = ? FOR UPDATE", (slot_id, court_id)).fetchone()
        if not slot:
            conn.rollback()
            return jsonify({'success': False, 'message': 'Invalid slot or court selection.'}), 400
            
        # Check slot expiration
        try:
            start_dt = datetime.strptime(f"{date_str} {slot['start_time']}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{date_str} {slot['end_time']}", "%Y-%m-%d %H:%M")
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
            if get_local_now() >= end_dt:
                conn.rollback()
                return jsonify({'success': False, 'message': 'This slot has expired and is no longer available for booking.'}), 400
        except Exception:
            pass
            
        if slot['is_blocked']:
            conn.rollback()
            return jsonify({'success': False, 'message': f'This slot is globally blocked: {slot["blocked_reason"]}'}), 400
            
        specific_block = conn.execute(
            "SELECT reason FROM slot_blocks WHERE slot_id = ? AND block_date = ?",
            (slot_id, date_str)
        ).fetchone()
        if specific_block:
            conn.rollback()
            return jsonify({'success': False, 'message': f'This slot is blocked on this date: {specific_block["reason"]}'}), 400
            
        # 2. Check if already booked (Double booking protection)
        existing_booking = conn.execute(
            "SELECT id FROM bookings WHERE court_id = ? AND slot_id = ? AND booking_date = ? AND status IN ('confirmed', 'pending_payment')",
            (court_id, slot_id, date_str)
        ).fetchone()
        if existing_booking:
            conn.rollback()
            return jsonify({'success': False, 'message': 'This slot has already been booked by another user.'}), 409
            
        existing_membership = conn.execute(
            """
            SELECT id FROM memberships 
            WHERE court_id = ? AND slot_id = ? AND ? BETWEEN start_date AND end_date AND status = 'confirmed'
            """, (court_id, slot_id, date_str)
        ).fetchone()
        if existing_membership:
            conn.rollback()
            return jsonify({'success': False, 'message': 'This slot is already booked via a membership subscription.'}), 409

            
        # 3. Calculate final pricing
        # Check if booking date is a weekend (5 = Saturday, 6 = Sunday)
        if booking_date.weekday() == 5 or booking_date.weekday() == 6:
            total_price = 300.0
        else:
            override = conn.execute(
                "SELECT price FROM pricing_overrides WHERE slot_id = ? AND override_date = ?",
                (slot_id, date_str)
            ).fetchone()
            price_per_person = override['price'] if override else slot['default_price']
            total_price = price_per_person * num_members
        
        # 4. Insert booking
        initial_status = 'pending_payment'
        cancel_token = secrets.token_urlsafe(16)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO bookings (user_id, court_id, slot_id, booking_date, num_slots, num_members, total_price, status, payment_method, cancellation_token) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?)",
            (user['id'], court_id, slot_id, date_str, num_members, total_price, initial_status, payment_method, cancel_token)
        )
        
        # Commit will unlock database
        conn.commit()
        booking_id = cursor.lastrowid
        
        return jsonify({
            'success': True, 
            'message': 'Slot booked successfully!',
            'booking': {
                'id': booking_id,
                'court_id': court_id,
                'slot_id': slot_id,
                'date': date_str,
                'total_price': total_price,
                'payment_method': payment_method,
                'cancellation_token': cancel_token
            }
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/api/book/ping', methods=['POST'])
def api_book_ping():
    # Retrieve from JSON, form, or query parameters
    data = request.get_json(silent=True) or {}
    booking_id = data.get('booking_id')
    cancellation_token = data.get('cancellation_token')
    
    if not booking_id:
        booking_id = request.form.get('booking_id') or request.args.get('booking_id')
    if not cancellation_token:
        cancellation_token = request.form.get('cancellation_token') or request.args.get('cancellation_token')
        
    # Parse raw request body if necessary
    if (not booking_id or not cancellation_token) and request.data:
        try:
            raw_str = request.data.decode('utf-8')
            if raw_str.strip().startswith('{'):
                raw_json = json.loads(raw_str)
                booking_id = booking_id or raw_json.get('booking_id')
                cancellation_token = cancellation_token or raw_json.get('cancellation_token')
            else:
                parsed = urllib.parse.parse_qs(raw_str)
                if 'booking_id' in parsed:
                    booking_id = booking_id or parsed['booking_id'][0]
                if 'cancellation_token' in parsed:
                    cancellation_token = cancellation_token or parsed['cancellation_token'][0]
        except Exception:
            pass

    if not booking_id or not cancellation_token:
        return jsonify({'success': False, 'message': 'Missing parameters'}), 400

    conn = database.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bookings SET created_at = NOW() WHERE id = ? AND cancellation_token = ? AND status = 'pending_payment'",
            (int(booking_id), cancellation_token)
        )
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/book/update-method', methods=['POST'])
def api_update_booking_payment_method():
    authorized, user = login_required()
    if not authorized:
        return jsonify({'success': False, 'message': user}), 401
        
    data = request.get_json() or {}
    booking_id = data.get('booking_id')
    payment_method = data.get('payment_method', 'online').strip().lower()
    
    if payment_method not in ('online', 'offline'):
        payment_method = 'online'
        
    if not booking_id:
        return jsonify({'success': False, 'message': 'Booking ID is required.'}), 400
        
    conn = database.get_db_connection()
    try:
        # Check if booking exists and belongs to the user or is admin
        booking = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        if not booking:
            return jsonify({'success': False, 'message': 'Booking not found.'}), 404
            
        if booking['user_id'] != user['id'] and user['role'] != 'admin':
            return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
            
        new_status = 'confirmed' if payment_method == 'offline' else 'pending_payment'
        conn.execute(
            "UPDATE bookings SET payment_method = ?, status = ? WHERE id = ?",
            (payment_method, new_status, booking_id)
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Payment method updated successfully.'})
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        err_msg = str(e).lower()
        if 'unique' in err_msg or 'duplicate key' in err_msg or (hasattr(e, 'pgcode') and e.pgcode == '23505'):
            return jsonify({'success': False, 'message': 'This slot has already been booked and confirmed by another user.'}), 409
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/api/book/confirm-payment', methods=['POST'])
def api_confirm_payment():
    authorized, user = login_required()
    if not authorized:
        return jsonify({'success': False, 'message': user}), 401
        
    data = request.get_json() or {}
    booking_id = data.get('booking_id')
    
    if not booking_id:
        return jsonify({'success': False, 'message': 'Booking ID is required.'}), 400
        
    conn = database.get_db_connection()
    try:
        booking = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        if not booking:
            return jsonify({'success': False, 'message': 'Booking not found.'}), 404
            
        if booking['user_id'] != user['id'] and user['role'] != 'admin':
            return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
            
        if booking['status'] != 'pending_payment':
            return jsonify({'success': True, 'message': 'Payment already confirmed.'})
            
        conn.execute(
            "UPDATE bookings SET status = 'confirmed' WHERE id = ?",
            (booking_id,)
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Payment confirmed successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/api/book-membership', methods=['POST'])
def api_book_membership():
    authorized, user = login_required()
    if not authorized:
        return jsonify({'success': False, 'message': user}), 401
        
    data = request.get_json() or {}
    court_id = data.get('court_id')
    slot_id = data.get('slot_id')
    start_date_str = data.get('start_date', '').strip()
    duration = data.get('duration', '').strip()
    amount = float(data.get('amount', 0.0))
    
    if not court_id or not slot_id or not start_date_str or not duration or amount <= 0:
        return jsonify({'success': False, 'message': 'Court ID, Slot ID, Start Date, Duration, and Amount are required.'}), 400
        
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        if start_date < get_local_today():
            return jsonify({'success': False, 'message': 'Cannot start membership in the past.'}), 400
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid start date format.'}), 400
        
    if duration == '1 Month':
        days = 30
    elif duration == '3 Months':
        days = 90
    elif duration == '6 Months':
        days = 180
    elif duration == '1 Year':
        days = 365
    else:
        return jsonify({'success': False, 'message': 'Invalid duration specified.'}), 400
        
    end_date = start_date + timedelta(days=days - 1)
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    conn = database.get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE TRANSACTION;")
        
        slot = conn.execute("SELECT * FROM slots WHERE id = ? AND court_id = ? FOR UPDATE", (slot_id, court_id)).fetchone()
        if not slot:
            conn.rollback()
            return jsonify({'success': False, 'message': 'Invalid slot or court selection.'}), 400
            
        # Validate that the slot is one of the allowed membership slot timings
        allowed_morning = ["04:00", "05:00", "06:00", "07:00", "08:00"]
        allowed_evening_night = ["16:00", "20:00", "21:00"]
        start_time = slot['start_time']
        
        if start_time not in allowed_morning and start_time not in allowed_evening_night:
            conn.rollback()
            return jsonify({'success': False, 'message': 'This slot is not eligible for membership booking.'}), 400
            
        # Determine monthly rate and expected price
        monthly_rate = 1200.0 if start_time in allowed_morning else 750.0
        
        if duration == '1 Month':
            months = 1
        elif duration == '3 Months':
            months = 3
        elif duration == '6 Months':
            months = 6
        elif duration == '1 Year':
            months = 12
        else:
            conn.rollback()
            return jsonify({'success': False, 'message': 'Invalid duration.'}), 400
            
        amount = monthly_rate * months
            
        existing_booking = conn.execute(
            """
            SELECT booking_date FROM bookings 
            WHERE court_id = ? AND slot_id = ? AND status = 'confirmed'
            AND booking_date BETWEEN ? AND ?
            """, (court_id, slot_id, start_date_str, end_date_str)
        ).fetchone()
        if existing_booking:
            conn.rollback()
            return jsonify({'success': False, 'message': f'This slot is already booked hourly on {existing_booking["booking_date"]}.'}), 409
            
        existing_membership = conn.execute(
            """
            SELECT start_date, end_date FROM memberships
            WHERE court_id = ? AND slot_id = ? AND status = 'confirmed'
            AND start_date <= ? AND end_date >= ?
            """, (court_id, slot_id, end_date_str, start_date_str)
        ).fetchone()
        if existing_membership:
            conn.rollback()
            return jsonify({
                'success': False, 
                'message': f'This slot already has an active membership from {existing_membership["start_date"]} to {existing_membership["end_date"]}.'
            }), 409
            
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO memberships (user_id, court_id, slot_id, start_date, end_date, duration, amount, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmed')
            """, (user['id'], court_id, slot_id, start_date_str, end_date_str, duration, amount)
        )
        conn.commit()
        membership_id = cursor.lastrowid
        
        return jsonify({
            'success': True,
            'message': 'Membership subscription booked successfully!',
            'membership': {
                'id': membership_id,
                'court_id': court_id,
                'slot_id': slot_id,
                'start_date': start_date_str,
                'end_date': end_date_str,
                'duration': duration,
                'amount': amount
            }
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()
@app.route('/api/membership-eligible-slots', methods=['GET'])
def api_membership_eligible_slots():
    court_id = request.args.get('court_id', '').strip()
    start_date_str = request.args.get('start_date', '').strip()
    duration = request.args.get('duration', '').strip()
    
    if not court_id or not start_date_str or not duration:
        return jsonify({'success': False, 'message': 'Missing parameters.'}), 400
        
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid start date format.'}), 400
        
    if duration == '1 Month':
        days = 30
    elif duration == '3 Months':
        days = 90
    elif duration == '6 Months':
        days = 180
    elif duration == '1 Year':
        days = 365
    else:
        return jsonify({'success': False, 'message': 'Invalid duration.'}), 400
        
    end_date = start_date + timedelta(days=days - 1)
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    conn = database.get_db_connection()
    try:
        # Get all slots for this court
        slots = conn.execute("SELECT * FROM slots WHERE court_id = ? ORDER BY start_time ASC", (court_id,)).fetchall()
        
        # We only care about allowed membership slots
        allowed_morning = ["04:00", "05:00", "06:00", "07:00", "08:00"]
        allowed_evening_night = ["16:00", "20:00", "21:00"] 
        
        result = []
        for s in slots:
            slot_id = s['id']
            start_time = s['start_time']
            
            # Check if this slot timing is eligible for memberships
            if start_time not in allowed_morning and start_time not in allowed_evening_night:
                continue
                
            # Check if globally blocked
            if s['is_blocked']:
                result.append({
                    'slot_id': slot_id,
                    'start_time': start_time,
                    'end_time': s['end_time'],
                    'status': 'blocked',
                    'reason': s['blocked_reason'] or 'Globally Blocked'
                })
                continue
                
            # Check if there are any hourly bookings in the range [start_date, end_date]
            existing_booking = conn.execute(
                """
                SELECT booking_date FROM bookings 
                WHERE court_id = ? AND slot_id = ? AND status = 'confirmed'
                AND booking_date BETWEEN ? AND ?
                """, (court_id, slot_id, start_date_str, end_date_str)
            ).fetchone()
            
            if existing_booking:
                result.append({
                    'slot_id': slot_id,
                    'start_time': start_time,
                    'end_time': s['end_time'],
                    'status': 'booked',
                    'reason': f'Booked hourly on {existing_booking["booking_date"]}'
                })
                continue
                
            # Check if there are any overlapping memberships in the range
            existing_membership = conn.execute(
                """
                SELECT start_date, end_date FROM memberships
                WHERE court_id = ? AND slot_id = ? AND status = 'confirmed'
                AND start_date <= ? AND end_date >= ?
                """, (court_id, slot_id, end_date_str, start_date_str)
            ).fetchone()
            
            if existing_membership:
                result.append({
                    'slot_id': slot_id,
                    'start_time': start_time,
                    'end_time': s['end_time'],
                    'status': 'booked',
                    'reason': f'Reserved by membership from {existing_membership["start_date"]} to {existing_membership["end_date"]}'
                })
                continue
                
            # Available
            result.append({
                'slot_id': slot_id,
                'start_time': start_time,
                'end_time': s['end_time'],
                'status': 'available',
                'reason': ''
            })
            
        return jsonify({'success': True, 'slots': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/cancel', methods=['POST'])
def api_cancel_booking():
    # Attempt to retrieve from JSON
    data = request.get_json(silent=True) or {}
    
    booking_id = data.get('booking_id')
    cancellation_token = data.get('cancellation_token')
    
    # Fallback to form parameters or query parameters
    if not booking_id:
        booking_id = request.form.get('booking_id') or request.args.get('booking_id')
    if not cancellation_token:
        cancellation_token = request.form.get('cancellation_token') or request.args.get('cancellation_token')
        
    # Extra fallback: parse request.data if it contains query string parameters or raw JSON
    if (not booking_id or not cancellation_token) and request.data:
        try:
            raw_str = request.data.decode('utf-8')
            if raw_str.strip().startswith('{'):
                raw_json = json.loads(raw_str)
                booking_id = booking_id or raw_json.get('booking_id')
                cancellation_token = cancellation_token or raw_json.get('cancellation_token')
            else:
                # Try parsing as form/query parameters
                parsed = urllib.parse.parse_qs(raw_str)
                if 'booking_id' in parsed:
                    booking_id = booking_id or parsed['booking_id'][0]
                if 'cancellation_token' in parsed:
                    cancellation_token = cancellation_token or parsed['cancellation_token'][0]
        except Exception:
            pass
    
    # Check if we can authorize this cancel using the secure token
    token_authorized = False
    token_user_id = None
    if booking_id and cancellation_token:
        try:
            booking_id_val = int(booking_id)
        except (TypeError, ValueError):
            booking_id_val = 0
            
        conn = database.get_db_connection()
        try:
            booking = conn.execute("SELECT cancellation_token, status, user_id FROM bookings WHERE id = ?", (booking_id_val,)).fetchone()
            if booking and booking['status'] == 'pending_payment' and booking['cancellation_token'] == cancellation_token:
                token_authorized = True
                token_user_id = booking['user_id']
        except Exception:
            pass
        finally:
            conn.close()
            
    # Mock user if token is authorized, so we bypass login_required
    user = None
    if token_authorized:
        user = {'role': 'user', 'id': token_user_id}
    else:
        authorized, logged_user = login_required()
        if not authorized:
            return jsonify({'success': False, 'message': logged_user}), 401
        user = logged_user
        
    if not booking_id:
        return jsonify({'success': False, 'message': 'Booking ID required.'}), 400
        
    try:
        booking_id_val = int(booking_id)
    except (TypeError, ValueError):
        booking_id_val = 0
        
    conn = database.get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE TRANSACTION;")
        
        if booking_id_val >= 1000000:
            # Cancel Membership
            membership_id = booking_id_val - 1000000
            membership = conn.execute(
                """
                SELECT m.*, s.start_time, s.end_time
                FROM memberships m
                JOIN slots s ON m.slot_id = s.id
                WHERE m.id = ?
                FOR UPDATE OF m
                """, (membership_id,)
            ).fetchone()
            if not membership:
                conn.rollback()
                return jsonify({'success': False, 'message': 'Membership subscription not found.'}), 404
                
            if user['role'] != 'admin' and membership['user_id'] != user['id']:
                conn.rollback()
                return jsonify({'success': False, 'message': 'Unauthorized to cancel this membership.'}), 403
                
            if user['role'] != 'admin':
                try:
                    start_date_dt = datetime.strptime(membership['start_date'], "%Y-%m-%d").date()
                    if get_local_today() >= start_date_dt:
                        conn.rollback()
                        return jsonify({'success': False, 'message': 'Cannot cancel a membership subscription after its start date.'}), 400
                except Exception:
                    conn.rollback()
                    return jsonify({'success': False, 'message': 'Error validating membership timing.'}), 400
                    
            if membership['status'] == 'cancelled':
                conn.rollback()
                return jsonify({'success': False, 'message': 'Membership is already cancelled.'}), 400
                
            conn.execute(
                "UPDATE memberships SET status = 'cancelled', cancelled_at = ? WHERE id = ?", 
                (get_local_now().strftime('%Y-%m-%d %H:%M:%S'), membership_id)
            )
            conn.commit()
            return jsonify({
                'success': True, 
                'message': 'Membership subscription cancelled successfully.',
                'payment_method': 'online'
            })
            
        else:
            # Cancel hourly booking
            booking = conn.execute(
                """
                SELECT b.*, s.start_time, s.end_time
                FROM bookings b
                JOIN slots s ON b.slot_id = s.id
                WHERE b.id = ?
                FOR UPDATE OF b
                """, (booking_id,)
            ).fetchone()
            if not booking:
                conn.rollback()
                return jsonify({'success': False, 'message': 'Booking not found.'}), 404
                
            if user['role'] != 'admin' and booking['user_id'] != user['id']:
                conn.rollback()
                return jsonify({'success': False, 'message': 'Unauthorized to cancel this booking.'}), 403
                
            if user['role'] != 'admin':
                try:
                    booking_date_str = booking['booking_date']
                    start_time_str = booking['start_time']
                    start_dt = datetime.strptime(f"{booking_date_str} {start_time_str}", "%Y-%m-%d %H:%M")
                    
                    if get_local_now() >= start_dt:
                        conn.rollback()
                        return jsonify({'success': False, 'message': 'Cannot cancel a booking after its slot timing has started.'}), 400
                except Exception as e:
                    conn.rollback()
                    return jsonify({'success': False, 'message': 'Error validating booking slot timing.'}), 400
                
            if booking['status'] == 'cancelled':
                conn.rollback()
                return jsonify({'success': False, 'message': 'Booking is already cancelled.'}), 400
                
            payment_method = booking['payment_method']
            if booking['status'] == 'pending_payment':
                conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
                conn.commit()
                return jsonify({
                    'success': True, 
                    'message': 'Pending booking released successfully.',
                    'payment_method': payment_method
                })
            else:
                conn.execute(
                    "UPDATE bookings SET status = 'cancelled', cancelled_at = ? WHERE id = ?", 
                    (get_local_now().strftime('%Y-%m-%d %H:%M:%S'), booking_id)
                )
                conn.commit()
                return jsonify({
                    'success': True, 
                    'message': 'Booking cancelled successfully.',
                    'payment_method': payment_method
                })
            
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()


# --- USER DASHBOARD APIS (History, Queries, Alerts) ---
@app.route('/api/bookings/history', methods=['GET'])
def api_bookings_history():
    authorized, user = login_required()
    if not authorized:
        return jsonify({'success': False, 'message': user}), 401
        
    conn = database.get_db_connection()
    try:
        # Fetch user's bookings joined with court details and slot details
        bookings = conn.execute(
            """
            SELECT b.id as booking_id, b.booking_date, b.num_members, b.total_price, b.status, b.created_at, b.cancelled_at, b.payment_method,
                   c.name as court_name, s.start_time, s.end_time
            FROM bookings b
            JOIN courts c ON b.court_id = c.id
            JOIN slots s ON b.slot_id = s.id
            WHERE b.user_id = ? AND b.status != 'pending_payment'
            ORDER BY b.booking_date DESC, s.start_time ASC
            """, (user['id'],)
        ).fetchall()
        
        # Fetch user's memberships joined with court details and slot details
        memberships = conn.execute(
            """
            SELECT m.id as membership_id, m.start_date, m.end_date, m.duration, m.amount, m.status, m.created_at, m.cancelled_at,
                   c.name as court_name, s.start_time, s.end_time
            FROM memberships m
            JOIN courts c ON m.court_id = c.id
            JOIN slots s ON m.slot_id = s.id
            WHERE m.user_id = ?
            ORDER BY m.start_date DESC, s.start_time ASC
            """, (user['id'],)
        ).fetchall()
        
        history = []
        for b in bookings:
            history.append({
                'booking_id': b['booking_id'],
                'date': b['booking_date'],
                'members': b['num_members'],
                'price': b['total_price'],
                'status': b['status'],
                'created_at': b['created_at'],
                'cancelled_at': b['cancelled_at'],
                'court_name': b['court_name'],
                'time': f"{b['start_time']} - {b['end_time']}",
                'type': 'hourly',
                'duration': '',
                'payment_method': b['payment_method'] or 'online'
            })
            
        for m in memberships:
            history.append({
                'booking_id': 1000000 + m['membership_id'],
                'date': f"{m['start_date']} to {m['end_date']}",
                'members': 1,
                'price': m['amount'],
                'status': m['status'],
                'created_at': m['created_at'],
                'cancelled_at': m['cancelled_at'],
                'court_name': m['court_name'],
                'time': f"{m['start_time']} - {m['end_time']}",
                'type': 'membership',
                'duration': m['duration'],
                'payment_method': 'online'
            })
            
        history.sort(key=lambda x: x['created_at'], reverse=True)
            
        return jsonify({'success': True, 'history': history})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/api/notifications', methods=['GET'])
def api_get_notifications():
    """
    Returns warning alerts for slots starting in less than 30 minutes, 
    and general admin alerts if booking events occur.
    """
    authorized, user = login_required()
    if not authorized:
        return jsonify({'success': False, 'message': user}), 401
        
    conn = database.get_db_connection()
    try:
        # Get active bookings for TODAY for this user
        today_str = get_local_now().strftime('%Y-%m-%d')
        now_time = get_local_now().time()
        
        bookings = conn.execute(
            """
            SELECT b.booking_date, s.start_time, c.name as court_name
            FROM bookings b
            JOIN slots s ON b.slot_id = s.id
            JOIN courts c ON b.court_id = c.id
            WHERE b.user_id = ? AND b.booking_date = ? AND b.status = 'confirmed'
            """, (user['id'], today_str)
        ).fetchall()
        
        alerts = []
        for b in bookings:
            start_dt = datetime.strptime(f"{today_str} {b['start_time']}", "%Y-%m-%d %H:%M")
            time_diff = start_dt - get_local_now()
            
            # If slot starts within 30 minutes and hasn't started yet
            if timedelta(minutes=0) < time_diff <= timedelta(minutes=30):
                minutes_left = int(time_diff.total_seconds() / 60)
                alerts.append({
                    'type': 'warning',
                    'message': f"Reminder: Your booking at {b['court_name']} starts in {minutes_left} minutes ({b['start_time']})!"
                })
                
        # If user is admin, also fetch recent booking events (bookings created in the last 2 hours)
        if user['role'] == 'admin':
            recent_events = conn.execute(
                """
                SELECT b.booking_date, b.status, u.name as user_name, c.name as court_name, s.start_time
                FROM bookings b
                JOIN users u ON b.user_id = u.id
                JOIN courts c ON b.court_id = c.id
                JOIN slots s ON b.slot_id = s.id
                WHERE b.created_at >= NOW() - INTERVAL '2 hours'
                ORDER BY b.created_at DESC
                """
            ).fetchall()
            for r in recent_events:
                action = "booked" if r['status'] == 'confirmed' else "cancelled"
                alerts.append({
                    'type': 'admin_alert',
                    'message': f"Admin Alert: {r['user_name']} {action} {r['court_name']} for {r['booking_date']} at {r['start_time']}."
                })
                
        return jsonify({'success': True, 'alerts': alerts})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/query', methods=['GET', 'POST'])
def api_query():
    authorized, user = login_required()
    if not authorized:
        return jsonify({'success': False, 'message': user}), 401
        
    conn = database.get_db_connection()
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            subject = data.get('subject', '').strip()
            message = data.get('message', '').strip()
            
            if not subject or not message:
                return jsonify({'success': False, 'message': 'Subject and message are required.'}), 400
                
            conn.execute(
                "INSERT INTO queries (user_id, subject, message) VALUES (?, ?, ?)",
                (user['id'], subject, message)
            )
            conn.commit()
            return jsonify({'success': True, 'message': 'Complaint raised successfully!'})
            
        else:
            # GET method: retrieve user's complaints
            queries = conn.execute(
                "SELECT * FROM queries WHERE user_id = ? ORDER BY created_at DESC",
                (user['id'],)
            ).fetchall()
            
            queries_list = []
            for q in queries:
                queries_list.append({
                    'id': q['id'],
                    'subject': q['subject'],
                    'message': q['message'],
                    'reply': q['reply'],
                    'status': q['status'],
                    'created_at': q['created_at']
                })
            return jsonify({'success': True, 'queries': queries_list})
    except Exception as e:
        if request.method == 'POST':
            conn.rollback()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()


# --- ADMIN CONTROL PANEL APIS ---
@app.route('/admin/api/slot', methods=['POST'])
def admin_api_slot():
    authorized, user = login_required('admin')
    if not authorized:
        return jsonify({'success': False, 'message': user}), 403
        
    data = request.get_json() or {}
    court_id = data.get('court_id')
    start_time = data.get('start_time', '').strip()
    end_time = data.get('end_time', '').strip()
    default_price = float(data.get('default_price', 50.0))
    
    if not court_id or not start_time or not end_time:
        return jsonify({'success': False, 'message': 'Court ID, Start Time, and End Time are required.'}), 400
        
    conn = database.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO slots (court_id, start_time, end_time, default_price) VALUES (?, ?, ?, ?)",
            (court_id, start_time, end_time, default_price)
        )
        conn.commit()
        return jsonify({'success': True, 'message': f'New slot {start_time} - {end_time} successfully created!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/admin/api/slot/block', methods=['POST'])
def admin_api_slot_block():
    authorized, user = login_required('admin')
    if not authorized:
        return jsonify({'success': False, 'message': user}), 403
        
    data = request.get_json() or {}
    slot_id = data.get('slot_id')
    block_date = data.get('date', '').strip() # Can be "global" or "YYYY-MM-DD"
    reason = data.get('reason', '').strip() or 'Maintenance'
    is_blocked = data.get('is_blocked') # boolean/int: 1=block, 0=unblock
    
    if not slot_id:
        return jsonify({'success': False, 'message': 'Slot ID is required.'}), 400
        
    conn = database.get_db_connection()
    try:
        if block_date == 'global' or not block_date:
            # Block slot globally in slots table
            conn.execute(
                "UPDATE slots SET is_blocked = ?, blocked_reason = ? WHERE id = ?",
                (is_blocked, reason if is_blocked else None, slot_id)
            )
        else:
            # Block slot for specific date
            if is_blocked:
                conn.execute(
                    """
                    INSERT INTO slot_blocks (slot_id, block_date, reason) VALUES (?, ?, ?)
                    ON CONFLICT (slot_id, block_date) DO UPDATE SET reason = EXCLUDED.reason
                    """,
                    (slot_id, block_date, reason)
                )
            else:
                conn.execute(
                    "DELETE FROM slot_blocks WHERE slot_id = ? AND block_date = ?",
                    (slot_id, block_date)
                )
        conn.commit()
        return jsonify({'success': True, 'message': 'Slot restriction updated successfully!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/admin/api/slot/price', methods=['POST'])
def admin_api_slot_price():
    authorized, user = login_required('admin')
    if not authorized:
        return jsonify({'success': False, 'message': user}), 403
        
    data = request.get_json() or {}
    slot_id = data.get('slot_id')
    date_str = data.get('date', '').strip() # Can be "global" or "YYYY-MM-DD"
    price = float(data.get('price', 0))
    
    if not slot_id or price <= 0:
        return jsonify({'success': False, 'message': 'Valid Slot ID and positive price required.'}), 400
        
    conn = database.get_db_connection()
    try:
        if date_str == 'global' or not date_str:
            # Update default template price
            conn.execute("UPDATE slots SET default_price = ? WHERE id = ?", (price, slot_id))
        else:
            # Create/overwrite override price for specific date
            conn.execute(
                """
                INSERT INTO pricing_overrides (slot_id, override_date, price) VALUES (?, ?, ?)
                ON CONFLICT (slot_id, override_date) DO UPDATE SET price = EXCLUDED.price
                """,
                (slot_id, date_str, price)
            )
        conn.commit()
        return jsonify({'success': True, 'message': 'Slot pricing updated successfully!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/admin/api/queries', methods=['GET'])
def admin_api_get_queries():
    authorized, user = login_required('admin')
    if not authorized:
        return jsonify({'success': False, 'message': user}), 403
        
    conn = database.get_db_connection()
    try:
        queries = conn.execute(
            """
            SELECT q.id, q.subject, q.message, q.reply, q.status, q.created_at, u.name as user_name, u.email as user_email
            FROM queries q
            JOIN users u ON q.user_id = u.id
            ORDER BY q.status ASC, q.created_at DESC
            """
        ).fetchall()
        
        queries_list = []
        for q in queries:
            queries_list.append({
                'id': q['id'],
                'subject': q['subject'],
                'message': q['message'],
                'reply': q['reply'],
                'status': q['status'],
                'created_at': q['created_at'],
                'user_name': q['user_name'],
                'user_email': q['user_email']
            })
        return jsonify({'success': True, 'queries': queries_list})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/admin/api/query/reply', methods=['POST'])
def admin_api_query_reply():
    authorized, user = login_required('admin')
    if not authorized:
        return jsonify({'success': False, 'message': user}), 403
        
    data = request.get_json() or {}
    query_id = data.get('query_id')
    reply = data.get('reply', '').strip()
    
    if not query_id or not reply:
        return jsonify({'success': False, 'message': 'Query ID and reply content required.'}), 400
        
    conn = database.get_db_connection()
    try:
        conn.execute(
            "UPDATE queries SET reply = ?, status = 'resolved' WHERE id = ?",
            (reply, query_id)
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Reply submitted. Query marked as resolved!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/admin/api/bookings', methods=['GET'])
def admin_api_bookings():
    authorized, user = login_required('admin')
    if not authorized:
        return jsonify({'success': False, 'message': user}), 403
        
    conn = database.get_db_connection()
    try:
        # Fetch all active bookings in chronological order
        bookings = conn.execute(
            """
            SELECT b.id, b.booking_date, b.num_members, b.total_price, b.status, b.created_at, b.cancelled_at, b.payment_method,
                   c.name as court_name, s.start_time, s.end_time, u.name as user_name, u.email as user_email, u.mobile as user_mobile
            FROM bookings b
            JOIN courts c ON b.court_id = c.id
            JOIN slots s ON b.slot_id = s.id
            JOIN users u ON b.user_id = u.id
            WHERE b.status != 'pending_payment'
            ORDER BY b.booking_date DESC, s.start_time ASC
            """
        ).fetchall()
        bookings_list = []
        for b in bookings:
            # Check if booking slot has completed (end_time has passed)
            is_completed = False
            if b['status'] == 'confirmed':
                try:
                    start_dt = datetime.strptime(f"{b['booking_date']} {b['start_time']}", "%Y-%m-%d %H:%M")
                    end_dt = datetime.strptime(f"{b['booking_date']} {b['end_time']}", "%Y-%m-%d %H:%M")
                    if end_dt <= start_dt:
                        # Overnight slot
                        end_dt += timedelta(days=1)
                    if get_local_now() >= end_dt:
                        is_completed = True
                except Exception:
                    pass

            bookings_list.append({
                'id': b['id'],
                'date': b['booking_date'],
                'members': str(b['num_members']),
                'price': b['total_price'],
                'status': b['status'],
                'is_completed': is_completed,
                'created_at': b['created_at'],
                'cancelled_at': b['cancelled_at'],
                'court_name': b['court_name'],
                'time_range': f"{b['start_time']} - {b['end_time']}",
                'user_name': b['user_name'],
                'user_email': b['user_email'],
                'user_mobile': b['user_mobile'],
                'payment_method': b['payment_method'] or 'online'
            })
            
        bookings_list.sort(key=lambda x: x['created_at'], reverse=True)
            
        return jsonify({'success': True, 'bookings': bookings_list})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/admin/api/memberships', methods=['GET'])
def admin_api_memberships():
    authorized, user = login_required('admin')
    if not authorized:
        return jsonify({'success': False, 'message': user}), 403
        
    conn = database.get_db_connection()
    try:
        memberships = conn.execute(
            """
            SELECT m.id, m.start_date, m.end_date, m.duration, m.amount, m.status, m.created_at, m.cancelled_at,
                   c.name as court_name, s.start_time, s.end_time, u.name as user_name, u.email as user_email, u.mobile as user_mobile
            FROM memberships m
            JOIN courts c ON m.court_id = c.id
            JOIN slots s ON m.slot_id = s.id
            JOIN users u ON m.user_id = u.id
            ORDER BY m.created_at DESC
            """
        ).fetchall()
        
        result = []
        for m in memberships:
            # Check if membership duration has completed
            is_completed = False
            if m['status'] == 'confirmed':
                try:
                    end_dt = datetime.strptime(m['end_date'], "%Y-%m-%d")
                    if get_local_now().date() > end_dt.date():
                        is_completed = True
                except Exception:
                    pass
            result.append({
                'id': m['id'],
                'start_date': m['start_date'],
                'end_date': m['end_date'],
                'duration': m['duration'],
                'amount': m['amount'],
                'status': m['status'],
                'is_completed': is_completed,
                'created_at': m['created_at'],
                'cancelled_at': m['cancelled_at'],
                'court_name': m['court_name'],
                'time_range': f"{m['start_time']} - {m['end_time']}",
                'user_name': m['user_name'],
                'user_email': m['user_email'],
                'user_mobile': m['user_mobile']
            })
        return jsonify({'success': True, 'memberships': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/admin/api/reports', methods=['GET'])
def admin_api_reports():
    authorized, user = login_required('admin')
    if not authorized:
        return jsonify({'success': False, 'message': user}), 403
        
    conn = database.get_db_connection()
    try:
        # Summary metrics
        total_bookings = conn.execute("SELECT COUNT(*) FROM bookings WHERE status = 'confirmed'").fetchone()[0]
        total_cancellations = conn.execute("SELECT COUNT(*) FROM bookings WHERE status = 'cancelled'").fetchone()[0]
        total_revenue = conn.execute("SELECT SUM(total_price) FROM bookings WHERE status = 'confirmed'").fetchone()[0] or 0.0
        
        # Monthly grouping revenue
        monthly_revenue = conn.execute(
            """
            SELECT to_char(to_date(booking_date, 'YYYY-MM-DD'), 'YYYY-MM') as month, SUM(total_price) as revenue, COUNT(*) as bookings_count
            FROM bookings
            WHERE status = 'confirmed'
            GROUP BY month
            ORDER BY month DESC
            """
        ).fetchall()
        
        # Weekly grouping revenue
        weekly_revenue = conn.execute(
            """
            SELECT to_char(to_date(booking_date, 'YYYY-MM-DD'), 'IYYY-IW') as week, SUM(total_price) as revenue, COUNT(*) as bookings_count
            FROM bookings
            WHERE status = 'confirmed'
            GROUP BY week
            ORDER BY week DESC
            LIMIT 12
            """
        ).fetchall()
        
        reports = {
            'metrics': {
                'total_bookings': total_bookings,
                'total_cancellations': total_cancellations,
                'total_revenue': total_revenue
            },
            'monthly': [{'month': m['month'], 'revenue': m['revenue'], 'bookings': m['bookings_count']} for m in monthly_revenue],
            'weekly': [{'week': m['week'], 'revenue': m['revenue'], 'bookings': m['bookings_count']} for m in weekly_revenue]
        }
        return jsonify({'success': True, 'reports': reports})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    # Bind to 0.0.0.0 and port from environment for Railway deployment
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1']
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
