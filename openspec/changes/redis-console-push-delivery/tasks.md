## 1. Add Redis-backed push storage

- [x] 1.1 Introduce a Redis-backed console push store keyed by tenant and session
- [x] 1.2 Preserve bounded retention and expiration behavior in the Redis implementation
- [x] 1.3 Keep a compatible append/take API so existing callers can migrate cleanly

## 2. Wire push writers and readers

- [x] 2.1 Update console channel send paths to publish push messages through the shared store
- [x] 2.2 Update cron push/error paths to publish through the shared store
- [x] 2.3 Update `/api/console/push-messages` to consume shared push delivery state

## 3. Verify cross-instance delivery

- [x] 3.1 Add tests for write-on-one-instance/read-on-another behavior
- [x] 3.2 Add tests for tenant and session isolation during push polling
- [x] 3.3 Add tests for expiry and bounded queue trimming behavior
