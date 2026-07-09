# CoWork API Bug Fix Report

This document details the root cause, specification violation, resolution, and verification for the identified and resolved defects within the coworking space booking API.

---

# Bug 1: Past Booking Acceptance Window

## Affected Components
- `app/routers/bookings.py`
- `create_booking`

## Root Cause
The validation check for the booking start time permitted timestamps falling up to 5 minutes in the past due to an overly permissive window configuration in the validation condition.

## Specification Violation
Rule #2: The booking `start_time` must be strictly in the future relative to the request execution time, with no grace period allowed.

## Resolution
Enforced strict inequality checking where the naive UTC `start_time` must be greater than `now` (`start > now`).

## Verification
- **Runtime Validation**: Verified that request payloads with past timestamps (ranging from seconds to minutes) are rejected with HTTP status code `400` and error code `INVALID_BOOKING_WINDOW`.

---

# Bug 2: Missing Booking Duration Validation

## Affected Components
- `app/routers/bookings.py`
- `create_booking`

## Root Cause
The controller endpoint lacked validation checks for negative, zero, or excessively large duration windows between `start_time` and `end_time`.

## Specification Violation
Rule #2: Booking duration must be a whole number of hours, with a minimum of 1 hour and a maximum of 8 hours. Additionally, `end_time` must be strictly after `start_time`.

## Resolution
Added validation checks to ensure that the duration evaluates to a whole number of hours, `end_time > start_time`, and the duration satisfies `1 <= duration_hours <= 8`.

## Verification
- **Runtime Validation**: Attempting to create bookings with zero, negative, or duration values greater than 8 hours returns HTTP status `400` and error code `INVALID_BOOKING_WINDOW`.

---

# Bug 3: Incorrect Overlap Detection for Adjacent Bookings

## Affected Components
- `app/routers/bookings.py`
- `_has_conflict`

## Root Cause
The booking collision query used inclusive range boundary checks, causing back-to-back bookings (where one booking ends exactly when another starts) to be treated as overlapping.

## Specification Violation
Rule #3: Confirmed bookings overlap if `existing.start_time < new.end_time AND new.start_time < existing.end_time`. Back-to-back bookings are permitted.

## Resolution
Updated the query condition to perform exclusive interval overlap validation, checking strictly that the start of the new booking is less than the end of the existing booking, and the end of the new booking is greater than the start of the existing booking.

## Verification
- **Runtime Validation**: Verified that adjacent bookings (e.g., Slot A: 10:00–11:00, Slot B: 11:00–12:00) successfully commit without raising `409 ROOM_CONFLICT`.

---

# Bug 4: Incorrect Pagination Ordering

## Affected Components
- `app/routers/bookings.py`
- `list_bookings`

## Root Cause
The database query for list retrieval did not apply the correct order-by criteria, resulting in unsorted or incorrectly ordered records.

## Specification Violation
Rule #11: Paginated booking results must be sorted by ascending `start_time` with ties resolved by ascending booking `id`.

## Resolution
Updated the SQL query structure to append the sorting expression `.order_by(Booking.start_time.asc(), Booking.id.asc())`.

## Verification
- **Runtime Validation**: Confirmed sorting orders return bookings with ascending `start_time` and ascending `id` values for ties.

---

# Bug 5: Incorrect Pagination Offset Calculation

## Affected Components
- `app/routers/bookings.py`
- `list_bookings`

## Root Cause
The pagination index offset calculation was off-by-one, resulting in skipped or duplicated booking records on subsequent page queries.

## Specification Violation
Rule #11: Paginated results for page $N$ and limit $L$ must return items falling in the database offset range `[(N-1) * L, N * L)`.

## Resolution
Modified the query pagination slicing logic to calculate the start offset as `(page - 1) * limit` and bound the limit correctly.

## Verification
- **Runtime Validation**: Queried sequential pages and verified that page boundary items do not repeat or skip.

---

# Bug 6: Pagination Ignored Requested Limit

## Affected Components
- `app/routers/bookings.py`
- `list_bookings`

## Root Cause
The pagination logic did not apply the client-provided `limit` query parameter to the underlying database execution query, returning default limit slices instead.

## Specification Violation
Rule #11: Pagination queries must respect the requested limit range of 1–100 (defaulting to 10).

## Resolution
Applied the validated `limit` parameter directly to the SQLAlchemy query `.limit(limit)` method.

## Verification
- **Runtime Validation**: Sent requests with varying limit values (e.g., `limit=5`, `limit=50`) and verified the correct item count was returned.

---

# Bug 7: Booking Detail Endpoint Returned Incorrect Start Time

## Affected Components
- `app/routers/bookings.py`
- `get_booking`

## Root Cause
The response mapping inside the handler serializer mapped the database `created_at` timestamp field to the API response object's `start_time` key.

## Specification Violation
The API response schema for `GET /bookings/{id}` must return the correct `start_time` attribute of the requested entity.

## Resolution
Corrected the response mapping expression to associate `start_time` with the booking entity's actual `start_time` database column.

## Verification
- **Runtime Validation**: Verified that details response data matches the database record's start time instead of its creation timestamp.

---

# Bug 8: Incorrect Refund Tier Calculation

## Affected Components
- `app/routers/bookings.py`
- `cancel_booking`

## Root Cause
The notice duration delta calculation used incorrect comparison operators, misallocating boundary windows exactly at 48 hours or under 24 hours.

## Specification Violation
Rule #6: Notice period is calculated as `start_time - cancellation_time`. Notice >= 48h yields 100% refund, 24h <= notice < 48h yields 50% refund, and notice < 24h yields 0% refund.

## Resolution
Implemented strict boundary validations on the cancellation notice time delta to correctly allocate the 100%, 50%, and 0% tiers.

## Verification
- **Runtime Validation**: Tested cancellations at exact windows (exactly 48h, 23h 59m, 24h 01m) and verified the correct refund percentages.

---

# Bug 9: Inconsistent Refund Amount Rounding

## Affected Components
- `app/routers/bookings.py`, `app/services/refunds.py`
- `cancel_booking`, `log_refund`

## Root Cause
Refund values were calculated using floating-point divisions, introducing precision rounding issues. Furthermore, the cancellation handler and `log_refund` recalculated the refund independently, leading to mismatches.

## Specification Violation
Rule #6: The refund amount must round to the nearest cent, half-cents rounding up. The amount returned by the API response must exactly equal the value stored in the `RefundLog`.

## Resolution
Converted the calculation to integer math: `refund_amount_cents = (price_cents * refund_percent + 50) // 100`. Updated `log_refund` to accept the exact calculated cent value.

## Verification
- **Runtime Validation**: Confirmed that refund calculations map correctly for boundary cents (e.g. 50% of 1001 cents -> 501).

---

# Bug 10: Usage Report Cache Invalidation Mismatch

## Affected Components
- `app/routers/bookings.py`
- `create_booking`

## Root Cause
Creating a new booking failed to trigger invalidation of the cached usage reports for the organization.

## Specification Violation
Rule #12: The usage report must reflect the current state of confirmed bookings immediately.

## Resolution
Added `cache.invalidate_report(user.org_id)` to the booking creation transaction path.

## Verification
- **Runtime Validation**: Verified that creating a booking immediately invalidates the admin usage report cache.

---

# Bug 11: Availability Cache Invalidation Mismatch

## Affected Components
- `app/routers/bookings.py`
- `cancel_booking`

## Root Cause
Booking cancellations did not invalidate the cached availability busy intervals for the room and date.

## Specification Violation
Rule #13: Room availability queries must reflect the current booking state immediately.

## Resolution
Added `cache.invalidate_availability(booking.room_id, booking.start_time.date().isoformat())` inside the cancellation handler.

## Verification
- **Runtime Validation**: Cancelling a booking immediately marks the corresponding slot as "free" in subsequent availability cache queries.

---

# Bug 12: Cross-Organization Export Data Exposure

## Affected Components
- `app/services/export.py`, `app/routers/admin.py`
- `generate_export`, `_fetch_scoped`

## Root Cause
The export query failed to filter results by the admin's `org_id` when `include_all=true` was specified, returning booking records belonging to other tenants.

## Specification Violation
Rule #9 (Multi-tenancy): Administrative operations must be scoped strictly to resources belonging to the authenticated user's organization.

## Resolution
Enforced global organizational scoping by joining the `Room` model in the query and appending `.filter(Room.org_id == org_id)`.

## Verification
- **Runtime Validation**: Executed exports with `include_all=true` and verified that no cross-tenant records were leaked.

---

# Bug 13: Notification Lock-Order Deadlock

## Affected Components
- `app/services/notifications.py`
- `notify_created`, `notify_cancelled`

## Root Cause
The email dispatch lock and database audit write lock were acquired in opposite orders across separate notification operations, leading to deadlock conditions under load.

## Specification Violation
Rule #16 (Liveness): The application must not lock or hang under concurrent processing conditions.

## Resolution
Refactored the locks to ensure the email lock is always acquired first, followed by the audit lock across all handlers.

## Verification
- **Concurrency Validation**: Ran parallel notification operations under high concurrent load and verified execution did not deadlock.

---

# Bug 14: Reference Code Generation Race Condition

## Affected Components
- `app/services/reference.py`
- `next_reference_code`

## Root Cause
The booking reference-code counter read and write sequence was not synchronized, allowing parallel threads to read the same counter value and issue duplicate codes.

## Specification Violation
Rule #7: Every booking's `reference_code` must be unique under concurrent creation.

## Resolution
Wrapped the counter read-modify-write block under a global mutex lock (`_counter_lock = threading.Lock()`).

## Verification
- **Concurrency Validation**: Dispatched parallel booking requests and confirmed all issued reference codes were unique and sequential.

---

# Bug 15: Booking Rate-Limit Race Condition

## Affected Components
- `app/services/ratelimit.py`
- `check_rate_limit`

## Root Cause
Checking, trimming, and updating rolling rate-limit windows was unsynchronized, permitting multiple concurrent requests to slip through validation before timestamps were recorded.

## Specification Violation
Rule #5: Booking creation requests are limited to 20 requests per rolling 60 seconds per user (all requests count).

## Resolution
Wrapped the rate limiter read-trim-append-write sequence in a module-level lock (`_bucket_lock = threading.Lock()`).

## Verification
- **Concurrency Validation**: Sent 25 simultaneous creation requests; exactly 20 were accepted and 5 returned `429 RATE_LIMITED`.

---

# Bug 16: Room Statistics Race Condition

## Affected Components
- `app/services/stats.py`
- `record_create`, `record_cancel`

## Root Cause
Incremental room statistics updates performed read-modify-write operations without synchronization. The context switch during the artificial sleep in `_aggregate_pause()` led to lost updates.

## Specification Violation
Rule #14: Room statistics must remain consistent with the database bookings.

## Resolution
Synchronized stats queries and writes inside the statistics service using a thread lock (`_stats_lock = threading.Lock()`).

## Verification
- **Concurrency Validation**: Executed concurrent creations and cancellations under load, verifying stats counts and revenues matched actual database records.

---

# Bug 17: Booking Creation Overlap Race Condition

## Affected Components
- `app/routers/bookings.py`
- `create_booking`

## Root Cause
Overlap checking and booking persistence were unsynchronized, allowing two parallel threads to pass overlap validation before either committed, leading to double-booked rooms.

## Specification Violation
Rule #3: Overlapping confirmed bookings for the same room are prohibited.

## Resolution
Wrapped the booking validation, reference generation, and database commit block inside a module-level lock (`_booking_lock = threading.Lock()`).

## Verification
- **Concurrency Validation**: Dispatched parallel overlapping booking requests; exactly one succeeded and the other returned `409 ROOM_CONFLICT`.

---

# Bug 18: Booking Quota Race Condition

## Affected Components
- `app/routers/bookings.py`
- `create_booking`

## Root Cause
Validation of the 24-hour booking limit occurred without thread synchronization, allowing concurrent requests to bypass the quota check before records were committed.

## Specification Violation
Rule #4: Members may hold at most 3 confirmed bookings in the `(now, now + 24h]` window.

## Resolution
Serialized the quota validation query and record commits inside the `create_booking` critical section using `_booking_lock`.

## Verification
- **Concurrency Validation**: Tried to concurrently book 4 slots in the 24-hour window; exactly 3 succeeded and the 4th returned `409 QUOTA_EXCEEDED`.

---

# Bug 19: Duplicate Refund Generation Race Condition

## Affected Components
- `app/routers/bookings.py`
- `cancel_booking`

## Root Cause
Cancellation checking and `RefundLog` generation were unsynchronized. Concurrent cancellation requests for the same booking passed the status check, generating multiple `RefundLog` entries.

## Specification Violation
Rule #6: A cancelled booking must have exactly one `RefundLog` entry in the database.

## Resolution
Wrapped the booking status validation, refund calculation, log creation, and database commit under the `_booking_lock` block.

## Verification
- **Concurrency Validation**: Dispatched concurrent cancellation requests for a single booking; exactly one succeeded and others returned `409 ALREADY_CANCELLED`.

---

# Bug 20: Split Transaction Cancellation Inconsistency

## Affected Components
- `app/services/refunds.py`
- `log_refund`

## Root Cause
`log_refund()` committed the `RefundLog` database record independently before the booking status update was committed in the handler. A crash in between left the booking `"confirmed"` while logging it as `"refunded"`.

## Specification Violation
Rule #6: Cancellation state transitions and refund logging must be atomic.

## Resolution
Removed `db.commit()` and `db.refresh()` from `log_refund()` and replaced them with `db.flush()`. This defers persistence to the single, atomic commit at the end of the cancellation handler.

## Verification
- **Runtime Validation**: Verified that both the `RefundLog` insertion and the status update commit together or roll back atomically.
- **Regression Testing**: Confirmed existing test suites continue to pass.

---

# Known Limitations

## Multi-Worker Concurrency Scaling
### Status
Unresolved (Architectural Constraint)

### Files involved
`app/routers/bookings.py`, `app/routers/auth.py`, `app/services/ratelimit.py`, `app/services/stats.py`

### Description
Concurrency validation, rate limiting, and stats updates are synchronized using in-memory mutex locks (`threading.Lock()`). When deployed across multiple worker processes (e.g. Uvicorn with multiple workers or Kubernetes replicas), these locks are not shared. This allows race conditions to trigger across processes.

### Why it was not fixed
Correcting this requires a centralized distributed lock mechanism (such as Redis or select-for-update database locks), which is outside the single-instance SQLite/FastAPI architecture of this competition.

### Suggested future fix
Transition the locking strategy to use database row locks (`SELECT ... FOR UPDATE`) or a distributed lock manager (e.g., Redis Redlock).

### Expected impact
Medium

---

## Stateful In-Memory Caching and Session Revocation
### Status
Unresolved (Architectural Constraint)

### Files involved
`app/auth.py`, `app/cache.py`

### Description
Token revocation lists (`_revoked_tokens`) and endpoint caches are stored in local in-memory structures. In multi-worker deployments, a logout or cache invalidation on one worker process does not propagate to others, leading to state inconsistencies.

### Why it was not fixed
Requires a shared distributed cache or session database, which introduces heavy external dependencies.

### Suggested future fix
Store revoked token claims in the SQLite database and migrate caching to a shared database-backed or memory-grid cache.

### Expected impact
Medium

---

## State Loss across Application Restarts
### Status
Unresolved (Architectural Constraint)

### Files involved
`app/auth.py`, `app/services/stats.py`, `app/services/reference.py`

### Description
Room statistics, booking reference counters, and token revocation records are kept in-memory. If the container or application process restarts, this state is wiped, resetting stats and reference numbering counters.

### Why it was not fixed
Requires schema migrations and startup database scanning routines, which introduce execution overhead.

### Suggested future fix
Lazy-load stats from the database on a cache miss, initialize reference counters by scanning the max booking reference code in the database, and persist revoked tokens to a database table.

### Expected impact
Medium
