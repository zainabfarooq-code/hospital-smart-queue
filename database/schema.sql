-- ============================================================
-- AI HOSPITAL MANAGEMENT & SMART QUEUE MANAGEMENT SYSTEM
-- PostgreSQL / Supabase
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ============================================================
-- ENUM TYPES
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type
        WHERE typname = 'user_role'
    ) THEN
        CREATE TYPE user_role AS ENUM (
            'patient',
            'doctor',
            'admin'
        );
    END IF;
END
$$;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type
        WHERE typname = 'appointment_status'
    ) THEN
        CREATE TYPE appointment_status AS ENUM (
            'scheduled',
            'checked_in',
            'in_queue',
            'in_progress',
            'completed',
            'cancelled',
            'no_show'
        );
    END IF;
END
$$;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type
        WHERE typname = 'queue_status'
    ) THEN
        CREATE TYPE queue_status AS ENUM (
            'waiting',
            'called',
            'serving',
            'completed',
            'skipped',
            'cancelled'
        );
    END IF;
END
$$;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type
        WHERE typname = 'queue_event_type'
    ) THEN
        CREATE TYPE queue_event_type AS ENUM (
            'created',
            'called',
            'started',
            'completed',
            'skipped',
            'cancelled'
        );
    END IF;
END
$$;


-- ============================================================
-- USERS
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    email VARCHAR(255) NOT NULL UNIQUE,

    password_hash TEXT NOT NULL,

    role user_role NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email
ON users(email);

CREATE INDEX IF NOT EXISTS idx_users_role
ON users(role);


-- ============================================================
-- DEPARTMENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS departments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    name VARCHAR(100) NOT NULL UNIQUE,

    description TEXT,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================
-- PATIENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS patients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL UNIQUE,

    full_name VARCHAR(150) NOT NULL,

    phone VARCHAR(30),

    date_of_birth DATE,

    gender VARCHAR(30),

    address TEXT,

    emergency_contact VARCHAR(150),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_patients_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_patients_user_id
ON patients(user_id);


-- ============================================================
-- DOCTORS
-- ============================================================

CREATE TABLE IF NOT EXISTS doctors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL UNIQUE,

    department_id UUID NOT NULL,

    full_name VARCHAR(150) NOT NULL,

    specialization VARCHAR(150),

    license_number VARCHAR(100),

    consultation_duration_minutes INTEGER NOT NULL DEFAULT 15,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_doctors_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_doctors_department
        FOREIGN KEY (department_id)
        REFERENCES departments(id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_doctors_consultation_duration
        CHECK (consultation_duration_minutes > 0)
);

CREATE INDEX IF NOT EXISTS idx_doctors_department
ON doctors(department_id);

CREATE INDEX IF NOT EXISTS idx_doctors_user
ON doctors(user_id);


-- ============================================================
-- DOCTOR SCHEDULES
-- ============================================================

CREATE TABLE IF NOT EXISTS doctor_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    doctor_id UUID NOT NULL,

    day_of_week SMALLINT NOT NULL,

    start_time TIME NOT NULL,

    end_time TIME NOT NULL,

    slot_duration_minutes INTEGER NOT NULL DEFAULT 15,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_doctor_schedules_doctor
        FOREIGN KEY (doctor_id)
        REFERENCES doctors(id)
        ON DELETE CASCADE,

    CONSTRAINT chk_doctor_schedules_day
        CHECK (day_of_week BETWEEN 0 AND 6),

    CONSTRAINT chk_doctor_schedules_time
        CHECK (end_time > start_time),

    CONSTRAINT chk_doctor_schedules_slot
        CHECK (slot_duration_minutes > 0)
);

CREATE INDEX IF NOT EXISTS idx_doctor_schedules_doctor_day
ON doctor_schedules(doctor_id, day_of_week);


-- ============================================================
-- APPOINTMENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    patient_id UUID NOT NULL,

    doctor_id UUID NOT NULL,

    department_id UUID NOT NULL,

    appointment_date DATE NOT NULL,

    appointment_time TIME NOT NULL,

    status appointment_status NOT NULL DEFAULT 'scheduled',

    reason TEXT,

    booked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    checked_in_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    cancelled_at TIMESTAMPTZ,

    CONSTRAINT fk_appointments_patient
        FOREIGN KEY (patient_id)
        REFERENCES patients(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_appointments_doctor
        FOREIGN KEY (doctor_id)
        REFERENCES doctors(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_appointments_department
        FOREIGN KEY (department_id)
        REFERENCES departments(id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_appointments_patient
ON appointments(patient_id);

CREATE INDEX IF NOT EXISTS idx_appointments_doctor_date
ON appointments(doctor_id, appointment_date);

CREATE INDEX IF NOT EXISTS idx_appointments_status
ON appointments(status);


-- ============================================================
-- QUEUES
-- ============================================================

CREATE TABLE IF NOT EXISTS queues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    appointment_id UUID NOT NULL UNIQUE,

    doctor_id UUID NOT NULL,

    queue_date DATE NOT NULL,

    token_number INTEGER NOT NULL,

    status queue_status NOT NULL DEFAULT 'waiting',

    check_in_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    called_at TIMESTAMPTZ,

    service_started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    skipped_at TIMESTAMPTZ,

    cancelled_at TIMESTAMPTZ,

    CONSTRAINT fk_queues_appointment
        FOREIGN KEY (appointment_id)
        REFERENCES appointments(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_queues_doctor
        FOREIGN KEY (doctor_id)
        REFERENCES doctors(id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_queues_token
        CHECK (token_number > 0),

    CONSTRAINT uq_queue_doctor_date_token
        UNIQUE (doctor_id, queue_date, token_number)
);

CREATE INDEX IF NOT EXISTS idx_queues_doctor_date
ON queues(doctor_id, queue_date);

CREATE INDEX IF NOT EXISTS idx_queues_status
ON queues(status);


-- ============================================================
-- QUEUE EVENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS queue_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    queue_id UUID NOT NULL,

    event_type queue_event_type NOT NULL,

    event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    performed_by UUID,

    notes TEXT,

    CONSTRAINT fk_queue_events_queue
        FOREIGN KEY (queue_id)
        REFERENCES queues(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_queue_events_user
        FOREIGN KEY (performed_by)
        REFERENCES users(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_queue_events_queue
ON queue_events(queue_id);

CREATE INDEX IF NOT EXISTS idx_queue_events_time
ON queue_events(event_time);


-- ============================================================
-- PREDICTIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    appointment_id UUID NOT NULL,

    queue_id UUID,

    model_version VARCHAR(100) NOT NULL,

    queue_length INTEGER NOT NULL,

    patients_ahead INTEGER NOT NULL,

    appointment_hour INTEGER NOT NULL,

    day_of_week INTEGER NOT NULL,

    consultation_duration_minutes INTEGER NOT NULL,

    arrival_delay_minutes INTEGER NOT NULL DEFAULT 0,

    predicted_wait_minutes NUMERIC(8, 2) NOT NULL,

    actual_wait_minutes NUMERIC(8, 2),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_predictions_appointment
        FOREIGN KEY (appointment_id)
        REFERENCES appointments(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_predictions_queue
        FOREIGN KEY (queue_id)
        REFERENCES queues(id)
        ON DELETE SET NULL,

    CONSTRAINT chk_predictions_queue_length
        CHECK (queue_length >= 0),

    CONSTRAINT chk_predictions_patients_ahead
        CHECK (patients_ahead >= 0),

    CONSTRAINT chk_predictions_hour
        CHECK (appointment_hour BETWEEN 0 AND 23),

    CONSTRAINT chk_predictions_day
        CHECK (day_of_week BETWEEN 0 AND 6),

    CONSTRAINT chk_predictions_consultation
        CHECK (consultation_duration_minutes > 0),

    CONSTRAINT chk_predictions_delay
        CHECK (arrival_delay_minutes >= 0),

    CONSTRAINT chk_predictions_wait
        CHECK (predicted_wait_minutes >= 0)
);

CREATE INDEX IF NOT EXISTS idx_predictions_appointment
ON predictions(appointment_id);

CREATE INDEX IF NOT EXISTS idx_predictions_created
ON predictions(created_at);