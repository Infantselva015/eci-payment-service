"""
Integration Tests for Payment Service
Tests idempotency, inter-service communication, and payment workflows
"""

import pytest
import requests
import time
import hashlib
import json
from datetime import datetime

BASE_URL = "http://localhost:8086"

class TestPaymentServiceIntegration:
    
    def test_health_check(self):
        """Test that the service is healthy"""
        response = requests.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "payment-service"
    
    def test_idempotent_charge_same_key_same_response(self):
        """
        CRITICAL TEST: Test that duplicate charges with same idempotency key 
        return the same response without creating duplicate payments
        """
        idempotency_key = f"test-key-{int(time.time())}"
        
        payment_data = {
            "order_id": 99999,
            "user_id": 1,
            "amount": 100.0,
            "currency": "INR",
            "payment_method": "CREDIT_CARD"
        }
        
        headers = {
            "Idempotency-Key": idempotency_key,
            "Content-Type": "application/json"
        }
        
        # First request
        response1 = requests.post(
            f"{BASE_URL}/v1/payments/charge",
            json=payment_data,
            headers=headers
        )
        assert response1.status_code == 201
        payment1 = response1.json()
        
        # Second request with same key (should return cached response)
        response2 = requests.post(
            f"{BASE_URL}/v1/payments/charge",
            json=payment_data,
            headers=headers
        )
        assert response2.status_code == 201
        payment2 = response2.json()
        
        # Both should have the same payment_id (idempotency working)
        assert payment1["payment_id"] == payment2["payment_id"]
        assert payment1["transaction_id"] == payment2["transaction_id"]
        
        print(f"✓ Idempotency test passed: payment_id={payment1['payment_id']}")
    
    def test_idempotent_charge_different_keys(self):
        """Test that different idempotency keys create different payments"""
        payment_data_base = {
            "user_id": 1,
            "amount": 100.0,
            "currency": "INR",
            "payment_method": "UPI"
        }
        
        # First request
        headers1 = {"Idempotency-Key": f"key-1-{int(time.time())}"}
        payment_data1 = {**payment_data_base, "order_id": 99991}
        response1 = requests.post(
            f"{BASE_URL}/v1/payments/charge",
            json=payment_data1,
            headers=headers1
        )
        assert response1.status_code == 201
        payment1 = response1.json()
        
        # Second request with different key
        time.sleep(0.1)  # Small delay to ensure different timestamp
        headers2 = {"Idempotency-Key": f"key-2-{int(time.time())}"}
        payment_data2 = {**payment_data_base, "order_id": 99992}
        response2 = requests.post(
            f"{BASE_URL}/v1/payments/charge",
            json=payment_data2,
            headers=headers2
        )
        assert response2.status_code == 201
        payment2 = response2.json()
        
        # Should have different payment_ids
        assert payment1["payment_id"] != payment2["payment_id"]
        
        print(f"✓ Different keys test passed: {payment1['payment_id']} != {payment2['payment_id']}")
    
    def test_charge_payment_creates_reference(self):
        """Test that payment charge creates a reference field"""
        idempotency_key = f"test-ref-{int(time.time())}"
        
        payment_data = {
            "order_id": 99998,
            "user_id": 1,
            "amount": 250.50,
            "currency": "INR",
            "payment_method": "DEBIT_CARD"
        }
        
        headers = {"Idempotency-Key": idempotency_key}
        response = requests.post(
            f"{BASE_URL}/v1/payments/charge",
            json=payment_data,
            headers=headers
        )
        
        assert response.status_code == 201
        payment = response.json()
        
        # Should have a reference field
        assert "reference" in payment
        assert payment["reference"] is not None
        assert payment["reference"].startswith("REF")
        
        print(f"✓ Reference field test passed: {payment['reference']}")
    
    def test_charge_payment_with_custom_reference(self):
        """Test charging payment with custom reference"""
        idempotency_key = f"test-custom-ref-{int(time.time())}"
        custom_ref = "INV-2025-123456"
        
        payment_data = {
            "order_id": 99997,
            "user_id": 1,
            "amount": 500.0,
            "currency": "INR",
            "payment_method": "NET_BANKING",
            "reference": custom_ref
        }
        
        headers = {"Idempotency-Key": idempotency_key}
        response = requests.post(
            f"{BASE_URL}/v1/payments/charge",
            json=payment_data,
            headers=headers
        )
        
        assert response.status_code == 201
        payment = response.json()
        assert payment["reference"] == custom_ref
        
        print(f"✓ Custom reference test passed: {payment['reference']}")
    
    def test_payment_amount_validation(self):
        """Test that payment amount is validated"""
        idempotency_key = f"test-invalid-{int(time.time())}"
        
        # Test negative amount
        payment_data = {
            "order_id": 99996,
            "user_id": 1,
            "amount": -100.0,
            "currency": "INR",
            "payment_method": "CREDIT_CARD"
        }
        
        headers = {"Idempotency-Key": idempotency_key}
        response = requests.post(
            f"{BASE_URL}/v1/payments/charge",
            json=payment_data,
            headers=headers
        )
        
        # Should fail validation
        assert response.status_code == 422  # Validation error
        
        print("✓ Amount validation test passed")
    
    def test_refund_workflow(self):
        """Test complete refund workflow"""
        # First, create and charge a payment
        idempotency_key = f"test-refund-{int(time.time())}"
        payment_data = {
            "order_id": 99995,
            "user_id": 1,
            "amount": 150.0,
            "currency": "INR",
            "payment_method": "WALLET"
        }
        
        headers = {"Idempotency-Key": idempotency_key}
        response = requests.post(
            f"{BASE_URL}/v1/payments/charge",
            json=payment_data,
            headers=headers
        )
        assert response.status_code == 201
        payment = response.json()
        payment_id = payment["payment_id"]
        
        # Now refund it
        refund_data = {
            "amount": 150.0,
            "reason": "Customer requested refund - automated test"
        }
        
        refund_response = requests.post(
            f"{BASE_URL}/v1/payments/{payment_id}/refund",
            json=refund_data
        )
        assert refund_response.status_code == 200
        refunded_payment = refund_response.json()
        
        assert refunded_payment["status"] == "REFUNDED"
        assert refunded_payment["payment_id"] == payment_id
        
        print(f"✓ Refund workflow test passed: payment {payment_id} refunded")
    
    def test_metrics_endpoint(self):
        """Test that metrics endpoint returns expected metrics"""
        response = requests.get(f"{BASE_URL}/metrics")
        assert response.status_code == 200
        
        metrics_text = response.text
        
        # Check for required metrics
        assert "payments_created_total" in metrics_text
        assert "payments_failed_total" in metrics_text  # REQUIRED by assignment
        assert "total_amount_processed" in metrics_text
        assert "total_refunds" in metrics_text
        assert "payments_by_status" in metrics_text
        assert "payments_by_method" in metrics_text
        
        print("✓ Metrics endpoint test passed")
    
    def test_get_payment_by_order_id(self):
        """Test retrieving payment by order ID"""
        # Create a payment
        idempotency_key = f"test-get-{int(time.time())}"
        order_id = 99994
        
        payment_data = {
            "order_id": order_id,
            "user_id": 1,
            "amount": 75.0,
            "currency": "INR",
            "payment_method": "UPI"
        }
        
        headers = {"Idempotency-Key": idempotency_key}
        create_response = requests.post(
            f"{BASE_URL}/v1/payments/charge",
            json=payment_data,
            headers=headers
        )
        assert create_response.status_code == 201
        
        # Retrieve by order_id
        get_response = requests.get(f"{BASE_URL}/v1/payments/order/{order_id}")
        assert get_response.status_code == 200
        
        payment = get_response.json()
        assert payment["order_id"] == order_id
        
        print(f"✓ Get payment by order_id test passed: order={order_id}")
    
    def test_list_payments_with_filters(self):
        """Test listing payments with status filter"""
        response = requests.get(f"{BASE_URL}/v1/payments?status=COMPLETED&page=1&page_size=10")
        assert response.status_code == 200
        
        data = response.json()
        assert "total" in data
        assert "page" in data
        assert "payments" in data
        
        # All returned payments should have COMPLETED status
        for payment in data["payments"]:
            assert payment["status"] == "COMPLETED"
        
        print(f"✓ List payments with filter test passed: {len(data['payments'])} payments")

    def test_payment_has_transaction_history(self):
        """Test that payment includes transaction history"""
        idempotency_key = f"test-txn-{int(time.time())}"
        
        payment_data = {
            "order_id": 99993,
            "user_id": 1,
            "amount": 200.0,
            "currency": "INR",
            "payment_method": "CREDIT_CARD"
        }
        
        headers = {"Idempotency-Key": idempotency_key}
        response = requests.post(
            f"{BASE_URL}/v1/payments/charge",
            json=payment_data,
            headers=headers
        )
        assert response.status_code == 201
        
        payment = response.json()
        assert "transactions" in payment
        assert len(payment["transactions"]) > 0
        
        # Check transaction structure
        txn = payment["transactions"][0]
        assert "transaction_log_id" in txn
        assert "transaction_type" in txn
        assert "amount" in txn
        assert "status" in txn
        
        print(f"✓ Transaction history test passed: {len(payment['transactions'])} transactions")


def run_all_tests():
    """Run all integration tests"""
    print("\n" + "="*70)
    print("PAYMENT SERVICE INTEGRATION TESTS")
    print("="*70 + "\n")
    
    test_suite = TestPaymentServiceIntegration()
    
    tests = [
        ("Health Check", test_suite.test_health_check),
        ("Idempotency - Same Key", test_suite.test_idempotent_charge_same_key_same_response),
        ("Idempotency - Different Keys", test_suite.test_idempotent_charge_different_keys),
        ("Reference Field Generation", test_suite.test_charge_payment_creates_reference),
        ("Custom Reference", test_suite.test_charge_payment_with_custom_reference),
        ("Amount Validation", test_suite.test_payment_amount_validation),
        ("Refund Workflow", test_suite.test_refund_workflow),
        ("Metrics Endpoint", test_suite.test_metrics_endpoint),
        ("Get Payment by Order ID", test_suite.test_get_payment_by_order_id),
        ("List Payments with Filters", test_suite.test_list_payments_with_filters),
        ("Transaction History", test_suite.test_payment_has_transaction_history),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            print(f"\nRunning: {test_name}...")
            test_func()
            passed += 1
            print(f"✓ PASSED: {test_name}")
        except Exception as e:
            failed += 1
            print(f"✗ FAILED: {test_name}")
            print(f"  Error: {str(e)}")
    
    print("\n" + "="*70)
    print(f"TEST SUMMARY: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("="*70 + "\n")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
