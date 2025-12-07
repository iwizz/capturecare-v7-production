# Quick Testing Guide - Appointment System Fixes

## Prerequisites

1. **Install Dependencies**
   ```bash
   cd "Capture Care Replit Version"
   pip install -r requirements.txt
   ```

2. **Run Database Migration**
   ```bash
   # Option 1: Using SQL file
   psql -U your_user -d your_database -f migrations/add_created_by_id.sql
   
   # Option 2: Using Flask-Migrate
   cd capturecare
   flask db migrate -m "Add created_by_id to appointments"
   flask db upgrade
   ```

3. **Start the Server**
   ```bash
   cd capturecare
   python web_dashboard.py
   ```
   
   Server will start at http://localhost:5000

## Testing Checklist

### ✅ Test 1: Create New Appointment

1. Navigate to http://localhost:5000/calendar
2. Click "New Appointment" button
3. Fill in the form:
   - Select a patient
   - Select a practitioner
   - Choose a date
   - Select an available time slot
   - Set duration (e.g., 60 minutes)
   - Add location (e.g., "Clinic Room 1")
   - Add notes
4. Click "Save"
5. **Expected Result**: 
   - Appointment appears on calendar
   - Success notification shows
   - All fields are saved correctly
   - Duration is calculated automatically

### ✅ Test 2: View Appointment Details

1. Click on an appointment in the calendar
2. **Expected Result**:
   - Modal/drawer shows all appointment details
   - Patient name, practitioner, time, duration, location, notes all display correctly
   - Created by user is tracked (if visible in UI)

### ✅ Test 3: Edit Appointment

1. Click on an existing appointment
2. Click "Edit" button
3. Modify any field (e.g., change time or duration)
4. Click "Save"
5. **Expected Result**:
   - Changes are saved
   - Calendar updates immediately
   - Google Calendar syncs (if configured)

### ✅ Test 4: Delete Appointment

1. Click on an appointment
2. Click "Delete" button
3. Confirm deletion
4. **Expected Result**:
   - Appointment removed from calendar
   - Success notification
   - Google Calendar event deleted (if synced)

### ✅ Test 5: Check Practitioner Availability

1. Navigate to availability management
2. Set availability patterns for a practitioner:
   - Daily hours (e.g., 9:00 AM - 5:00 PM)
   - Specific weekdays
3. **Expected Result**:
   - Availability blocks show on calendar as background
   - Only available time slots appear in appointment booking

### ✅ Test 6: Block Time Slots

1. Navigate to calendar
2. Enable "Block Mode"
3. Click on a time slot to block it
4. **Expected Result**:
   - Time slot is marked as unavailable
   - Blocked times don't appear as available when booking

### ✅ Test 7: Practitioner Filtering

1. On calendar page, use practitioner filter badges
2. Toggle different practitioners on/off
3. **Expected Result**:
   - Calendar updates to show only selected practitioners
   - Appointments are color-coded by practitioner

### ✅ Test 8: Google Calendar Sync (If Configured)

1. Create a new appointment
2. Check Google Calendar
3. **Expected Result**:
   - Event appears in Google Calendar
   - Event details match appointment
4. Edit the appointment
5. **Expected Result**:
   - Google Calendar event updates
6. Delete the appointment
7. **Expected Result**:
   - Google Calendar event is removed

## Common Issues and Solutions

### Issue: "No module named 'flask_cors'"
**Solution**: Install dependencies
```bash
pip install -r requirements.txt
```

### Issue: "column created_by_id does not exist"
**Solution**: Run database migration
```bash
psql -U your_user -d your_database -f migrations/add_created_by_id.sql
```

### Issue: Appointments not appearing
**Solution**: 
1. Check browser console for errors
2. Verify API endpoint is responding: http://localhost:5000/api/calendar/events
3. Check practitioner filter is not hiding appointments

### Issue: Google Calendar not syncing
**Solution**:
1. Verify Google Calendar API credentials are configured
2. Check `client_secrets.json` exists
3. Review application logs for sync errors

### Issue: Time slots not showing as available
**Solution**:
1. Verify practitioner has availability patterns set
2. Check for availability exceptions that might block times
3. Ensure date range is correct

## Browser Console Testing

Open browser console (F12) and run these commands to test API directly:

### Test 1: Create Appointment via API
```javascript
fetch('/api/calendar/appointments', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    patient_id: 1,
    practitioner_id: 1,
    title: 'Test Appointment',
    date: '2025-12-10',
    time: '14:00',
    duration_minutes: 60,
    appointment_type: 'Consultation',
    location: 'Clinic Room 1',
    notes: 'Test notes'
  })
})
.then(r => r.json())
.then(d => console.log('Created:', d))
.catch(e => console.error('Error:', e));
```

### Test 2: Get Calendar Events
```javascript
fetch('/api/calendar/events?start=2025-12-01&end=2025-12-31')
  .then(r => r.json())
  .then(d => console.log('Events:', d))
  .catch(e => console.error('Error:', e));
```

### Test 3: Check Availability
```javascript
fetch('/api/calendar/availability/1?date=2025-12-10&duration=60')
  .then(r => r.json())
  .then(d => console.log('Available slots:', d))
  .catch(e => console.error('Error:', e));
```

## Performance Testing

### Load Test: Multiple Appointments
1. Create 50+ appointments across different practitioners
2. Navigate through calendar views (month, week, day)
3. **Expected**: Smooth performance, no lag

### Stress Test: Rapid Creation
1. Quickly create 10 appointments in succession
2. **Expected**: All appointments save correctly, no duplicates

## Verification Checklist

After all tests:

- [ ] All appointments created successfully
- [ ] All fields (patient, practitioner, time, duration, location, notes) save correctly
- [ ] Calendar displays appointments properly
- [ ] Practitioner filtering works
- [ ] Availability management works
- [ ] Time slot blocking works
- [ ] Google Calendar sync works (if configured)
- [ ] Editing appointments works
- [ ] Deleting appointments works
- [ ] No errors in browser console
- [ ] No errors in server logs
- [ ] Database migrations applied successfully

## Next Steps After Testing

1. **If all tests pass**: System is ready for production use
2. **If issues found**: Document errors and check logs
3. **For production**: 
   - Backup database before deployment
   - Test in staging environment first
   - Monitor logs after deployment
   - Have rollback plan ready

## Support

If you encounter issues:
1. Check `APPOINTMENT_FIXES_SUMMARY.md` for detailed fix information
2. Review application logs in `capturecare/logs/`
3. Check browser console for JavaScript errors
4. Verify database migration was successful

