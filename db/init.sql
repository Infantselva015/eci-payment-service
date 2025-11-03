-- Payment Service Database Schema

-- Create payments table
CREATE TABLE IF NOT EXISTS payments (
    payment_id SERIAL PRIMARY KEY,
    order_id INTEGER UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'INR',
    payment_method VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'PENDING',
    transaction_id VARCHAR(50) UNIQUE,
    reference VARCHAR(100),
    authorization_code VARCHAR(50),
    gateway_response VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    captured_at TIMESTAMP
);

-- Create transactions table
CREATE TABLE IF NOT EXISTS transactions (
    transaction_log_id SERIAL PRIMARY KEY,
    payment_id INTEGER NOT NULL REFERENCES payments(payment_id) ON DELETE CASCADE,
    transaction_type VARCHAR(20) NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    description VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create idempotency_keys table (REQUIRED by assignment)
CREATE TABLE IF NOT EXISTS idempotency_keys (
    id SERIAL PRIMARY KEY,
    idempotency_key VARCHAR(255) UNIQUE NOT NULL,
    payment_id INTEGER REFERENCES payments(payment_id),
    request_hash VARCHAR(64) NOT NULL,
    response_body TEXT,
    status_code INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

-- Create indexes for payments table
CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
CREATE INDEX IF NOT EXISTS idx_payments_transaction_id ON payments(transaction_id);
CREATE INDEX IF NOT EXISTS idx_payments_reference ON payments(reference);

-- Create indexes for transactions table
CREATE INDEX IF NOT EXISTS idx_transactions_payment_id ON transactions(payment_id);

-- Create indexes for idempotency_keys table
CREATE INDEX IF NOT EXISTS idx_idempotency_key ON idempotency_keys(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_idempotency_expires ON idempotency_keys(expires_at);

-- Add comments
COMMENT ON TABLE payments IS 'Stores payment records for orders';
COMMENT ON TABLE transactions IS 'Audit trail of all payment transactions';
COMMENT ON TABLE idempotency_keys IS 'Ensures idempotent payment operations - prevents duplicate charges';
COMMENT ON COLUMN payments.reference IS 'External payment reference (e.g., invoice number, gateway reference)';
COMMENT ON COLUMN idempotency_keys.idempotency_key IS 'Client-provided key to ensure idempotent operations';
COMMENT ON COLUMN idempotency_keys.expires_at IS 'Idempotency keys expire after 24 hours';
