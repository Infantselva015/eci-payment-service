# PowerShell script to test idempotent payment charge
# Both requests should return the same payment_id

$IdempotencyKey = "test-key-" + (Get-Date -Format "yyyyMMddHHmmss")

Write-Host "First request with Idempotency-Key: $IdempotencyKey" -ForegroundColor Green

$body = @{
    order_id = 9001
    user_id = 701
    amount = 1999.99
    currency = "INR"
    payment_method = "UPI"
} | ConvertTo-Json

$headers = @{
    "Content-Type" = "application/json"
    "Idempotency-Key" = $IdempotencyKey
}

$response1 = Invoke-RestMethod -Uri "http://localhost:8086/v1/payments/charge" -Method Post -Body $body -Headers $headers
Write-Host "`nFirst Response:" -ForegroundColor Yellow
$response1 | ConvertTo-Json -Depth 5

Write-Host "`n`nSecond request with SAME Idempotency-Key: $IdempotencyKey" -ForegroundColor Green
Write-Host "Should return the same payment_id without creating a new payment" -ForegroundColor Cyan

$response2 = Invoke-RestMethod -Uri "http://localhost:8086/v1/payments/charge" -Method Post -Body $body -Headers $headers
Write-Host "`nSecond Response:" -ForegroundColor Yellow
$response2 | ConvertTo-Json -Depth 5

Write-Host "`n`nComparison:" -ForegroundColor Magenta
if ($response1.payment_id -eq $response2.payment_id) {
    Write-Host "✓ PASS: Both responses have the same payment_id ($($response1.payment_id))" -ForegroundColor Green
    Write-Host "✓ Idempotency is working correctly!" -ForegroundColor Green
} else {
    Write-Host "✗ FAIL: Different payment_ids returned ($($response1.payment_id) vs $($response2.payment_id))" -ForegroundColor Red
}
