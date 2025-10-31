from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
import logging
import json
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
import random
import string

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5434/payment_db")
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
    gateway_response = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
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

# Create tables
Base.metadata.create_all(bind=engine)

# Pydantic Models
class PaymentCreate(BaseModel):
    order_id: int = Field(..., gt=0, description="Order ID from Order Service")
    user_id: int = Field(..., gt=0, description="User ID")
    amount: float = Field(..., gt=0, description="Payment amount")
    currency: str = Field(default="INR", max_length=3)
    payment_method: PaymentMethod

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
    gateway_response: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
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
    "payments_by_status": {status.value: 0 for status in PaymentStatus},
    "payments_by_method": {method.value: 0 for method in PaymentMethod},
    "total_amount_processed": 0.0,
    "total_refunds": 0.0
}

# FastAPI App
app = FastAPI(
    title="Payment Service",
    description="Handles payment processing, transactions, and refunds for ECI platform",
    version="1.0.0"
)

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
        "gateway_response": payment.gateway_response,
        "created_at": payment.created_at.isoformat(),
        "updated_at": payment.updated_at.isoformat(),
        "completed_at": payment.completed_at.isoformat() if payment.completed_at else None,
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
        f"total_amount_processed {metrics['total_amount_processed']:.2f}",
        f"total_refunds {metrics['total_refunds']:.2f}"
    ]
    
    for status, count in metrics['payments_by_status'].items():
        metric_lines.append(f'payments_by_status{{status="{status}"}} {count}')
    
    for method, count in metrics['payments_by_method'].items():
        metric_lines.append(f'payments_by_method{{method="{method}"}} {count}')
    
    return "\n".join(metric_lines)

@app.post("/v1/payments", response_model=PaymentResponse, status_code=201)
def create_payment(payment_data: PaymentCreate):
    """Create a new payment"""
    db = SessionLocal()
    try:
        # Check if payment for order already exists
        existing = db.query(Payment).filter(Payment.order_id == payment_data.order_id).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Payment for order_id {payment_data.order_id} already exists")
        
        # Generate transaction ID
        transaction_id = generate_transaction_id()
        
        # Create payment
        payment = Payment(
            order_id=payment_data.order_id,
            user_id=payment_data.user_id,
            amount=payment_data.amount,
            currency=payment_data.currency,
            payment_method=payment_data.payment_method,
            status=PaymentStatus.PENDING,
            transaction_id=transaction_id
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
def update_payment_status(payment_id: int, status_update: PaymentStatusUpdate):
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
def refund_payment(payment_id: int, refund_request: RefundRequest):
    """Process refund for a payment"""
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
        
        logger.info(f"Payment {payment_id} refunded: {refund_amount} {payment.currency}")
        
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
