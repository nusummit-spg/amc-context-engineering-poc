-- ===========================================================================
-- SQL seed script: Create Compliance & Regulatory Officer user
-- ===========================================================================
-- 
-- This script inserts a Compliance & Regulatory Officer user into the
-- auth_users table.
--
-- Usage:
--   sqlite3 data.db < seed_compliance_officer.sql
--   OR
--   psql -d amc_db -f seed_compliance_officer.sql
--

-- Delete if exists (optional - comment out for safety)
-- DELETE FROM auth_users WHERE username = 'compliance_officer';

-- Create the Compliance Officer user
INSERT INTO auth_users (
    username,
    password_hash,
    display_name,
    email,
    role,
    department,
    avatar_initials,
    status,
    tenant_id,
    created_at,
    updated_at,
    is_superuser,
    last_login,
    last_login_ip
) VALUES (
    'compliance_officer',
    'pbkdf2_sha256$260000$52a5b1dfcd28274230cf2f4d5e23eb16$171fd0d36b213661b2588d135faf3c5b977642e8720e1067d63ba55aed5a6f9d',
    'Compliance Officer',
    'compliance@amc.com',
    'Compliance & Regulatory Officer',
    'Regulatory & Legal Compliance',
    'CO',
    'Active',
    NULL,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    0,
    NULL,
    NULL
);

-- Verify the user was created
SELECT 'User created successfully' as status;
SELECT username, display_name, role, status FROM auth_users WHERE username = 'compliance_officer';

-- Notes:
-- Password is: Compliance@2026
-- The password_hash above matches "Compliance@2026" hashed with PBKDF2-SHA256
-- You can verify by logging in with username=compliance_officer, password=Compliance@2026
