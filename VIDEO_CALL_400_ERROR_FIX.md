# Video Call 400 Error Fix

## Problem
When attempting to create a video room, the system was returning:
```
❌ Error creating video room: 400 Bad Request: The browser (or proxy) sent a request that this server could not understand.
```

## Root Cause
The frontend was making a POST request to `/api/patients/<id>/video-token` **without a request body or Content-Type header**:

```javascript
const tokenResponse = await fetch(`/api/patients/${patientId}/video-token`, {
    method: 'POST'  // ❌ No body, no headers
});
```

Flask was expecting a properly formatted request, and when it received a POST with no body, it returned a 400 error.

## Solution
Added proper headers and an empty JSON body to the fetch request:

```javascript
const tokenResponse = await fetch(`/api/patients/${patientId}/video-token`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({})  // ✅ Empty JSON object
});
```

## Files Modified
- `capturecare/templates/communications.html` (line ~1158)

## Testing Instructions

### Local Testing
1. **Hard refresh the browser** (Cmd+Shift+R on Mac, Ctrl+Shift+R on Windows/Linux) to clear cached JavaScript
2. Navigate to Communications page
3. Click "Video Call" button
4. Select a patient with a phone number
5. Enter practitioner phone number
6. Click "Step 1: Send SMS Invite to Patient"
7. **Verify**: Should see "✅ SMS invite sent to patient!" without any 400 errors
8. Click "Step 2: Setup Your Camera"
9. Allow camera/microphone permissions
10. **Verify**: Should see your camera preview
11. Click "Step 3: Join Video Call"
12. **Verify**: Should join the video room successfully
13. Patient should receive SMS with link
14. Patient clicks link and joins same room
15. **Verify**: Both parties can see each other

### Production Deployment
```bash
# 1. Commit changes
git add capturecare/templates/communications.html VIDEO_CALL_400_ERROR_FIX.md
git commit -m "fix: Add proper Content-Type header to video token request

- Fixed 400 Bad Request error when creating video rooms
- Added Content-Type: application/json header
- Send empty JSON body {} for POST request
- Ensures Flask can properly parse the request"

# 2. Deploy to Cloud Run
./deploy.sh

# 3. Test on production
# - Open https://capturecare-310697189983.australia-southeast2.run.app
# - Hard refresh (Cmd+Shift+R)
# - Test video call flow end-to-end
```

## Why This Worked Before
This issue appeared after we made changes to the backend's `generate_video_token` endpoint. The original implementation may have been more lenient with request parsing, but proper REST API practices require:
1. Setting `Content-Type: application/json` for JSON requests
2. Sending a valid JSON body (even if empty: `{}`)

## Prevention
Always include proper headers and body when making POST requests:
```javascript
// ✅ Good
fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data || {})
})

// ❌ Bad
fetch(url, {
    method: 'POST'
})
```

## Related Documentation
- `VIDEO_CALL_FLOW_IMPROVEMENT.md` - 3-step video call flow
- `VIDEO_CALL_FIXES.md` - Camera preview and start button fixes
- `PATIENT_VIDEO_ROOM_MOBILE_FIX.md` - Mobile responsive patient view
- `COMMUNICATIONS_ENHANCEMENT.md` - Original communication features

