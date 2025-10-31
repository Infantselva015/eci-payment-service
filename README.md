# Payment Service - ECI Microservices

## Overview
The Payment Service handles payment processing, transaction management, and refunds for the E-commerce with Inventory (ECI) platform.

## Features
- ✅ Process payments for orders
- ✅ Support multiple payment methods (Credit Card, Debit Card, UPI, Net Banking, Wallet, COD)
- ✅ Track payment status lifecycle
- ✅ Process refunds (full and partial)
- ✅ Transaction history and audit trail
- ✅ RESTful API with OpenAPI 3.0 documentation
- ✅ Database-per-service pattern (Payment DB)
- ✅ Health checks and metrics endpoints
- ✅ Docker containerization
- ✅ Kubernetes deployment manifests

## Technology Stack
- **Framework**: FastAPI (Python 3.11)
- **Database**: PostgreSQL
- **ORM**: SQLAlchemy
- **API Documentation**: OpenAPI 3.0 (Swagger UI)
- **Containerization**: Docker
- **Orchestration**: Kubernetes (Minikube)

## Database Schema

### Tables
1. **payments**: Main payment records
   - payment_id (PK)
   - order_id (UNIQUE, FK to Order Service)
   - user_id (FK to User Service)
   - amount, currency
   - payment_method (CREDIT_CARD, DEBIT_CARD, UPI, NET_BANKING, WALLET, COD)
   - status (PENDING, PROCESSING, COMPLETED, FAILED, REFUNDED, CANCELLED)
   - transaction_id (UNIQUE)
   - gateway_response
   - created_at, updated_at, completed_at

2. **transactions**: Transaction history
   - transaction_log_id (PK)
   - payment_id (FK)
   - transaction_type (PAYMENT, REFUND)
   - amount, status, description
   - created_at

## API Endpoints

### Base URL: `/v1`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/payments` | Create a new payment |
| GET | `/v1/payments/{payment_id}` | Get payment by ID |
| GET | `/v1/payments/order/{order_id}` | Get payment by order ID |
| GET | `/v1/payments/transaction/{transaction_id}` | Get payment by transaction ID |
| PATCH | `/v1/payments/{payment_id}/status` | Update payment status |
| POST | `/v1/payments/{payment_id}/refund` | Process refund |
| DELETE | `/v1/payments/{payment_id}` | Cancel payment |
| GET | `/v1/payments` | List payments (with filters & pagination) |
| GET | `/health` | Health check |
| GET | `/metrics` | Service metrics |

## Port Configuration

### Docker Compose (Local Development)
- **External Port**: `8086`
- **Internal Port**: `8006`
- **Database Port**: `5434` (external) → `5432` (internal)

**Access URLs:**
```
http://localhost:8086/health
http://localhost:8086/docs
http://localhost:8086/v1/payments
```

### Kubernetes
- **Service Port**: `80` (NodePort: 30006)
- **Container Port**: `8006`

## Quick Start

### Option 1: Docker Compose
```powershell
# Start services
docker-compose up -d

# Test health
Invoke-RestMethod -Uri "http://localhost:8086/health"

# Open Swagger UI
Start-Process "http://localhost:8086/docs"

# View logs
docker-compose logs -f payment-service

# Stop services
docker-compose down
```

### Option 2: Kubernetes
```powershell
# Build image in Minikube
& minikube -p minikube docker-env --shell powershell | Invoke-Expression
docker build -t payment-service:latest .

# Deploy
kubectl apply -f k8s/

# Get service URL
minikube service payment-service --url

# Or port forward
kubectl port-forward service/payment-service 8086:80
```

## Sample Requests

### 1. Create Payment
```powershell
$body = @{
    order_id = 2001
    user_id = 501
    amount = 1499.99
    currency = "INR"
    payment_method = "CREDIT_CARD"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8086/v1/payments" -Method Post -Body $body -ContentType "application/json"
```

### 2. Update Payment Status to COMPLETED
```powershell
$update = @{
    status = "COMPLETED"
    gateway_response = "Payment processed successfully"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8086/v1/payments/1/status" -Method Patch -Body $update -ContentType "application/json"
```

### 3. Process Refund
```powershell
$refund = @{
    amount = 1499.99
    reason = "Customer requested refund - Product defective"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8086/v1/payments/1/refund" -Method Post -Body $refund -ContentType "application/json"
```

### 4. Get Payment by Transaction ID
```powershell
Invoke-RestMethod -Uri "http://localhost:8086/v1/payments/transaction/TXN1234567890"
```

### 5. List Payments with Filters
```powershell
# Filter by status
Invoke-RestMethod -Uri "http://localhost:8086/v1/payments?status=COMPLETED"

# Filter by payment method
Invoke-RestMethod -Uri "http://localhost:8086/v1/payments?payment_method=UPI"

# Filter by user
Invoke-RestMethod -Uri "http://localhost:8086/v1/payments?user_id=501"
```

## Payment Status Lifecycle

```
PENDING → PROCESSING → COMPLETED
   ↓                        ↓
FAILED              REFUNDED
   ↓
CANCELLED
```

### Status Descriptions
- **PENDING**: Payment initiated, awaiting processing
- **PROCESSING**: Payment being processed by gateway
- **COMPLETED**: Payment successful
- **FAILED**: Payment failed (insufficient funds, card declined, etc.)
- **REFUNDED**: Payment refunded to customer
- **CANCELLED**: Payment cancelled before completion

## Payment Methods
- **CREDIT_CARD**: Credit card payment
- **DEBIT_CARD**: Debit card payment
- **UPI**: UPI (Unified Payments Interface)
- **NET_BANKING**: Net banking
- **WALLET**: Digital wallet (Paytm, PhonePe, etc.)
- **COD**: Cash on Delivery

## Database Credentials

- **Username**: `user`
- **Password**: `password`
- **Database**: `payment_db`
- **Port**: `5434` (Docker Compose)

### Check Database
```powershell
docker exec -it payment-postgres psql -U user -d payment_db -c "SELECT * FROM payments;"
```

## Inter-Service Communication

### Integration with Other Services

**Order Service → Payment Service**:
```python
# When order is confirmed, create payment
payment_response = requests.post(
    "http://payment-service/v1/payments",
    json={
        "order_id": order_id,
        "user_id": user_id,
        "amount": total_amount,
        "currency": "INR",
        "payment_method": "CREDIT_CARD"
    }
)
```

**Payment Service → Notification Service**:
```python
# After payment completed, send notification
requests.post(
    "http://notification-service/v1/notifications",
    json={
        "user_id": user_id,
        "type": "PAYMENT_SUCCESS",
        "message": f"Payment of ₹{amount} completed successfully"
    }
)
```

## Metrics

```powershell
Invoke-RestMethod -Uri "http://localhost:8086/metrics"
```

**Available Metrics:**
- `payments_created_total`: Total payments created
- `payments_by_status{status}`: Payments grouped by status
- `payments_by_method{method}`: Payments grouped by method
- `total_amount_processed`: Total amount processed
- `total_refunds`: Total refund amount

## Project Structure

```
payment-service/
├── main.py                      # FastAPI application
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Container image
├── docker-compose.yml          # Multi-container setup
├── .gitignore                   # Git ignore rules
├── db/
│   ├── init.sql                 # Database schema
│   └── init_with_seed.sql       # Schema + sample data
├── k8s/
│   ├── deployment.yaml          # K8s deployments
│   ├── service.yaml             # K8s services
│   ├── configmap.yaml           # App configuration
│   ├── db-configmap.yaml        # DB initialization
│   ├── secret.yaml              # Secrets
│   └── pvc.yaml                 # Persistent volume
├── sample_requests/
│   ├── create_payment.json
│   ├── update_status.json
│   ├── refund_payment.json
│   └── check_payment.json
└── README.md                    # This file
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://user:password@localhost:5434/payment_db` | Database connection string |
| `LOG_LEVEL` | `INFO` | Logging level |

## Error Handling

### Common Error Responses

**409 Conflict**:
```json
{
  "detail": "Payment for order_id 2001 already exists"
}
```

**400 Bad Request**:
```json
{
  "detail": "Cannot refund payment with status: PENDING"
}
```

**404 Not Found**:
```json
{
  "detail": "Payment 999 not found"
}
```

## Business Rules

1. **One Payment Per Order**: Each order can have only one payment
2. **Status Constraints**:
   - Cannot change status of COMPLETED payment (except to REFUNDED)
   - Cannot change status of REFUNDED payment
   - Cannot cancel COMPLETED or REFUNDED payments
3. **Refund Rules**:
   - Can only refund COMPLETED payments
   - Refund amount cannot exceed payment amount
   - Partial refunds supported

## Testing

### Manual Testing Steps
See detailed testing guide in the Shipping Service documentation for similar testing approach.

### Database Verification
```powershell
# Check payments
docker exec -it payment-postgres psql -U user -d payment_db -c "SELECT payment_id, order_id, amount, status FROM payments;"

# Check transactions
docker exec -it payment-postgres psql -U user -d payment_db -c "SELECT * FROM transactions ORDER BY created_at DESC LIMIT 10;"

# Payment statistics
docker exec -it payment-postgres psql -U user -d payment_db -c "SELECT status, COUNT(*), SUM(amount) FROM payments GROUP BY status;"
```

## License
MIT License - BITS WILP Assignment

## Support
For issues or questions, please contact the development team.
