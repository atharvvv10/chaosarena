## Summary
- Incident: Network‑latency attack on **payment‑service** detected by the monitoring system.  
- Version: **v1.0.3**.  
- Detection latency: **14.0 s**.  
- Outcome: Service recovered, score **100**, grade **A**, verdict **PROMOTE**.

## Timeline
- **12:35:04 UTC** – Restart of **order‑service** requested in namespace **shop‑test**.  
- **12:35:18 UTC** – Evaluation completed; cleanup verified and no chaos objects remained.

## Root cause
- Diagnosis category: **latency_spike**.  
- Primary affected service: **order‑service** (confidence 0.99).  
- Evidence:  
  - `order-service_p95_latency z=+289.5`  
  - `payment-service_request_rate z=-7.5`  
  - `product-service_request_rate z=-7.0`

## Actions taken
- Restart of **order‑service** in namespace **shop‑test** (status: requested).  
- Attack cleanup succeeded; no chaos objects left behind.

## Outcome
- Service fully recovered.  
- Score 100 meets threshold 70.  
- Cleanup OK, chaos_objects_remaining = 0.  
- Verdict: **PROMOTE**.

## Follow-ups
- No deductions.  
- No additional follow‑up actions required.