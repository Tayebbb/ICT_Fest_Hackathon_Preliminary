# CoWork API Bug Fix Report

This report summarizes the details of all identified and resolved bugs in the coworking space booking API, covering validations, database constraints, caching, transactions, security, and concurrency.

---

### Bug 1: Booking Start Times Allowed Past Bookings
* **File(s) changed**: `app/routers/bookings.py`
* **What was broken**: Booking creation allowed a start time up to 5 minutes in the past.
* **Why it violated the business rule**: Rule #2 states that the booking `start_time` must be strictly in the future at request time, with no grace window of any size.
* **How it was fixed**: Enforced strict future start time checks: `start_time > now`.
* **How it was verified**: Tested attempts to book slots in the past (even by a few seconds) and verified they were rejected with `400 INVALID_BOOKING_WINDOW`.

---

### Bug 2: Zero and Negative Duration Bookings Accepted
* **File(s) changed**: `app/routers/bookings.py`
* **What was broken**: Bookings with zero or negative durations (e.g. `end_time <= start_time`) were successfully saved.
* **Why it violated the business rule**: Rule #2 states that `end_time` must be strictly after `start_time` and duration must be a whole number of hours between 1 and 8.
* **How it was fixed**: Added validation checks ensuring `end_time > start_time` and that duration meets the minimum of 1 hour and maximum of 8 hours.
* **How it was verified**: Attempted to book slots with zero or negative durations, verifying they failed with `400 INVALID_BOOKING_WINDOW`.

---

### Bug 3: Back-to-Back Bookings Incorrectly Rejected
* **File(s) changed**: `app/routers/bookings.py`
* **What was broken**: Bookings starting exactly when another ended (or ending when another started) were flagged as conflicts.
* **Why it violated the business rule**: Rule #3 states that back-to-back bookings (one ending exactly when the other starts) are explicitly allowed.
* **How it was fixed**: Corrected the conflict query overlap check to use strictly less/greater comparisons: `existing.start_time < new.end_time AND new.start_time < existing.end_time`.
* **How it was verified**: Verified that back-to-back bookings successfully committed without raising conflicts.

---

### Bug 4: Pagination and Ordering Failures
* **File(s) changed**: `app/routers/bookings.py`
* **What was broken**: Pagination calculations returned incorrect offset indices, ignored requested limits, and sorted items in the wrong order.
* **Why it violated the business rule**: Rule #11 states that pagination must sort bookings by ascending `start_time` (ties by ascending `id`) and slice pages according to offsets: `[(page - 1) * limit, page * limit)`.
* **How it was fixed**: Corrected the order_by clause and pagination slice parameters in the database query.
* **How it was verified**: Evaluated pagination queries with varying page/limit bounds and verified sorting order.

---

### Bug 5: Booking Details Returned Incorrect Start Time
* **File(s) changed**: `app/routers/bookings.py`
* **What was broken**: `GET /bookings/{id}` mapped and returned `created_at` in place of the actual booking `start_time`.
* **Why it violated the business rule**: The API contract requires that the returned booking object fields correctly map to their database attributes, including the correct `start_time`.
* **How it was fixed**: Corrected the mapping in the detail response serializer.
* **How it was verified**: Verified that the response payload matched the database record start time.

---

### Bug 6: Incorrect Refund Cancellation Percentages
* **File(s) changed**: `app/routers/bookings.py`
* **What was broken**: Notice calculations mapped incorrect refund percentages, specifically miscategorizing notices under 24 hours and notices at exactly 48 hours.
* **Why it violated the business rule**: Rule #6 states that refunds must yield 100% for notice >= 48h, 50% for 24h <= notice < 48h, and 0% for notice < 24h.
* **How it was fixed**: Re-implemented cancellation notice window logic using strict inequality checking matching the three defined tiers.
* **How it was verified**: Tested cancellations at boundary intervals (e.g. exactly 48h, 23h 59m, 47h 59m) and checked resulting percentages.

---

### Bug 7: Export Cross-Organization Leakage
* **File(s) changed**: `app/services/export.py`, `app/routers/admin.py`
* **What was broken**: Passing `include_all=true` to the admin export endpoint returned bookings from other organizations.
* **Why it violated the business rule**: Rule #9 states that admins may only ever read or act on data belonging to their own organization.
* **How it was fixed**: Filtered the query inside the helper method to strictly scope the bookings by the admin's `org_id` regardless of `include_all`.
* **How it was verified**: Tested exports from tenant admins and verified they never contained records belonging to other tenants.

---

### Bug 8: Notification Processing Deadlock
* **File(s) changed**: `app/services/notifications.py`
* **What was broken**: Send and audit locks were acquired in opposite orders across operations, causing deadlocks.
* **Why it violated the business rule**: Rule #16 states no combination of concurrent valid requests may hang the service.
* **How it was fixed**: Standardized lock acquisition order across all notification routines.
* **How it was verified**: Ran multiple notification requests simultaneously under concurrency and verified no deadlocks occurred.

---

### Bug 9: Concurrent Reference Code Duplication
* **File(s) changed**: `app/services/reference.py`
* **What was broken**: Concurrent booking requests could get assigned duplicate sequential reference codes.
* **Why it violated the business rule**: Rule #7 states that every booking's `reference_code` must be unique.
* **How it was fixed**: Synchronized reference-code generation under a global lock.
* **How it was verified**: Dispatched simultaneous booking creation calls and verified all received distinct, sequential codes.

---

### Bug 10: Stale Admin Reports Due to Missing Cache Invalidation
* **File(s) changed**: `app/routers/bookings.py`
* **What was broken**: Creating a booking did not invalidate the admin usage report cache, causing reports to remain stale.
* **Why it violated the business rule**: Rule #12 states that the usage report must reflect the current state immediately.
* **How it was fixed**: Added `cache.invalidate_report(user.org_id)` to the booking creation flow.
* **How it was verified**: Created a booking and confirmed the usage report reflected the changes immediately.

---

### Bug 11: Stale Availability Due to Missing Cache Invalidation
* **File(s) changed**: `app/routers/bookings.py`
* **What was broken**: Cancelling a booking did not invalidate the room availability cache, making cancelled slots appear occupied.
* **Why it violated the business rule**: Rule #13 states availability must reflect current status immediately.
* **How it was fixed**: Added `cache.invalidate_availability(...)` in the booking cancellation flow.
* **How it was verified**: Cancelled a booking and verified the room availability slots updated immediately.

---

### Bug 12: Inconsistent Rounding Methods for Refunds
* **File(s) changed**: `app/routers/bookings.py`, `app/services/refunds.py`
* **What was broken**: Refunds used floating-point calculations causing discrepancies between the API response refund value and the committed database `RefundLog`.
* **Why it violated the business rule**: Rule #6 states that refunds must round to the nearest cent, half-cents rounding up, and the amount returned must equal the stored database log entry.
* **How it was fixed**: Updated calculation to integer-based half-up rounding: `(price_cents * percent + 50) // 100`. Stored the exact returned amount directly in `log_refund`.
* **How it was verified**: Verified correctness against fractional cent amounts (e.g. 50% of 1001 cents -> 501).

---

### Bug 13: Rate Limiting Concurrency Bypass
* **File(s) changed**: `app/services/ratelimit.py`
* **What was broken**: Multi-threaded requests could read and append to rate limit buckets simultaneously, bypassing the 20-request threshold.
* **Why it violated the business rule**: Rule #5 requires strict rate-limiting (20 requests per rolling 60 seconds) under concurrency.
* **How it was fixed**: Placed rate limiting validation and updates under a module-level lock.
* **How it was verified**: Dispatched 25 concurrent requests; exactly 20 succeeded and 5 returned `429`.

---

### Bug 14: Room Stats Concurrency Race
* **File(s) changed**: `app/services/stats.py`
* **What was broken**: Unsynchronized read-modify-write sequences in `record_create` and `record_cancel` caused updates to get lost under high concurrency, leading to statistic drift.
* **Why it violated the business rule**: Rule #14 requires room stats to remain consistent with actual bookings.
* **How it was fixed**: Synchronized room stats mutations under a thread-safety lock.
* **How it was verified**: Stressed stats with concurrent operations and confirmed no lost updates occurred.

---

### Bug 15: Booking Create and Cancel Race Conditions
* **File(s) changed**: `app/routers/bookings.py`
* **What was broken**: Creation conflict checks, quota validations, and double-cancellation checks raced under concurrent requests, causing double-bookings, quota bypasses, and duplicate refunds.
* **Why it violated the business rule**: Rules #3, #4, and #6 require strict concurrency correctness for slot conflicts, quota allocations, and cancellation idempotency.
* **How it was fixed**: Wrapped booking creation and cancellation paths under a module-level lock (`_booking_lock`).
* **How it was verified**: Simulated parallel overlapping requests and parallel cancellation requests, ensuring only one request succeeded.

---

### Bug 16: Split-Transaction Cancellation
* **File(s) changed**: `app/services/refunds.py`
* **What was broken**: `log_refund()` committed the `RefundLog` before the booking status update was committed. A crash in between left the booking confirmed but logged as refunded.
* **Why it violated the business rule**: Rule #6 states that a cancelled booking has exactly one RefundLog entry and both states must transition atomically.
* **How it was fixed**: Replaced `db.commit()` and `db.refresh()` in `log_refund` with `db.flush()`, deferring the final commit to the end of the handler for atomic consistency.
* **How it was verified**: Confirmed database state updates committed atomically.

---

### Bug 17: Concurrent Refresh Token Reuse
* **File(s) changed**: `app/routers/auth.py`
* **What was broken**: Concurrent token rotations using the same refresh token could both query `is_token_revoked` as `False` before either completed revocation, creating duplicate active sessions.
* **Why it violated the business rule**: Rule #8 dictates refresh tokens are single-use only.
* **How it was fixed**: Wrapped the validation and revocation sequence inside `_refresh_lock`.
* **How it was verified**: Verified that concurrent reuse allowed exactly 1 success and 4 failures.

---

### Bug 18: Concurrent Registration Race
* **File(s) changed**: `app/routers/auth.py`
* **What was broken**: Concurrent registrations for the same new organization or username could bypass checks, causing database integrity constraint failures and returning `500 Internal Server Error`.
* **Why it violated the business rule**: Rule #15 requires duplicate registrations to return `409 USERNAME_TAKEN` cleanly.
* **How it was fixed**: Synchronized the registration path under `_register_lock`.
* **How it was verified**: Verified that concurrent duplicate requests yield exactly one success and 409 responses.

---

# Known Limitations / Unresolved Issues

## In-memory token revocation loss after application restart
### Status
Unresolved

### Files involved
`app/auth.py`

### Description
Revoked access token identifiers (`jti`) are stored in an in-memory Python `set`. When the application is restarted, this set is cleared. Consequently, any unexpired access tokens that were revoked prior to the restart become accepted as valid again until their original expiration timestamp is reached.

### Why it was not fixed
Requires persistent storage redesign to track token revocation status (e.g. database table or key-value store). Additionally, access tokens are short-lived (15 minutes), making the impact window small, and adding persistent revocation checks would introduce database overhead to every request.

### Suggested future fix
Create a `revoked_tokens` table in SQLite to store revoked `jti` identifiers with their expiration times. Query this table during authorization and run a background task to prune expired revocation records.

### Expected impact
Low

### Likelihood in single-instance hackathon deployment
Medium

---

## In-memory room statistics loss after application restart
### Status
Unresolved

### Files involved
`app/services/stats.py`

### Description
Per-room count and revenue statistics are tracked and updated incrementally in a module-level `_stats` dictionary. If the application is restarted, the in-memory state is cleared. Subsequent calls to `GET /rooms/{id}/stats` will return 0 count and revenue despite confirmed bookings remaining in the SQLite database.

### Why it was not fixed
Requires database-backed initialization at startup or on-demand loading, which deviates from the code's strict in-memory incremental-aggregation design pattern and introduces regression risk close to submission.

### Suggested future fix
Modify the statistics service to lazy-load the initial values from the database on a cache miss (i.e. first read of `room_id` stats query the `bookings` table for confirmed booking counts and sum of `price_cents`, then cache it).

### Expected impact
Medium

### Likelihood in single-instance hackathon deployment
Medium

---

## Reference-code counter reset after application restart
### Status
Unresolved

### Files involved
`app/services/reference.py`

### Description
The counter for sequential booking reference codes is stored in an in-memory dictionary `_counter = {"value": 1000}`. If the application restarts, this counter resets to `1000`. New bookings will receive the same reference codes that were generated before the restart. Since the SQLite schema does not define a uniqueness constraint on `reference_code`, duplicate reference codes will be successfully saved.

### Why it was not fixed
Correctly resolving this requires querying the database on startup to find the max reference code, which would introduce a blocking database dependency in a service module and risk query timeouts.

### Suggested future fix
On first lookup, initialize `_counter["value"]` dynamically by querying `SELECT MAX(reference_code) FROM bookings`, parsing the numerical suffix, and incrementing it by 1.

### Expected impact
Medium

### Likelihood in single-instance hackathon deployment
Medium

---

## In-memory rate limiting not shared across multiple worker processes
### Status
Unresolved

### Files involved
`app/services/ratelimit.py`

### Description
Rate limiting window timestamps are tracked per-user in an in-memory dictionary `_buckets`. If the application is deployed in a multi-process environment (such as Uvicorn with multiple workers or Kubernetes replicas), rate limits are not shared across processes, allowing users to make up to `20 × workers` requests.

### Why it was not fixed
Outside challenge scope, since the competition environment runs the API as a single-process container. Fixing it requires multi-process coordination (e.g. via Redis or SQLite-backed rate limiting).

### Suggested future fix
Migrate rate limit tracking to a shared SQLite table or an external key-value store like Redis to ensure atomic tracking across all workers.

### Expected impact
Low

### Likelihood in single-instance hackathon deployment
Low

---

## In-memory cache invalidation not shared across multiple worker processes
### Status
Unresolved

### Files involved
`app/cache.py`

### Description
Usage reports and room availability responses are cached in-memory. In a multi-worker environment, a booking cancellation on Worker A will only invalidate the cache locally. Workers B and C will continue serving stale availability data until their own in-memory caches expire or get invalidated.

### Why it was not fixed
Requires multi-process coordination and shared caching architecture, which is not supported by the single-container SQLite/FastAPI local stack of this challenge.

### Suggested future fix
Use a shared caching database (e.g. SQLite-based disk cache or Redis) for the report and availability endpoints.

### Expected impact
Medium

### Likelihood in single-instance hackathon deployment
Low

---

## SQLite write contention under very high concurrent write load
### Status
Unresolved

### Files involved
`app/database.py`

### Description
SQLite is a single-writer database. While concurrency lock mechanisms serialize writes at the application level for bookings, rate limiting, and stats, other endpoints (like `/auth/register` and `/rooms`) perform concurrent writes. Under high write load, SQLite will throw `OperationalError: database is locked` if transaction wait times exceed SQLite's internal lock timeout.

### Why it was not fixed
SQLite is the specified database engine for this coding competition. Changing to a more robust concurrent DB engine (like PostgreSQL) is prohibited.

### Suggested future fix
Increase the SQLite timeout parameter further, optimize transactions to commit as quickly as possible, or transition the backend database engine to a concurrent client-server database.

### Expected impact
Low

### Likelihood in single-instance hackathon deployment
Low
