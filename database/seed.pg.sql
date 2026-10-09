-- Seed data for AI Chatbot Appointment Booking System
-- Run after schema.pg.sql
-- Postgres Version

-- ============================================
-- SAMPLE BUSINESS
-- ============================================
INSERT INTO businesses (id, name, email, phone, address, city, timezone, settings) VALUES 
    ('bus_001', 'AI Scheduler', 'admin@aischeduler.com', '+1-212-555-0100',
     '350 Fifth Avenue, Suite 4200', 'New York', 'America/New_York',
     '{"booking_window_days": 30, "min_notice_hours": 2}')
ON CONFLICT (id) DO UPDATE SET 
    name = EXCLUDED.name,
    email = EXCLUDED.email,
    phone = EXCLUDED.phone,
    address = EXCLUDED.address,
    city = EXCLUDED.city;

-- ============================================
-- SAMPLE USERS
-- ============================================
-- Password for all users: "password123" (valid bcrypt hash with 10 salt rounds)
INSERT INTO users (id, business_id, email, password_hash, first_name, last_name, phone, city, role) VALUES 
    ('usr_admin', 'bus_001', 'admin@aischeduler.com', 
     '$2a$10$JpSZxlTlmnTDZ7oBIcK4XeF7aiwQigFRUY.kPrQOqi67tPiYIGQh2', 
     'Admin', 'User', '+1-555-0100', 'New York', 'admin'),
    ('usr_staff', 'bus_001', 'staff@aischeduler.com', 
     '$2a$10$JpSZxlTlmnTDZ7oBIcK4XeF7aiwQigFRUY.kPrQOqi67tPiYIGQh2', 
     'Staff', 'Member', '+1-555-0101', 'New York', 'staff'),
    ('usr_001', 'bus_001', 'john.doe@email.com', 
     '$2a$10$JpSZxlTlmnTDZ7oBIcK4XeF7aiwQigFRUY.kPrQOqi67tPiYIGQh2', 
     'John', 'Doe', '+1-555-0001', 'New York', 'customer'),
    ('usr_002', 'bus_001', 'jane.smith@email.com', 
     '$2a$10$JpSZxlTlmnTDZ7oBIcK4XeF7aiwQigFRUY.kPrQOqi67tPiYIGQh2', 
     'Jane', 'Smith', '+1-555-0002', 'Los Angeles', 'customer')
ON CONFLICT (email) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    business_id = EXCLUDED.business_id;

-- ============================================
-- SAMPLE SERVICES
-- ============================================
INSERT INTO services (id, business_id, name, description, duration_minutes, price) VALUES 
    ('svc_001', 'bus_001', 'General Consultation', 'Standard consultation with a healthcare provider', 30, 75.00),
    ('svc_002', 'bus_001', 'Extended Consultation', 'Extended consultation for complex cases', 60, 125.00),
    ('svc_003', 'bus_001', 'Follow-up Visit', 'Quick follow-up after initial consultation', 15, 40.00),
    ('svc_004', 'bus_001', 'Wellness Check', 'Comprehensive wellness assessment', 45, 95.00),
    ('svc_005', 'bus_001', 'Physiotherapy Session', 'Physical therapy and rehabilitation session', 45, 90.00),
    ('svc_006', 'bus_001', 'Dental Checkup', 'Routine dental examination and cleaning', 30, 85.00),
    ('svc_007', 'bus_001', 'Mental Health Consultation', 'Counseling and mental health support session', 60, 150.00),
    ('svc_008', 'bus_001', 'Specialist Referral', 'Quick referral consultation with a specialist', 20, 50.00);

-- ============================================
-- SAMPLE PROVIDERS (Doctors, Therapists, etc.)
-- ============================================
INSERT INTO providers (id, business_id, name, specialty, bio, city, address, phone, email) VALUES
    ('prv_001', 'bus_001', 'Dr. Emily Smith', 'General Practice',
     'Board-certified family physician with 12 years of experience in primary care.',
     'New York', '350 Fifth Avenue, Suite 4210', '+1-212-555-0201', 'e.smith@aischeduler.com'),
    ('prv_002', 'bus_001', 'Dr. Sarah Chen', 'Therapy',
     'Licensed clinical psychologist specializing in anxiety, depression, and stress management.',
     'New York', '350 Fifth Avenue, Suite 4220', '+1-212-555-0202', 's.chen@aischeduler.com'),
    ('prv_003', 'bus_001', 'Dr. Carlos Martinez', 'Cognitive Behavioral Therapy',
     'CBT specialist with expertise in trauma recovery and behavioral health.',
     'Los Angeles', '9100 Wilshire Blvd, Suite 300', '+1-310-555-0301', 'c.martinez@aischeduler.com'),
    ('prv_004', 'bus_001', 'Dr. James Johnson', 'Dentistry',
     'General dentist providing preventive care, restorations, and cosmetic dentistry.',
     'Los Angeles', '9100 Wilshire Blvd, Suite 310', '+1-310-555-0302', 'j.johnson@aischeduler.com')
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    specialty = EXCLUDED.specialty;

-- ============================================
-- PROVIDER-SERVICE MAPPINGS
-- ============================================
INSERT INTO provider_services (provider_id, service_id, business_id, is_active) VALUES
    ('prv_001', 'svc_001', 'bus_001', 1),
    ('prv_001', 'svc_002', 'bus_001', 1),
    ('prv_002', 'svc_007', 'bus_001', 1),
    ('prv_002', 'svc_004', 'bus_001', 1),
    ('prv_003', 'svc_007', 'bus_001', 1),
    ('prv_003', 'svc_004', 'bus_001', 1),
    ('prv_004', 'svc_006', 'bus_001', 1)
ON CONFLICT (provider_id, service_id) DO UPDATE SET
    is_active = EXCLUDED.is_active;

-- ============================================
-- SAMPLE AVAILABILITY (Business Hours)
-- ============================================
-- Monday to Friday: 9:00 AM - 9:00 PM
INSERT INTO availability (id, business_id, day_of_week, start_time, end_time) VALUES 
    ('avl_mon', 'bus_001', 1, '09:00', '21:00'),
    ('avl_tue', 'bus_001', 2, '09:00', '21:00'),
    ('avl_wed', 'bus_001', 3, '09:00', '21:00'),
    ('avl_thu', 'bus_001', 4, '09:00', '21:00'),
    ('avl_fri', 'bus_001', 5, '09:00', '21:00'),
    ('avl_sat', 'bus_001', 6, '10:00', '18:00');  -- Saturday: limited evening hours

-- ============================================
-- SAMPLE APPOINTMENTS
-- ============================================
INSERT INTO appointments (id, business_id, user_id, service_id, provider_id, start_time, end_time, status, notes) VALUES 
    ('apt_001', 'bus_001', 'usr_001', 'svc_001', 'prv_001',
     (DATE_TRUNC('day', NOW() + INTERVAL '1 day') + INTERVAL '10 hours'), 
     (DATE_TRUNC('day', NOW() + INTERVAL '1 day') + INTERVAL '10 hours 30 minutes'), 
     'confirmed', 'First visit'),
    ('apt_002', 'bus_001', 'usr_002', 'svc_007', 'prv_002',
     (DATE_TRUNC('day', NOW() + INTERVAL '2 days') + INTERVAL '14 hours'), 
     (DATE_TRUNC('day', NOW() + INTERVAL '2 days') + INTERVAL '15 hours'), 
     'pending', 'Needs insurance verification');

-- ============================================
-- SAMPLE CHAT SESSION
-- ============================================
INSERT INTO chat_sessions (id, user_id, business_id, status, intent, outcome) VALUES 
    ('sess_001', 'usr_001', 'bus_001', 'completed', 'booking', 'booked');

INSERT INTO chat_messages (id, session_id, role, content) VALUES 
    ('msg_001', 'sess_001', 'user', 'Hi, I would like to book an appointment'),
    ('msg_002', 'sess_001', 'assistant', 'Hello! I''d be happy to help you book an appointment. What type of service are you looking for?'),
    ('msg_003', 'sess_001', 'user', 'A general consultation please'),
    ('msg_004', 'sess_001', 'assistant', 'Great choice! When would you prefer to come in? We have availability this week.');
