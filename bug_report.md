# CoWork API Bug Fix Report

This report summarizes the details of the fixed bugs in the coworking space booking API, including validations, caching, transactions, and concurrency issues.

---

### Bugs 1–11 (Route Scope and Notification Liveness)
* **File(s) changed**: `app/routers/admin.py`, `app/services/export.py`, `app/services/notifications.py`
* **What was broken**: 
  - Administrative exports did not enforce proper organizational scoping when exporting all bookings.
  - Notifications were prone to deadlocks or blocking behavior under sequential/concurrent calls.
* **Why it violated the business rule**: 
  - Rule #9 (Multi-tenancy): Users must only ever read or act on data belonging to their own organization.
  - Rule #16 (Liveness): The service must respond to all endpoints at all times and not hang under concurrent stress.
* **How it was fixed**: 
  - Restructured export logic to scope every query strictly by `org_id` and correct parameters.
  - Optimized locks in `app/services/notifications.py` to prevent circular dependencies or deadlock states.
* **How it was verified**: Evaluated via integration tests checking organization isolation and load tests verifying notification delivery without blocking.

---

### Bug 12: Refund Rounding and RefundLog Consistency
* **File(s) changed**: `app/routers/bookings.py`, `app/services/refunds.py`
* **What was broken**: 
  - Refund calculations used float division which introduced floating-point rounding errors.
  - The logged refund in `RefundLog` was re-derived from the refund percentage, resulting in drift between the returned refund amount and the stored log entry.
* **Why it violated the business rule**: Rule #6 states that the refund amount must round to the nearest cent (half-cents rounding up), and the returned amount must exactly equal the amount stored in the `RefundLog`.
* **How it was fixed**: 
  - Transitioned the refund calculation in `bookings.py` to integer-based half-up rounding: `refund_amount_cents = (booking.price_cents * refund_percent + 50) // 100`.
  - Changed `log_refund` to accept the exact calculated `amount_cents` and write it directly.
* **How it was verified**: Tested with boundary amounts (e.g. 50% of 35 cents -> 18, 50% of 1001 cents -> 501) and asserted equality between the cancellation response and database log.

---

### Bug 14: Availability Cache Invalidation after Cancellation
* **File(s) changed**: `app/routers/bookings.py`
* **What was broken**: Cancelling a booking did not invalidate the availability cache for that room and date.
* **Why it violated the business rule**: Rule #13 requires that availability queries (`GET /rooms/{id}/availability`) reflect the current booking state immediately. Stale cached entries made cancelled slots appear busy.
* **How it was fixed**: Added a call to `cache.invalidate_availability(booking.room_id, booking.start_time.date().isoformat())` inside the `cancel_booking` flow before committing.
* **How it was verified**: Queried availability of a room, booked it, cancelled the booking, and verified the slot immediately returned to "free" in subsequent availability requests.

---

### Bug 18: Concurrency Violations in Rate Limiting
* **File(s) changed**: `app/services/ratelimit.py`
* **What was broken**: The rate limiting logic performed checking, trimming, pausing, and writing to the memory bucket without synchronization, allowing concurrent requests to bypass the limit.
* **Why it violated the business rule**: Rule #5 states booking creation is limited to 20 requests per rolling 60 seconds per user, including rejected requests.
* **How it was fixed**: Wrapped the rate limit read/trim/append/write sequence inside a module-level lock (`_bucket_lock = threading.Lock()`).
* **How it was verified**: Sent 25 simultaneous requests from a single user; exactly 20 succeeded and 5 returned `429 RATE_LIMITED`.

---

### Bug 19: Room Stats Concurrency Race
* **File(s) changed**: `app/services/stats.py`
* **What was broken**: Incremental statistics updates (`record_create` and `record_cancel`) performed read-modify-write operations unsynchronized. The artificial sleep in `_aggregate_pause()` context-switched threads, causing lost updates under load.
* **Why it violated the business rule**: Rule #14 requires that room stats count and revenue must always be consistent with the database bookings themselves. Lost updates caused stats to drift.
* **How it was fixed**: Wrapped the update sequences inside `record_create` and `record_cancel` under a module-level lock (`_stats_lock = threading.Lock()`).
* **How it was verified**: Executed simultaneous creations and cancellations, confirming final count and revenue matched actual bookings perfectly.

---

### Bug 20: Booking Create and Cancel Concurrency Violations
* **File(s) changed**: `app/routers/bookings.py`
* **What was broken**: 
  - Overlapping booking checks and quota validations were run without synchronization, permitting double-bookings and quota bypasses.
  - Cancellation requests on the same booking raced, committing multiple duplicate `RefundLog` entries.
* **Why it violated the business rule**: Rules #3, #4, and #6 dictate strict enforcement of double-booking prevention, 3-booking rolling quota limit, and single `RefundLog` generation.
* **How it was fixed**: Created a module-level lock (`_booking_lock = threading.Lock()`) and wrapped the critical sections of both `create_booking` and `cancel_booking` in it.
* **How it was verified**: Tested with multi-threaded clients sending concurrent overlapping slots, concurrent quota-crossing bookings, and concurrent duplicate cancellation requests.

---

### Concurrent Refresh Token Rotation
* **File(s) changed**: `app/routers/auth.py`
* **What was broken**: Multiple concurrent token rotations (`POST /auth/refresh`) using the same refresh token could both query `is_token_revoked` as `False` before either completed `revoke_access_token`, creating duplicate active sessions.
* **Why it violated the business rule**: Rule #8 dictates refresh tokens are single-use only, and reuse must trigger a `401`.
* **How it was fixed**: Introduced `_refresh_lock = threading.Lock()` and wrapped the rotation verification and revocation sequence inside the lock.
* **How it was verified**: Sent 5 concurrent refresh requests with the same token; exactly 1 succeeded and 4 returned `401`.

---

### Concurrent Registration Race
* **File(s) changed**: `app/routers/auth.py`
* **What was broken**: Concurrent registration requests for the same new organization or username could bypass the validation checks and write to the database, causing one thread to crash with a `500 Internal Server Error` due to SQLite constraint violations.
* **Why it violated the business rule**: Rule #15 requires duplicate registrations to return a clean `409 USERNAME_TAKEN` instead of crashing.
* **How it was fixed**: Introduced `_register_lock = threading.Lock()` and wrapped the registration transaction path in it.
* **How it was verified**: Dispatched 5 concurrent duplicate registrations; exactly 1 succeeded and 4 returned `409 USERNAME_TAKEN`.

---

### Split-Transaction Cancellation
* **File(s) changed**: `app/services/refunds.py`
* **What was broken**: `log_refund()` committed the `RefundLog` record before `cancel_booking` committed the status update to `"cancelled"`. A process crash or network drop in between would leave the booking `"confirmed"` while committing the `RefundLog`.
* **Why it violated the business rule**: Rule #6 requires cancellation and refund logging to be consistent and atomic.
* **How it was fixed**: Removed `db.commit()` and `db.refresh()` from `log_refund()` and replaced them with `db.flush()`. This keeps the database transaction active so the `RefundLog` and booking status update are committed atomically at the end of the handler.
* **How it was verified**: Verified that the cancellation commits both states atomically, preventing database drift on intermediate failures.
