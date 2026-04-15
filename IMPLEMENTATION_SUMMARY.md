# Implementation Summary: Group Credit Adjustments Feature

## Date: 2026-04-14 (Updated 2026-04-15)

## Overview

This implementation summary covers three key features:

1. **Automatic Group Credit Adjustments**: Automatic application of group default credits to user balances when group memberships change
2. **Dry-Run Mode**: Preview credit adjustments before applying them to ensure accuracy and prevent unintended changes
3. **Default Credits Configuration**: Configurable default credit amounts for groups and users via environment variables

---

## Problem Statement

Previously, when a user's group membership changed or when group default credits were updated:
- `total_default_credits` was calculated correctly (sum of all group defaults)
- But the actual `balance` in the database was NOT adjusted automatically
- Credits were only applied during the monthly reset

**Impact**: Users added to groups didn't receive their entitled credits until the next monthly reset. Users removed from groups kept credits they shouldn't have.

---

## Solution

Added an additive adjustment system that:
1. Tracks the last applied default credits per user (`last_applied_default_credits`)
2. Calculates the difference between current and last-applied defaults
3. Applies the difference additively to the current balance
4. Logs each adjustment as a transaction

**Formula**: `new_balance = current_balance + (new_default_credits - old_default_credits)`

---

## Implementation Details

### Files Modified

#### 1. `credit_admin/app/database.py`

**Schema Changes** (PostgreSQL - line 107):
```sql
ALTER TABLE credit_users ADD COLUMN IF NOT EXISTS last_applied_default_credits REAL NOT NULL DEFAULT 0.0
```

**Schema Changes** (SQLite - line 320):
```sql
ALTER TABLE credit_users ADD COLUMN last_applied_default_credits REAL DEFAULT 0.0
```

**New Method** (line 1088):
```python
def apply_group_credit_adjustments(self, force_all: bool = False) -> Dict[str, Any]:
    """
    Apply default credit changes to user balances based on current group memberships.
    
    Args:
        force_all: If True, adjust ALL users. If False, only adjust users with changes.
    
    Returns:
        Dict with adjustment results (users_adjusted, total_adjustment, details)
    """
```

**Key Features**:
- Iterates through all users with their group memberships
- Compares `total_default_credits` with `last_applied_default_credits`
- Applies additive adjustment when differences are detected
- Logs single transaction per user with type `group_adjustment`
- Updates `last_applied_default_credits` after adjustment
- Supports `force_all` mode to adjust all users regardless of changes

#### 2. `credit_admin/app/config.py` (line 53)

**New Configuration**:
```python
AUTO_APPLY_GROUP_CREDITS = os.getenv("AUTO_APPLY_GROUP_CREDITS", "true").lower() == "true"
```

**Usage**: Set `AUTO_APPLY_GROUP_CREDITS=false` in environment to disable automatic adjustments during sync.

#### 3. `credit_admin/app/api/credits_v2.py`

**New Import** (line 14):
```python
from app.config import DB_FILE, DATABASE_URL, AUTO_APPLY_GROUP_CREDITS
```

**New API Endpoint** (line 773):
```python
@router.post("/api/credits/apply-group-adjustments", tags=["admin"])
async def apply_group_adjustments(
    request: dict,
    current_user: User = Depends(get_current_admin_user)
):
    """Manually trigger application of group default credits to user balances."""
```

**Sync Integration** (line 702):
```python
if AUTO_APPLY_GROUP_CREDITS:
    adjustment_result = db.apply_group_credit_adjustments()
    result["adjustments"] = adjustment_result
```

---

## API Reference

### Manual Adjustment Endpoint

**POST** `/api/credits/apply-group-adjustments`

**Authentication**: Admin required (`get_current_admin_user`)

**Request Body**:
```json
{
  "force_all": false,
  "dry_run": false
}
```

**Parameters**:
- `force_all` (boolean, optional): If true, adjust all users regardless of whether their default credits have changed. Default: `false`
- `dry_run` (boolean, optional): If true, preview adjustments without applying them to the database. Default: `false`

**Response** (Success - Dry Run):
```json
{
  "status": "success",
  "message": "Preview: Would adjust 5 users with total adjustment of 5000 credits",
  "details": {
    "users_adjusted": 5,
    "total_adjustment": 5000.0,
    "dry_run": true,
    "details": [
      {
        "user_id": "user123",
        "user_name": "John Doe",
        "adjustment": 1000,
        "new_balance": 2000,
        "old_default_credits": 0,
        "new_default_credits": 1000,
        "preview_only": true
      }
    ]
  }
}
```

**Response** (Error):
```json
{
  "status": "error",
  "message": "Group adjustment failed: <error details>"
}
```

---

## Transaction Logging

Each adjustment creates a transaction record:

```sql
INSERT INTO credit_transactions 
(user_id, amount, transaction_type, reason, actor, balance_after)
VALUES (%s, %s, %s, %s, %s, %s)
```

**Example Transaction**:
- `transaction_type`: `group_adjustment`
- `reason`: `Group credit adjustment: +1000 credits`
- `actor`: `system`
- `amount`: Can be positive or negative

---

## Updated Implementation Plan

### Phase 1: Database Schema ✅ COMPLETED
- [x] Add `last_applied_default_credits` column to `credit_users` table
- [x] Add migration for PostgreSQL databases
- [x] Add migration for SQLite databases

### Phase 2: Core Logic ✅ COMPLETED
- [x] Implement `apply_group_credit_adjustments()` method
- [x] Calculate credit differences per user
- [x] Apply additive adjustments to balances
- [x] Update `last_applied_default_credits` after adjustment
- [x] Log transactions with proper metadata

### Phase 3: Configuration ✅ COMPLETED
- [x] Add `AUTO_APPLY_GROUP_CREDITS` config flag
- [x] Default to enabled (`true`)
- [x] Support environment variable override

### Phase 4: API Integration ✅ COMPLETED
- [x] Add manual trigger endpoint `/api/credits/apply-group-adjustments`
- [x] Integrate into `sync_all_from_openwebui()` flow
- [x] Include adjustment results in sync response
- [x] Admin authentication on manual endpoint

### Phase 5: Testing & Verification ⏳ PENDING

**Test Scenarios**:
1. Create test user in "default" group only (0 credits)
2. Manually set user balance to 500 credits
3. Add user to "premium" group (1000 credits default)
4. Call `/api/credits/apply-group-adjustments`
5. **Expected**: User balance = 1500 (500 + 1000)
6. **Expected**: Transaction history shows +1000 adjustment
7. **Expected**: `last_applied_default_credits` = 1000
8. Test automatic sync triggers adjustment when enabled
9. Test `force_all=true` adjusts all users regardless of changes
10. Test negative adjustments (user removed from group)

---

## Dry-Run Mode Feature

### Overview

Dry-run mode allows administrators to preview credit adjustments before applying them to the database. This prevents unintended changes and provides transparency for credit operations.

### Implementation Details

**File**: `credit_admin/app/api/credits_v2.py` (line 773-850)

**New Parameter**: `dry_run` (boolean, default: `false`)

**Behavior**:
- When `dry_run=true`: Calculates all adjustments without writing to database
- Returns same response structure as normal execution
- Marks results with `dry_run: true` and `preview_only: true` flags
- No transactions are logged, no balance changes are persisted

**Use Cases**:
- Preview impact of group membership changes before applying
- Verify adjustment calculations before bulk operations
- Audit and compliance review of planned changes
- Testing with `force_all=true` without affecting user balances

### Example Usage

```bash
# Preview all pending adjustments
curl -X POST https://yourdomain.com/credits/api/credits/apply-group-adjustments \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"force_all": false, "dry_run": true}'

# Preview adjustments for all users (even if no changes)
curl -X POST https://yourdomain.com/credits/api/credits/apply-group-adjustments \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"force_all": true, "dry_run": true}'
```

---

## Default Credits Configuration

### Overview

The system supports configurable default credit amounts via environment variables, allowing flexible credit allocation strategies for groups and individual users.

### Configuration Variables

**DEFAULT_GROUP_CREDITS** (default: `1000`)
- Base credit amount assigned to users via group membership
- Applied automatically when users join groups with default allocations
- Can be overridden per-group in the admin interface

**DEFAULT_USER_CREDITS** (default: `1000`)
- Base credit amount for direct user assignments
- Used when assigning credits directly to users (not via groups)
- Provides fallback for users without group memberships

### How It Works

1. **Group-Based Allocation**: Users inherit credits from their group memberships
2. **Additive Adjustments**: When group membership changes, credits are adjusted additively
3. **Tracking System**: `last_applied_default_credits` tracks what has been applied
4. **Formula**: `new_balance = current_balance + (new_default_credits - old_default_credits)`

### Example Scenarios

**Scenario 1: New User Joins Premium Group**
- User has 0 credits, joins "premium" group (1000 credits default)
- Adjustment: +1000 credits
- New balance: 1000 credits

**Scenario 2: User Moves from Premium to Basic Group**
- User has 1000 credits (from premium), moves to "basic" group (500 credits default)
- Adjustment: 500 - 1000 = -500 credits
- New balance: 500 credits

**Scenario 3: User in Multiple Groups**
- User in "premium" (1000) + "student" (500) = 1500 total default credits
- Adjustment applies full 1500 when first joining groups

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_APPLY_GROUP_CREDITS` | `true` | Enable/disable automatic group credit adjustments during sync |
| `DEFAULT_GROUP_CREDITS` | `1000` | Default credit amount for group-based allocations |
| `DEFAULT_USER_CREDITS` | `1000` | Default credit amount for direct user assignments |

---

## Migration Notes

### Existing Databases

The schema migration is automatic:
- PostgreSQL: Uses `ADD COLUMN IF NOT EXISTS`
- SQLite: Uses `ADD COLUMN` (runs silently if column exists)

**No manual migration required** - the column will be added on next service startup.

### Data Initialization

For existing users without `last_applied_default_credits` values:
- New column defaults to `0.0`
- First adjustment will apply full `total_default_credits` as adjustment
- This is intentional - ensures all users get their entitled credits

---

## Future Enhancements

Potential improvements for future iterations:
1. **Batch processing**: For large user bases, process adjustments in batches
2. **Dry-run mode**: Preview adjustments before applying
3. **Selective adjustments**: Adjust specific users or groups only
4. **Audit trail enhancement**: Store more detailed change history
5. **Scheduled adjustments**: Run at specific times rather than during sync

---

## Related Files

- [`credit_admin/app/database.py`](./credit_admin/app/database.py) - Core database logic
- [`credit_admin/app/api/credits_v2.py`](./credit_admin/app/api/credits_v2.py) - API endpoints
- [`credit_admin/app/config.py`](./credit_admin/app/config.py) - Configuration
