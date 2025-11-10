from fastapi import FastAPI, HTTPException, Query, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime, timedelta
from enum import Enum
import logging
import json
import hashlib
import asyncio
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
import random
import string
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5434/payment_db")

# Service URLs for inter-service communication
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
)
logger = logging.getLogger(__name__)

# Enums
class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    CANCELLED = "CANCELLED"

class PaymentMethod(str, Enum):
    CREDIT_CARD = "CREDIT_CARD"
    DEBIT_CARD = "DEBIT_CARD"
    UPI = "UPI"
    NET_BANKING = "NET_BANKING"
    WALLET = "WALLET"
    COD = "COD"

class TransactionType(str, Enum):
    PAYMENT = "PAYMENT"
    REFUND = "REFUND"

# Database Models
class Payment(Base):
    __tablename__ = "payments"
    
    payment_id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, unique=True, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="INR")
    payment_method = Column(SQLEnum(PaymentMethod), nullable=False)
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING, index=True)
    transaction_id = Column(String(50), unique=True, index=True)
    reference = Column(String(100), index=True)  # Added as per assignment requirements
    authorization_code = Column(String(50))
    gateway_response = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    captured_at = Column(DateTime, nullable=True)
    
    # Relationship
    transactions = relationship("Transaction", back_populates="payment", cascade="all, delete-orphan")

class Transaction(Base):
    __tablename__ = "transactions"
    
    transaction_log_id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.payment_id"), nullable=False)
    transaction_type = Column(SQLEnum(TransactionType), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(SQLEnum(PaymentStatus), nullable=False)
    description = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    payment = relationship("Payment", back_populates="transactions")

class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    payment_id = Column(Integer, ForeignKey("payments.payment_id"), nullable=True)
    request_hash = Column(String(64), nullable=False)
    response_body = Column(Text)
    status_code = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    
    __table_args__ = (
        Index('idx_idempotency_expires', 'expires_at'),
    )

# Create tables
Base.metadata.create_all(bind=engine)

# Pydantic Models
class PaymentCreate(BaseModel):
    order_id: int = Field(..., gt=0, description="Order ID from Order Service")
    user_id: int = Field(..., gt=0, description="User ID")
    amount: float = Field(..., gt=0, description="Payment amount")
    currency: str = Field(default="INR", max_length=3)
    payment_method: PaymentMethod
    reference: Optional[str] = Field(None, max_length=100, description="External reference (e.g., invoice number)")
    
    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be greater than 0')
        if v > 100000:
            raise ValueError('Amount exceeds maximum transaction limit of 100,000')
        return round(v, 2)  # Banker's rounding to 2 decimals

class PaymentStatusUpdate(BaseModel):
    status: PaymentStatus
    gateway_response: Optional[str] = None

class PaymentResponse(BaseModel):
    payment_id: int
    order_id: int
    user_id: int
    amount: float
    currency: str
    payment_method: PaymentMethod
    status: PaymentStatus
    transaction_id: Optional[str]
    reference: Optional[str]
    authorization_code: Optional[str]
    gateway_response: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    captured_at: Optional[datetime]
    transactions: List[dict] = []

class RefundRequest(BaseModel):
    amount: Optional[float] = Field(None, gt=0, description="Partial refund amount (optional)")
    reason: str = Field(..., min_length=5, description="Reason for refund")

class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    payments: List[PaymentResponse]

# Metrics storage
metrics = {
    "payments_created_total": 0,
    "payments_failed_total": 0,  # Required by assignment
    "payments_by_status": {status.value: 0 for status in PaymentStatus},
    "payments_by_method": {method.value: 0 for method in PaymentMethod},
    "total_amount_processed": 0.0,
    "total_refunds": 0.0,
    "refunds_processed_total": 0,
    "payment_processing_errors": 0
}

# FastAPI App
app = FastAPI(
    title="Payment Service",
    description="Handles payment processing, transactions, and refunds for ECI platform",
    version="1.0.0"
)

# Add Prometheus instrumentation
Instrumentator().instrument(app).expose(app)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper Functions
def generate_transaction_id():
    """Generate unique transaction ID"""
    return "TXN" + ''.join(random.choices(string.digits, k=10))

def generate_reference():
    """Generate payment reference"""
    return "REF" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

def compute_request_hash(data: dict) -> str:
    """Compute SHA256 hash of request data"""
    json_str = json.dumps(data, sort_keys=True)
    return hashlib.sha256(json_str.encode()).hexdigest()

def mask_sensitive_data(data: dict) -> dict:
    """Mask sensitive information in logs"""
    masked = data.copy()
    # Add masking logic for sensitive fields if needed
    return masked

def log_transaction(db, payment_id: int, transaction_type: TransactionType, 
                   amount: float, status: PaymentStatus, description: str):
    """Log transaction event"""
    transaction = Transaction(
        payment_id=payment_id,
        transaction_type=transaction_type,
        amount=amount,
        status=status,
        description=description
    )
    db.add(transaction)
    db.commit()
    logger.info(f"Transaction logged: {transaction_type} for payment_id={payment_id}")

def payment_to_dict(payment: Payment, include_transactions: bool = True):
    """Convert Payment object to dictionary"""
    result = {
        "payment_id": payment.payment_id,
        "order_id": payment.order_id,
        "user_id": payment.user_id,
        "amount": payment.amount,
        "currency": payment.currency,
        "payment_method": payment.payment_method.value,
        "status": payment.status.value,
        "transaction_id": payment.transaction_id,
        "reference": payment.reference,
        "authorization_code": payment.authorization_code,
        "gateway_response": payment.gateway_response,
        "created_at": payment.created_at.isoformat(),
        "updated_at": payment.updated_at.isoformat(),
        "completed_at": payment.completed_at.isoformat() if payment.completed_at else None,
        "captured_at": payment.captured_at.isoformat() if payment.captured_at else None,
        "transactions": []
    }
    
    if include_transactions:
        result["transactions"] = [
            {
                "transaction_log_id": t.transaction_log_id,
                "transaction_type": t.transaction_type.value,
                "amount": t.amount,
                "status": t.status.value,
                "description": t.description,
                "created_at": t.created_at.isoformat()
            }
            for t in payment.transactions
        ]
    
    return result

# Inter-Service Communication Functions
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def notify_order_service(order_id: int, payment_status: str, payment_id: int):
    """Notify order service about payment status with retry logic"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.patch(
                f"{ORDER_SERVICE_URL}/v1/orders/{order_id}/payment-status",
                json={
                    "payment_id": payment_id,
                    "payment_status": payment_status
                }
            )
            response.raise_for_status()
            logger.info(f"Order {order_id} notified: payment_status={payment_status}")
            return True
    except Exception as e:
        logger.error(f"Failed to notify order service for order {order_id}: {str(e)}")
        raise

async def notify_order_service_async(order_id: int, payment_status: str, payment_id: int):
    """Non-blocking notification to order service"""
    try:
        await notify_order_service(order_id, payment_status, payment_id)
    except Exception as e:
        logger.error(f"All retry attempts failed for order {order_id}: {str(e)}")
        # Log but don't fail the payment operation

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
async def release_inventory_reservation(order_id: int, reason: str = "Payment failed"):
    """Request inventory service to release reservations"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{INVENTORY_SERVICE_URL}/v1/inventory/release",
                json={"order_id": order_id, "reason": reason}
            )
            response.raise_for_status()
            logger.info(f"Inventory released for order {order_id}: {reason}")
            return True
    except Exception as e:
        logger.error(f"Failed to release inventory for order {order_id}: {str(e)}")
        raise

async def release_inventory_async(order_id: int, reason: str):
    """Non-blocking inventory release"""
    try:
        await release_inventory_reservation(order_id, reason)
    except Exception as e:
        logger.error(f"All retry attempts failed for inventory release order {order_id}: {str(e)}")

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
async def send_notification(user_id: int, notification_type: str, message: str):
    """Send notification via notification service"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{NOTIFICATION_SERVICE_URL}/v1/notifications",
                json={
                    "user_id": user_id,
                    "type": notification_type,
                    "message": message,
                    "channel": "EMAIL"
                }
            )
            response.raise_for_status()
            logger.info(f"Notification sent to user {user_id}: {notification_type}")
            return True
    except Exception as e:
        logger.error(f"Failed to send notification to user {user_id}: {str(e)}")
        # Don't retry, notifications are non-critical
        return False

# API Endpoints

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "payment-service",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/metrics")
def get_metrics():
    """Prometheus-style metrics endpoint"""
    metric_lines = [
        f"payments_created_total {metrics['payments_created_total']}",
        f"payments_failed_total {metrics['payments_failed_total']}",
        f"total_amount_processed {metrics['total_amount_processed']:.2f}",
        f"total_refunds {metrics['total_refunds']:.2f}",
        f"refunds_processed_total {metrics['refunds_processed_total']}",
        f"payment_processing_errors {metrics['payment_processing_errors']}"
    ]
    
    for status, count in metrics['payments_by_status'].items():
        metric_lines.append(f'payments_by_status{{status="{status}"}} {count}')
    
    for method, count in metrics['payments_by_method'].items():
        metric_lines.append(f'payments_by_method{{method="{method}"}} {count}')
    
    return Response(content="\n".join(metric_lines), media_type="text/plain")

@app.post("/v1/payments/charge", response_model=PaymentResponse, status_code=201)
async def charge_payment(
    request: Request,
    payment_data: PaymentCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key")
):
    """
    Charge payment with idempotency support (REQUIRED by assignment)
    
    This endpoint ensures that duplicate requests with the same Idempotency-Key
    return the same response, preventing double charges.
    """
    db = SessionLocal()
    try:
        # Compute request hash for validation
        request_body = payment_data.dict()
        request_hash = compute_request_hash(request_body)
        
        # Check if idempotency key already exists
        existing_idempotency = db.query(IdempotencyKey).filter(
            IdempotencyKey.idempotency_key == idempotency_key
        ).first()
        
        if existing_idempotency:
            # Check if key has expired
            if existing_idempotency.expires_at < datetime.utcnow():
                db.delete(existing_idempotency)
                db.commit()
            else:
                # Return cached response (idempotent behavior)
                logger.info(f"Idempotent request detected: {idempotency_key}")
                if existing_idempotency.response_body:
                    cached_response = json.loads(existing_idempotency.response_body)
                    return Response(
                        content=existing_idempotency.response_body,
                        status_code=existing_idempotency.status_code,
                        media_type="application/json"
                    )
        
        # Check if payment for order already exists (business rule)
        existing_payment = db.query(Payment).filter(Payment.order_id == payment_data.order_id).first()
        if existing_payment:
            raise HTTPException(
                status_code=400, 
                detail=f"Payment for order_id {payment_data.order_id} already exists"
            )
        
        # Generate transaction ID and reference
        transaction_id = generate_transaction_id()
        reference = payment_data.reference or generate_reference()
        
        # Create payment
        payment = Payment(
            order_id=payment_data.order_id,
            user_id=payment_data.user_id,
            amount=payment_data.amount,
            currency=payment_data.currency,
            payment_method=payment_data.payment_method,
            status=PaymentStatus.PROCESSING,
            transaction_id=transaction_id,
            reference=reference
        )
        
        db.add(payment)
        db.commit()
        db.refresh(payment)
        
        # Log initial transaction
        log_transaction(
            db, payment.payment_id, TransactionType.PAYMENT,
            payment.amount, PaymentStatus.PROCESSING,
            f"Payment charge initiated via {payment_data.payment_method.value}"
        )
        
        # Simulate payment processing (in real world, this would call a payment gateway)
        # For demo purposes, we'll mark it as completed
        payment.status = PaymentStatus.COMPLETED
        payment.completed_at = datetime.utcnow()
        payment.gateway_response = "Payment processed successfully"
        db.commit()
        db.refresh(payment)
        
        # Log completion
        log_transaction(
            db, payment.payment_id, TransactionType.PAYMENT,
            payment.amount, PaymentStatus.COMPLETED,
            "Payment completed successfully"
        )
        
        # Update metrics
        metrics['payments_created_total'] += 1
        metrics['payments_by_status'][PaymentStatus.COMPLETED.value] += 1
        metrics['payments_by_method'][payment_data.payment_method.value] += 1
        metrics['total_amount_processed'] += payment.amount
        
        # Prepare response
        response_data = payment_to_dict(payment)
        response_json = json.dumps(response_data)
        
        # Store idempotency key with response
        idempotency_record = IdempotencyKey(
            idempotency_key=idempotency_key,
            payment_id=payment.payment_id,
            request_hash=request_hash,
            response_body=response_json,
            status_code=201,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        db.add(idempotency_record)
        db.commit()
        
        logger.info(f"Payment charged: payment_id={payment.payment_id}, order_id={payment.order_id}, amount={payment.amount}")
        
        # Async notifications (non-blocking)
        asyncio.create_task(notify_order_service_async(payment.order_id, "COMPLETED", payment.payment_id))
        asyncio.create_task(send_notification(
            payment.user_id,
            "PAYMENT_SUCCESS",
            f"Payment of {payment.amount} {payment.currency} completed successfully. Reference: {payment.reference}"
        ))
        
        return response_data
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        metrics['payments_failed_total'] += 1
        metrics['payment_processing_errors'] += 1
        logger.error(f"Error charging payment: {str(e)}")
        
        # Attempt to release inventory on payment failure
        if payment_data.order_id:
            asyncio.create_task(release_inventory_async(payment_data.order_id, "Payment processing failed"))
        
        raise HTTPException(status_code=500, detail=f"Failed to charge payment: {str(e)}")
    finally:
        db.close()

@app.post("/v1/payments", response_model=PaymentResponse, status_code=201)
async def create_payment(payment_data: PaymentCreate):
    """
    Create a new payment (legacy endpoint - use /v1/payments/charge instead)
    
    NOTE: This endpoint does NOT support idempotency. Use /v1/payments/charge for production.
    """
    db = SessionLocal()
    try:
        # Check if payment for order already exists
        existing = db.query(Payment).filter(Payment.order_id == payment_data.order_id).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Payment for order_id {payment_data.order_id} already exists")
        
        # Generate transaction ID
        transaction_id = generate_transaction_id()
        reference = payment_data.reference or generate_reference()
        
        # Create payment
        payment = Payment(
            order_id=payment_data.order_id,
            user_id=payment_data.user_id,
            amount=payment_data.amount,
            currency=payment_data.currency,
            payment_method=payment_data.payment_method,
            status=PaymentStatus.PENDING,
            transaction_id=transaction_id,
            reference=reference
        )
        
        db.add(payment)
        db.commit()
        db.refresh(payment)
        
        # Log initial transaction
        log_transaction(
            db, payment.payment_id, TransactionType.PAYMENT,
            payment.amount, PaymentStatus.PENDING,
            f"Payment initiated via {payment_data.payment_method.value}"
        )
        
        # Update metrics
        metrics['payments_created_total'] += 1
        metrics['payments_by_status'][PaymentStatus.PENDING.value] += 1
        metrics['payments_by_method'][payment_data.payment_method.value] += 1
        
        logger.info(f"Payment created: payment_id={payment.payment_id}, order_id={payment.order_id}")
        
        return payment_to_dict(payment)
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating payment: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create payment: {str(e)}")
    finally:
        db.close()

@app.get("/v1/payments/{payment_id}", response_model=PaymentResponse)
def get_payment(payment_id: int):
    """Get payment by ID"""
    db = SessionLocal()
    try:
        payment = db.query(Payment).filter(Payment.payment_id == payment_id).first()
        if not payment:
            raise HTTPException(status_code=404, detail=f"Payment {payment_id} not found")
        
        return payment_to_dict(payment)
    finally:
        db.close()

@app.get("/v1/payments/order/{order_id}", response_model=PaymentResponse)
def get_payment_by_order(order_id: int):
    """Get payment by order ID"""
    db = SessionLocal()
    try:
        payment = db.query(Payment).filter(Payment.order_id == order_id).first()
        if not payment:
            raise HTTPException(status_code=404, detail=f"Payment for order {order_id} not found")
        
        return payment_to_dict(payment)
    finally:
        db.close()

@app.get("/v1/payments/transaction/{transaction_id}", response_model=PaymentResponse)
def get_payment_by_transaction(transaction_id: str):
    """Get payment by transaction ID"""
    db = SessionLocal()
    try:
        payment = db.query(Payment).filter(Payment.transaction_id == transaction_id).first()
        if not payment:
            raise HTTPException(status_code=404, detail=f"Payment with transaction {transaction_id} not found")
        
        return payment_to_dict(payment)
    finally:
        db.close()

@app.get("/v1/payments", response_model=PaginatedResponse)
def list_payments(
    status: Optional[PaymentStatus] = None,
    payment_method: Optional[PaymentMethod] = None,
    user_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100)
):
    """List payments with filters and pagination"""
    db = SessionLocal()
    try:
        query = db.query(Payment)
        
        if status:
            query = query.filter(Payment.status == status)
        if payment_method:
            query = query.filter(Payment.payment_method == payment_method)
        if user_id:
            query = query.filter(Payment.user_id == user_id)
        
        total = query.count()
        payments = query.order_by(Payment.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "payments": [payment_to_dict(p, include_transactions=False) for p in payments]
        }
    finally:
        db.close()

@app.patch("/v1/payments/{payment_id}/status", response_model=PaymentResponse)
async def update_payment_status(payment_id: int, status_update: PaymentStatusUpdate):
    """Update payment status"""
    db = SessionLocal()
    try:
        payment = db.query(Payment).filter(Payment.payment_id == payment_id).first()
        if not payment:
            raise HTTPException(status_code=404, detail=f"Payment {payment_id} not found")
        
        # Business rules
        if payment.status == PaymentStatus.COMPLETED and status_update.status != PaymentStatus.REFUNDED:
            raise HTTPException(status_code=400, detail="Cannot change status of completed payment (use refund endpoint)")
        
        if payment.status == PaymentStatus.REFUNDED:
            raise HTTPException(status_code=400, detail="Cannot change status of refunded payment")
        
        old_status = payment.status
        payment.status = status_update.status
        payment.updated_at = datetime.utcnow()
        
        if status_update.gateway_response:
            payment.gateway_response = status_update.gateway_response
        
        # Set completed_at timestamp
        if status_update.status == PaymentStatus.COMPLETED and not payment.completed_at:
            payment.completed_at = datetime.utcnow()
            metrics['total_amount_processed'] += payment.amount
        
        # Track failures
        if status_update.status == PaymentStatus.FAILED:
            metrics['payments_failed_total'] += 1
        
        db.commit()
        
        # Log transaction
        log_transaction(
            db, payment.payment_id, TransactionType.PAYMENT,
            payment.amount, status_update.status,
            f"Status changed from {old_status.value} to {status_update.status.value}"
        )
        
        # Update metrics
        metrics['payments_by_status'][old_status.value] -= 1
        metrics['payments_by_status'][status_update.status.value] += 1
        
        logger.info(f"Payment {payment_id} status updated: {old_status.value} -> {status_update.status.value}")
        
        # Async notifications
        asyncio.create_task(notify_order_service_async(payment.order_id, status_update.status.value, payment.payment_id))
        
        if status_update.status == PaymentStatus.FAILED:
            # Release inventory on payment failure
            asyncio.create_task(release_inventory_async(payment.order_id, "Payment failed"))
            asyncio.create_task(send_notification(
                payment.user_id,
                "PAYMENT_FAILED",
                f"Payment of {payment.amount} {payment.currency} failed. Reference: {payment.reference}"
            ))
        
        db.refresh(payment)
        return payment_to_dict(payment)
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating payment status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update status: {str(e)}")
    finally:
        db.close()

@app.post("/v1/payments/{payment_id}/refund", response_model=PaymentResponse)
async def refund_payment(payment_id: int, refund_request: RefundRequest):
    """
    Process refund for a payment (idempotent operation as per assignment requirements)
    """
    db = SessionLocal()
    try:
        payment = db.query(Payment).filter(Payment.payment_id == payment_id).first()
        if not payment:
            raise HTTPException(status_code=404, detail=f"Payment {payment_id} not found")
        
        # Business rules
        if payment.status != PaymentStatus.COMPLETED:
            raise HTTPException(status_code=400, detail=f"Cannot refund payment with status: {payment.status.value}")
        
        # Calculate refund amount
        refund_amount = refund_request.amount if refund_request.amount else payment.amount
        
        if refund_amount > payment.amount:
            raise HTTPException(status_code=400, detail="Refund amount cannot exceed payment amount")
        
        # Update payment status
        payment.status = PaymentStatus.REFUNDED
        payment.updated_at = datetime.utcnow()
        payment.gateway_response = f"Refund: {refund_request.reason}"
        
        db.commit()
        
        # Log refund transaction
        log_transaction(
            db, payment.payment_id, TransactionType.REFUND,
            refund_amount, PaymentStatus.REFUNDED,
            f"Refund of {refund_amount} {payment.currency}: {refund_request.reason}"
        )
        
        # Update metrics
        metrics['payments_by_status'][PaymentStatus.COMPLETED.value] -= 1
        metrics['payments_by_status'][PaymentStatus.REFUNDED.value] += 1
        metrics['total_refunds'] += refund_amount
        metrics['refunds_processed_total'] += 1
        
        logger.info(f"Payment {payment_id} refunded: {refund_amount} {payment.currency}")
        
        # Async notifications
        asyncio.create_task(notify_order_service_async(payment.order_id, "REFUNDED", payment.payment_id))
        asyncio.create_task(release_inventory_async(payment.order_id, "Payment refunded"))
        asyncio.create_task(send_notification(
            payment.user_id,
            "PAYMENT_REFUNDED",
            f"Refund of {refund_amount} {payment.currency} processed. Reference: {payment.reference}. Reason: {refund_request.reason}"
        ))
        
        db.refresh(payment)
        return payment_to_dict(payment)
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error processing refund: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process refund: {str(e)}")
    finally:
        db.close()

@app.delete("/v1/payments/{payment_id}", response_model=PaymentResponse)
def cancel_payment(payment_id: int):
    """Cancel a payment"""
    db = SessionLocal()
    try:
        payment = db.query(Payment).filter(Payment.payment_id == payment_id).first()
        if not payment:
            raise HTTPException(status_code=404, detail=f"Payment {payment_id} not found")
        
        # Business rules
        if payment.status in [PaymentStatus.COMPLETED, PaymentStatus.REFUNDED]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel payment with status: {payment.status.value}"
            )
        
        old_status = payment.status
        payment.status = PaymentStatus.CANCELLED
        payment.updated_at = datetime.utcnow()
        
        db.commit()
        
        # Log transaction
        log_transaction(
            db, payment.payment_id, TransactionType.PAYMENT,
            payment.amount, PaymentStatus.CANCELLED,
            "Payment cancelled by user"
        )
        
        # Update metrics
        metrics['payments_by_status'][old_status.value] -= 1
        metrics['payments_by_status'][PaymentStatus.CANCELLED.value] += 1
        
        logger.info(f"Payment {payment_id} cancelled")
        
        db.refresh(payment)
        return payment_to_dict(payment)
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error cancelling payment: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel payment: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
