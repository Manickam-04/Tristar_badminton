-- PostgreSQL Database Schema for Tristar Badminton Academy

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    mobile VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'user', -- 'user' or 'admin'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Courts Table
CREATE TABLE IF NOT EXISTS courts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    image_url VARCHAR(255),
    is_active INTEGER DEFAULT 1 -- 1 = active, 0 = inactive
);

-- Slots Table (Templates for court hours)
CREATE TABLE IF NOT EXISTS slots (
    id SERIAL PRIMARY KEY,
    court_id INTEGER NOT NULL,
    start_time VARCHAR(20) NOT NULL, -- e.g., '06:00'
    end_time VARCHAR(20) NOT NULL,   -- e.g., '07:00'
    default_price DOUBLE PRECISION NOT NULL DEFAULT 500.0,
    is_blocked INTEGER DEFAULT 0, -- 1 = blocked globally, 0 = active
    blocked_reason TEXT,
    FOREIGN KEY(court_id) REFERENCES courts(id) ON DELETE CASCADE
);

-- Bookings Table (Stores actual booked dates)
CREATE TABLE IF NOT EXISTS bookings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    court_id INTEGER NOT NULL,
    slot_id INTEGER NOT NULL,
    booking_date VARCHAR(20) NOT NULL, -- 'YYYY-MM-DD'
    num_slots INTEGER NOT NULL DEFAULT 1,
    num_members INTEGER NOT NULL DEFAULT 1,
    total_price DOUBLE PRECISION NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'confirmed', -- 'confirmed' or 'cancelled'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cancelled_at VARCHAR(50),
    payment_method VARCHAR(50) DEFAULT 'online',
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(court_id) REFERENCES courts(id),
    FOREIGN KEY(slot_id) REFERENCES slots(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_unique_confirmed ON bookings(court_id, slot_id, booking_date) WHERE status = 'confirmed';

-- Pricing Overrides Table (Admin can change pricing for specific dates/slots)
CREATE TABLE IF NOT EXISTS pricing_overrides (
    id SERIAL PRIMARY KEY,
    slot_id INTEGER NOT NULL,
    override_date VARCHAR(20) NOT NULL, -- 'YYYY-MM-DD'
    price DOUBLE PRECISION NOT NULL,
    FOREIGN KEY(slot_id) REFERENCES slots(id) ON DELETE CASCADE,
    UNIQUE(slot_id, override_date)
);

-- Slots Blocked for specific dates (Admin can block slots on specific days)
CREATE TABLE IF NOT EXISTS slot_blocks (
    id SERIAL PRIMARY KEY,
    slot_id INTEGER NOT NULL,
    block_date VARCHAR(20) NOT NULL, -- 'YYYY-MM-DD'
    reason TEXT,
    FOREIGN KEY(slot_id) REFERENCES slots(id) ON DELETE CASCADE,
    UNIQUE(slot_id, block_date)
);

-- Queries/Complaints Table
CREATE TABLE IF NOT EXISTS queries (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    subject VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    reply TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- 'pending' or 'resolved'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

-- Memberships Table (Stores block bookings/subscriptions)
CREATE TABLE IF NOT EXISTS memberships (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    court_id INTEGER NOT NULL,
    slot_id INTEGER NOT NULL,
    start_date VARCHAR(20) NOT NULL, -- 'YYYY-MM-DD'
    end_date VARCHAR(20) NOT NULL,   -- 'YYYY-MM-DD' (start_date + duration)
    duration VARCHAR(50) NOT NULL,   -- '1 Month', '3 Months', '6 Months', '1 Year'
    amount DOUBLE PRECISION NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'confirmed', -- 'confirmed' or 'cancelled'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cancelled_at VARCHAR(50),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(court_id) REFERENCES courts(id),
    FOREIGN KEY(slot_id) REFERENCES slots(id)
);
