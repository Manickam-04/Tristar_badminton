import os
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
    return render_template('login.html')

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
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    mobile = data.get('mobile', '').strip()
    password = data.get('password', '')
    name = data.get('name', '').strip()
    
    if not email or not mobile or not password or not name:
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400
        
    conn = database.get_db_connection()
    try:
        # Check if user exists with same email or mobile
        exists = conn.execute("SELECT id FROM users WHERE email = ? OR mobile = ?", (email, mobile)).fetchone()
        if exists:
            return jsonify({'success': False, 'message': 'Email or Mobile number already registered.'}), 400
            
        hashed_password = generate_password_hash(password)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (email, mobile, password_hash, name, role) VALUES (?, ?, ?, ?, 'user')",
            (email, mobile, hashed_password, name)
        )
        conn.commit()
        
        # Log them in automatically
        user_id = cursor.lastrowid
        session['user_id'] = user_id
        session['email'] = email
        session['name'] = name
        session['role'] = 'user'
        session.permanent = True
        
        return jsonify({'success': True, 'message': 'Registration successful!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    identity = data.get('email', '').strip() # Accept email or mobile
    password = data.get('password', '')
    as_role = data.get('role', 'user') # 'user' or 'admin'
    remember = data.get('remember', False)
    
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
    data = request.get_json() or {}
    identity = data.get('identity', '').strip()
    new_password = data.get('new_password', '')
    
    if not identity or not new_password:
        return jsonify({'success': False, 'message': 'Identity and new password are required.'}), 400
        
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters.'}), 400
        
    conn = database.get_db_connection()
    try:
        user = conn.execute("SELECT id FROM users WHERE LOWER(email) = ? OR mobile = ?", (identity.lower(), identity)).fetchone()
        if not user:
            return jsonify({'success': False, 'message': 'User with this Email/Mobile number does not exist.'}), 404
            
        hashed_pw = generate_password_hash(new_password)
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed_pw, user['id']))
        conn.commit()
        return jsonify({'success': True, 'message': 'Password reset successfully!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    finally:
        conn.close()

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
        
        # Fetch confirmed bookings for this date and court
        bookings_rows = conn.execute(
            "SELECT * FROM bookings WHERE court_id = ? AND booking_date = ? AND status = 'confirmed'",
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
                
                # Fetch name of the user who booked
                booker_id = booking['user_id']
                if user_or_err and booker_id == user_or_err['id']:
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
    
    if not court_id or not slot_id or not date_str:
        return jsonify({'success': False, 'message': 'Court ID, Slot ID, and Date are required.'}), 400
        
    # Validate date
    try:
        booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        if booking_date < get_local_today():
            return jsonify({'success': False, 'message': 'Cannot book slots in the past.'}), 400
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid date format.'}), 400
        
    conn = database.get_db_connection()
    try:
        # Start isolated immediate lock
        conn.execute("BEGIN IMMEDIATE TRANSACTION;")
        
        # 1. Verify if slot is globally or specifically blocked
        slot = conn.execute("SELECT * FROM slots WHERE id = ? AND court_id = ?", (slot_id, court_id)).fetchone()
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
            "SELECT id FROM bookings WHERE court_id = ? AND slot_id = ? AND booking_date = ? AND status = 'confirmed'",
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
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO bookings (user_id, court_id, slot_id, booking_date, num_slots, num_members, total_price, status) VALUES (?, ?, ?, ?, 1, ?, ?, 'confirmed')",
            (user['id'], court_id, slot_id, date_str, num_members, total_price)
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
                'total_price': total_price
            }
        })
    except Exception as e:
        conn.rollback()
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
        
        slot = conn.execute("SELECT * FROM slots WHERE id = ? AND court_id = ?", (slot_id, court_id)).fetchone()
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
    authorized, user = login_required()
    if not authorized:
        return jsonify({'success': False, 'message': user}), 401
        
    data = request.get_json() or {}
    booking_id = data.get('booking_id')
    
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
                
            conn.execute("UPDATE memberships SET status = 'cancelled' WHERE id = ?", (membership_id,))
            conn.commit()
            return jsonify({'success': True, 'message': 'Membership subscription cancelled successfully.'})
            
        else:
            # Cancel hourly booking
            booking = conn.execute(
                """
                SELECT b.*, s.start_time, s.end_time
                FROM bookings b
                JOIN slots s ON b.slot_id = s.id
                WHERE b.id = ?
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
                
            conn.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
            conn.commit()
            return jsonify({'success': True, 'message': 'Booking cancelled successfully.'})
            
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
            SELECT b.id as booking_id, b.booking_date, b.num_members, b.total_price, b.status, b.created_at,
                   c.name as court_name, s.start_time, s.end_time
            FROM bookings b
            JOIN courts c ON b.court_id = c.id
            JOIN slots s ON b.slot_id = s.id
            WHERE b.user_id = ?
            ORDER BY b.booking_date DESC, s.start_time ASC
            """, (user['id'],)
        ).fetchall()
        
        # Fetch user's memberships joined with court details and slot details
        memberships = conn.execute(
            """
            SELECT m.id as membership_id, m.start_date, m.end_date, m.duration, m.amount, m.status, m.created_at,
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
                'court_name': b['court_name'],
                'time': f"{b['start_time']} - {b['end_time']}",
                'type': 'hourly',
                'duration': ''
            })
            
        for m in memberships:
            history.append({
                'booking_id': 1000000 + m['membership_id'],
                'date': f"{m['start_date']} to {m['end_date']}",
                'members': 1,
                'price': m['amount'],
                'status': m['status'],
                'created_at': m['created_at'],
                'court_name': m['court_name'],
                'time': f"{m['start_time']} - {m['end_time']}",
                'type': 'membership',
                'duration': m['duration']
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
                WHERE b.created_at >= datetime('now', '-2 hour')
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
                    "INSERT OR REPLACE INTO slot_blocks (slot_id, block_date, reason) VALUES (?, ?, ?)",
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
                "INSERT OR REPLACE INTO pricing_overrides (slot_id, override_date, price) VALUES (?, ?, ?)",
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
            SELECT b.id, b.booking_date, b.num_members, b.total_price, b.status, b.created_at,
                   c.name as court_name, s.start_time, s.end_time, u.name as user_name, u.email as user_email, u.mobile as user_mobile
            FROM bookings b
            JOIN courts c ON b.court_id = c.id
            JOIN slots s ON b.slot_id = s.id
            JOIN users u ON b.user_id = u.id
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
                'court_name': b['court_name'],
                'time_range': f"{b['start_time']} - {b['end_time']}",
                'user_name': b['user_name'],
                'user_email': b['user_email'],
                'user_mobile': b['user_mobile']
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
            SELECT m.id, m.start_date, m.end_date, m.duration, m.amount, m.status, m.created_at,
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
            SELECT strftime('%Y-%m', booking_date) as month, SUM(total_price) as revenue, COUNT(*) as bookings_count
            FROM bookings
            WHERE status = 'confirmed'
            GROUP BY month
            ORDER BY month DESC
            """
        ).fetchall()
        
        # Weekly grouping revenue
        weekly_revenue = conn.execute(
            """
            SELECT strftime('%Y-%W', booking_date) as week, SUM(total_price) as revenue, COUNT(*) as bookings_count
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
