# Company-Wide Availability System - Implementation Guide

## 🎯 Overview

We've implemented a **company-wide availability system** that allows you to set practice-wide closures and holidays that automatically apply to ALL practitioners, eliminating the need to set individual blockouts for each person.

---

## ✅ What's Been Implemented

### 1. Database Schema Updates ✅

Added `is_company_wide` flag to the `availability_exceptions` table:
- Company-wide blocks have `is_company_wide = TRUE`
- Company-wide blocks have `user_id = NULL` (not tied to any specific practitioner)
- Individual practitioner blocks have `is_company_wide = FALSE`
- Database migration runs automatically on startup

### 2. Availability Logic Updates ✅

Updated all availability checking endpoints to respect company-wide blocks:
- **Batch availability endpoint** (`/api/calendar/availability/batch`)
- **Single practitioner endpoint** (`/api/calendar/availability/<practitioner_id>`)
- **Calendar events endpoint** (for displaying appointments)

**Priority Order:**
1. ✋ **Company-wide blocks** are checked FIRST
2. 👤 **Individual practitioner blocks** are checked SECOND
3. ✅ **Availability patterns** are applied LAST

**Result:** If the practice is closed company-wide, NO practitioners show as available, regardless of their individual patterns.

### 3. Admin Interface ✅

New **Company Settings** page accessible from the sidebar (Admin only):
- Add single-day or multi-day closures
- Bulk add holidays (e.g., Christmas week closure)
- View all company-wide blocks in chronological order
- Delete blocks when needed
- Beautiful, intuitive UI with calendar date picker

### 4. Database Connection Pool Improvements ✅

Also fixed the random 500 errors by:
- Increased pool size: 5 → 10 connections
- Added burst capacity: +20 overflow connections (30 total max)
- Faster connection recycling: 1 hour → 30 minutes
- Added TCP keepalives to prevent stale connections

---

## 📘 How To Use

### For Admins: Setting Company-Wide Closures

1. **Navigate to Company Settings**
   - Click **"Company Settings"** in the sidebar (Admin only)
   
2. **Add a Single Holiday**
   - Click **"+ Add Holiday/Closure"**
   - Select the date (e.g., Dec 25, 2025)
   - Choose type: "Public Holiday", "Company Vacation", or "Practice Closed"
   - Enter reason: e.g., "Christmas Day"
   - Leave "End Date" blank for single day
   - Click **"Add Block"**

3. **Add Multi-Day Closure** (e.g., Christmas/New Year Week)
   - Click **"+ Add Holiday/Closure"**
   - **Start Date:** Dec 24, 2025
   - **End Date:** Jan 5, 2026
   - Type: "Company Vacation"
   - Reason: "Christmas-New Year Closure"
   - Click **"Add Block"**
   - ✅ This will create 13 individual blocks (one for each day)

4. **Delete a Block**
   - Click the **trash icon** (🗑️) next to any block
   - Confirm deletion

### For Practitioners: Personal Time Off

Individual practitioners can still add their own personal time off:
1. Go to **"My Availability"**
2. Click **"+ Block Date"** under "Holidays & Blocked Dates"
3. Add personal vacation days, appointments, etc.

**Note:** Personal blocks only apply to that practitioner. Company-wide blocks apply to everyone.

---

## 🔧 Technical Details

### Database Schema

```sql
-- availability_exceptions table
CREATE TABLE availability_exceptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NULL REFERENCES users(id),  -- NULL for company-wide
    exception_date DATE NOT NULL,
    exception_type VARCHAR(20) DEFAULT 'blocked',
    is_company_wide BOOLEAN DEFAULT FALSE NOT NULL,  -- NEW COLUMN
    is_all_day BOOLEAN DEFAULT TRUE,
    start_time TIME NULL,
    end_time TIME NULL,
    reason VARCHAR(200),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX idx_availability_exceptions_company_wide 
ON availability_exceptions(is_company_wide, exception_date);
```

### Availability Checking Logic

```python
# 1. Check company-wide blocks FIRST
company_wide_blocks = AvailabilityException.query.filter_by(
    is_company_wide=True,
    exception_date=target_date
).all()

company_wide_full_block = any(
    ex.is_all_day and ex.exception_type in ['blocked', 'holiday', 'vacation']
    for ex in company_wide_blocks
)

# 2. Check individual practitioner blocks
exceptions = AvailabilityException.query.filter_by(
    user_id=practitioner_id,
    exception_date=target_date
).all()

# 3. Combine: blocked if EITHER company-wide OR individual
full_day_block = company_wide_full_block or any(
    ex.is_all_day and ex.exception_type in ['blocked', 'holiday', 'vacation']
    for ex in exceptions
)
```

---

## 🚀 Next Steps

### Immediate Action Required

**You need to add company-wide blocks for your Christmas/New Year closure:**

1. Log in as admin
2. Go to **Company Settings**
3. Click **"+ Add Holiday/Closure"**
4. Add the closure dates:
   - Start: Dec 24, 2025
   - End: Jan 5, 2026
   - Type: Company Vacation
   - Reason: "Christmas-New Year Closure"

This will immediately make Dec 26 (and all other dates in that range) unavailable for ALL practitioners.

### Testing

1. **Test the Company Settings page**
   - Add a test holiday (e.g., a future date)
   - Verify it appears in the list
   - Delete it to clean up

2. **Test appointment booking**
   - Go to a patient page
   - Click "Book Appointment"
   - Select David Brown (or any practitioner)
   - Verify blocked dates don't show in available dates
   - Try to book on Dec 26 - should show no availability

3. **Test the calendar view**
   - Go to Calendar
   - Navigate to December 2025
   - Company-wide blocks should be visible for all practitioners

---

## 📊 Benefits

### Before (Old System)
- ❌ Had to set blockouts for EACH practitioner individually
- ❌ Easy to miss someone when adding holidays
- ❌ Tedious and error-prone
- ❌ David Brown showing available on Dec 26

### After (New System)
- ✅ Set holidays ONCE for entire practice
- ✅ Applies to ALL practitioners automatically
- ✅ Easy to manage from central location
- ✅ Individual practitioners can still add personal time off
- ✅ Clear separation between company-wide and personal blocks

---

## 🐛 Troubleshooting

### Issue: Practitioner still showing available on blocked date

**Possible causes:**
1. Block wasn't added as company-wide (check `is_company_wide` flag)
2. Cache issue - refresh the page
3. Block date doesn't match the date you're checking

**Solution:**
1. Go to Company Settings
2. Verify the block exists and shows correct date
3. Delete and re-add if needed
4. Hard refresh browser (Ctrl+Shift+R or Cmd+Shift+R)

### Issue: Can't access Company Settings page

**Possible causes:**
- User is not an admin

**Solution:**
- Ensure your user has `is_admin = TRUE` in the database
- Or ask an existing admin to grant you admin privileges

---

## 📞 Support

If you encounter any issues:
1. Check the browser console for JavaScript errors
2. Check server logs: `gcloud logging read ...`
3. Verify database migration ran successfully
4. Check that `is_company_wide` column exists in `availability_exceptions` table

---

## 🎉 Success!

Your appointment system now has:
- ✅ Company-wide holiday management
- ✅ Fixed database connection pool (no more random 500 errors)
- ✅ Improved availability checking logic
- ✅ Beautiful admin interface
- ✅ Automatic application of practice closures to all staff

**Next:** Add your Christmas/New Year closure dates and test booking on Dec 26 - it should now correctly show as unavailable! 🎄

