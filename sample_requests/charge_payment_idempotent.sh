#!/bin/bash

# Test idempotent payment charge with same Idempotency-Key
# Both requests should return the same payment_id

IDEMPOTENCY_KEY="test-key-$(date +%s)"

echo "First request with Idempotency-Key: $IDEMPOTENCY_KEY"
curl -X POST "http://localhost:8086/v1/payments/charge" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
  -d '{
    "order_id": 9001,
    "user_id": 701,
    "amount": 1999.99,
    "currency": "INR",
    "payment_method": "UPI"
  }' | jq .

echo -e "\n\nSecond request with SAME Idempotency-Key: $IDEMPOTENCY_KEY"
echo "Should return the same payment_id without creating a new payment"
curl -X POST "http://localhost:8086/v1/payments/charge" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
  -d '{
    "order_id": 9001,
    "user_id": 701,
    "amount": 1999.99,
    "currency": "INR",
    "payment_method": "UPI"
  }' | jq .
