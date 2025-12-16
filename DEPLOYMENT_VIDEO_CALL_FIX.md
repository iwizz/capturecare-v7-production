# Video Call 400 Error - Deployment Complete ✅

## Deployment Summary
**Date**: December 16, 2025  
**Revision**: capturecare-00219-2sh  
**Status**: ✅ DEPLOYED TO PRODUCTION

## What Was Fixed
Fixed the recurring "400 Bad Request" error when creating video rooms by adding proper HTTP headers to the frontend request.

### Root Cause
```javascript
// ❌ BEFORE (causing 400 error)
const tokenResponse = await fetch(`/api/patients/${patientId}/video-token`, {
    method: 'POST'  // No Content-Type header, no body
});
```

### Solution
```javascript
// ✅ AFTER (working correctly)
const tokenResponse = await fetch(`/api/patients/${patientId}/video-token`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({})  // Empty JSON object
});
```

## Deployment Details

### Git Commits
```
commit 0e46b70
Author: Tim Hook
Date: December 16, 2025

fix: Add proper Content-Type header to video token request

- Fixed 400 Bad Request error when creating video rooms
- Added Content-Type: application/json header
- Send empty JSON body {} for POST request
- Ensures Flask can properly parse the request
```

### Cloud Run Deployment
- **Service**: capturecare
- **Region**: australia-southeast2
- **Revision**: capturecare-00219-2sh
- **Traffic**: 100% to new revision
- **URL**: https://capturecare-310697189983.australia-southeast2.run.app

### Git Repositories Updated
- ✅ Origin: https://github.com/iwizz/Capturecare_Replit.git
- ✅ Production: https://github.com/iwizz/capturecare-v7-production.git

## Testing Instructions

### CRITICAL: Clear Browser Cache First!
Before testing, you **MUST** do a hard refresh to clear cached JavaScript:
- **Mac**: Cmd + Shift + R
- **Windows/Linux**: Ctrl + Shift + R
- **Alternative**: Open in Incognito/Private window

### Test Flow (Production)
1. **Navigate to**: https://capturecare-310697189983.australia-southeast2.run.app
2. **Login** with your credentials
3. **Go to**: Communications page
4. **Click**: "Video Call" button
5. **Select**: A patient with a phone number
6. **Enter**: Your practitioner phone number
7. **Click**: "Step 1: Send SMS Invite to Patient"
   - ✅ Should see: "✅ SMS invite sent to patient!"
   - ❌ Should NOT see: "400 Bad Request" error
8. **Click**: "Step 2: Setup Your Camera"
   - Allow camera/microphone permissions
   - ✅ Should see: Your camera preview
9. **Click**: "Step 3: Join Video Call"
   - ✅ Should see: "Connected to video room"
   - ✅ Should see: Your video in the active call view
10. **Patient side**: Open SMS link on mobile device
    - ✅ Should see: Mobile-responsive video interface
    - ✅ Should see: Practitioner video (large)
    - ✅ Should see: Patient self-view (small PiP)
11. **Verify**: Both parties can see and hear each other

### Expected Behavior
- ✅ No 400 errors when creating video room
- ✅ SMS sent successfully with video link
- ✅ Practitioner can setup camera and see preview
- ✅ Practitioner can join video room
- ✅ Patient receives SMS with correct room link
- ✅ Patient joins the SAME room as practitioner
- ✅ Both parties can communicate via video/audio

### Browser Console Logs (Expected)
```
✅ Video room created: patient_123_abc12345
✅ Token saved (valid for 1 hour)
🔄 Joining room with saved token: patient_123_abc12345
✅ Connected to video room: patient_123_abc12345
```

## Files Modified
1. **capturecare/templates/communications.html**
   - Line ~1158: Added headers and body to fetch request
   
2. **VIDEO_CALL_400_ERROR_FIX.md** (NEW)
   - Detailed documentation of the fix
   
3. **DEPLOYMENT_VIDEO_CALL_FIX.md** (NEW - this file)
   - Deployment summary and testing instructions

## Related Documentation
- `VIDEO_CALL_400_ERROR_FIX.md` - Technical details of the fix
- `VIDEO_CALL_FLOW_IMPROVEMENT.md` - 3-step video call flow
- `VIDEO_CALL_FIXES.md` - Camera preview and start button
- `PATIENT_VIDEO_ROOM_MOBILE_FIX.md` - Mobile responsive patient view
- `COMMUNICATIONS_ENHANCEMENT.md` - Original communication features

## Rollback Plan (If Needed)
If issues arise, rollback to previous revision:
```bash
gcloud run services update-traffic capturecare \
  --region=australia-southeast2 \
  --to-revisions=capturecare-00218-xxx=100
```

## Success Criteria
- [x] Code committed to git
- [x] Deployed to Cloud Run
- [x] Pushed to origin and production repos
- [ ] **PENDING**: User testing in production
- [ ] **PENDING**: Confirm no 400 errors
- [ ] **PENDING**: Confirm video calls work end-to-end

## Next Steps
1. **Test in production** (with hard refresh!)
2. **Verify** the 400 error is resolved
3. **Test** complete video call flow with a real patient
4. **Monitor** logs for any issues
5. **Report** success or any remaining issues

---

**Deployment completed at**: 2025-12-16 18:15 AEDT  
**Status**: ✅ Ready for testing  
**Action required**: User to test in production with hard refresh

