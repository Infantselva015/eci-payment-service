-- Payment Service Database Schema with Seed Data

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
    gateway_response VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
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

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
CREATE INDEX IF NOT EXISTS idx_payments_transaction_id ON payments(transaction_id);
CREATE INDEX IF NOT EXISTS idx_transactions_payment_id ON transactions(payment_id);

-- Insert sample payment data
INSERT INTO payments (order_id, user_id, amount, currency, payment_method, status, transaction_id, gateway_response, created_at, updated_at, completed_at) VALUES
(1001, 101, 1299.00, 'INR', 'CREDIT_CARD', 'COMPLETED', 'TXN1234567890', 'Payment successful', '2025-10-25 10:00:00', '2025-10-25 10:01:00', '2025-10-25 10:01:00'),
(1002, 102, 2499.00, 'INR', 'UPI', 'COMPLETED', 'TXN1234567891', 'Payment successful', '2025-10-25 11:00:00', '2025-10-25 11:00:30', '2025-10-25 11:00:30'),
(1003, 103, 799.00, 'INR', 'DEBIT_CARD', 'COMPLETED', 'TXN1234567892', 'Payment successful', '2025-10-26 09:30:00', '2025-10-26 09:30:45', '2025-10-26 09:30:45'),
(1004, 104, 3599.00, 'INR', 'NET_BANKING', 'COMPLETED', 'TXN1234567893', 'Payment successful', '2025-10-26 14:15:00', '2025-10-26 14:16:00', '2025-10-26 14:16:00'),
(1005, 105, 1899.00, 'INR', 'WALLET', 'COMPLETED', 'TXN1234567894', 'Payment successful', '2025-10-27 10:00:00', '2025-10-27 10:00:20', '2025-10-27 10:00:20'),
(1006, 106, 4299.00, 'INR', 'CREDIT_CARD', 'COMPLETED', 'TXN1234567895', 'Payment successful', '2025-10-27 15:30:00', '2025-10-27 15:31:00', '2025-10-27 15:31:00'),
(1007, 107, 999.00, 'INR', 'UPI', 'PROCESSING', 'TXN1234567896', 'Payment in progress', '2025-10-28 11:00:00', '2025-10-28 11:00:15', NULL),
(1008, 108, 5499.00, 'INR', 'CREDIT_CARD', 'PROCESSING', 'TXN1234567897', 'Payment in progress', '2025-10-28 16:20:00', '2025-10-28 16:20:10', NULL),
(1009, 109, 1599.00, 'INR', 'DEBIT_CARD', 'PENDING', 'TXN1234567898', NULL, '2025-10-29 10:45:00', '2025-10-29 10:45:00', NULL),
(1010, 110, 2299.00, 'INR', 'NET_BANKING', 'PENDING', 'TXN1234567899', NULL, '2025-10-29 14:00:00', '2025-10-29 14:00:00', NULL),
(1011, 111, 699.00, 'INR', 'UPI', 'FAILED', 'TXN1234567900', 'Insufficient balance', '2025-10-30 09:00:00', '2025-10-30 09:00:30', NULL),
(1012, 112, 3899.00, 'INR', 'CREDIT_CARD', 'FAILED', 'TXN1234567901', 'Card declined', '2025-10-30 12:30:00', '2025-10-30 12:30:45', NULL),
(1013, 113, 1199.00, 'INR', 'WALLET', 'REFUNDED', 'TXN1234567902', 'Refund: Customer request', '2025-10-28 10:00:00', '2025-10-30 15:00:00', '2025-10-28 10:01:00'),
(1014, 114, 2799.00, 'INR', 'UPI', 'REFUNDED', 'TXN1234567903', 'Refund: Product defective', '2025-10-27 14:00:00', '2025-10-30 16:00:00', '2025-10-27 14:00:30'),
(1015, 115, 899.00, 'INR', 'DEBIT_CARD', 'CANCELLED', 'TXN1234567904', NULL, '2025-10-31 08:00:00', '2025-10-31 08:05:00', NULL),
(1016, 116, 4599.00, 'INR', 'CREDIT_CARD', 'COMPLETED', 'TXN1234567905', 'Payment successful', '2025-10-29 11:00:00', '2025-10-29 11:01:00', '2025-10-29 11:01:00'),
(1017, 117, 1499.00, 'INR', 'UPI', 'COMPLETED', 'TXN1234567906', 'Payment successful', '2025-10-30 10:30:00', '2025-10-30 10:30:25', '2025-10-30 10:30:25'),
(1018, 118, 2999.00, 'INR', 'NET_BANKING', 'COMPLETED', 'TXN1234567907', 'Payment successful', '2025-10-30 15:00:00', '2025-10-30 15:01:00', '2025-10-30 15:01:00'),
(1019, 119, 599.00, 'INR', 'WALLET', 'PENDING', 'TXN1234567908', NULL, '2025-10-31 09:00:00', '2025-10-31 09:00:00', NULL),
(1020, 120, 3299.00, 'INR', 'CREDIT_CARD', 'PROCESSING', 'TXN1234567909', 'Payment in progress', '2025-10-31 11:00:00', '2025-10-31 11:00:10', NULL);

-- Insert sample transaction logs
INSERT INTO transactions (payment_id, transaction_type, amount, status, description, created_at) VALUES
(1, 'PAYMENT', 1299.00, 'PENDING', 'Payment initiated via CREDIT_CARD', '2025-10-25 10:00:00'),
(1, 'PAYMENT', 1299.00, 'COMPLETED', 'Status changed from PENDING to COMPLETED', '2025-10-25 10:01:00'),
(2, 'PAYMENT', 2499.00, 'PENDING', 'Payment initiated via UPI', '2025-10-25 11:00:00'),
(2, 'PAYMENT', 2499.00, 'COMPLETED', 'Status changed from PENDING to COMPLETED', '2025-10-25 11:00:30'),
(3, 'PAYMENT', 799.00, 'PENDING', 'Payment initiated via DEBIT_CARD', '2025-10-26 09:30:00'),
(3, 'PAYMENT', 799.00, 'COMPLETED', 'Status changed from PENDING to COMPLETED', '2025-10-26 09:30:45'),
(7, 'PAYMENT', 999.00, 'PENDING', 'Payment initiated via UPI', '2025-10-28 11:00:00'),
(7, 'PAYMENT', 999.00, 'PROCESSING', 'Status changed from PENDING to PROCESSING', '2025-10-28 11:00:15'),
(11, 'PAYMENT', 699.00, 'PENDING', 'Payment initiated via UPI', '2025-10-30 09:00:00'),
(11, 'PAYMENT', 699.00, 'FAILED', 'Status changed from PENDING to FAILED', '2025-10-30 09:00:30'),
(13, 'PAYMENT', 1199.00, 'PENDING', 'Payment initiated via WALLET', '2025-10-28 10:00:00'),
(13, 'PAYMENT', 1199.00, 'COMPLETED', 'Status changed from PENDING to COMPLETED', '2025-10-28 10:01:00'),
(13, 'REFUND', 1199.00, 'REFUNDED', 'Refund of 1199.0 INR: Customer request', '2025-10-30 15:00:00'),
(15, 'PAYMENT', 899.00, 'PENDING', 'Payment initiated via DEBIT_CARD', '2025-10-31 08:00:00'),
(15, 'PAYMENT', 899.00, 'CANCELLED', 'Payment cancelled by user', '2025-10-31 08:05:00');
