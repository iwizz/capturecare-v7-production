# 📞 Communications Page - User Guide

## Quick Start

Navigate to **Communications** from the main menu to access the centralized communication hub.

---

## 🎯 Quick Actions

At the top of the Communications page, you'll see three action buttons:

### 📱 Send SMS

**Steps:**
1. Click the **"Send SMS"** button
2. Select a patient from the dropdown
3. Phone number auto-fills (or enter manually)
4. Type your message (max 160 characters)
5. Click **"Send SMS"**
6. Wait for confirmation
7. Message appears in correspondence list

**Tips:**
- Character counter shows remaining characters
- SMS is logged automatically to patient record
- Failed messages show error details

---

### 📞 Make Call

**Steps:**
1. Click the **"Make Call"** button
2. Select a patient from the dropdown
3. Phone number auto-fills (or enter manually)
4. Click **"Start Call"**
5. Call connects via Twilio
6. Use controls during call:
   - **Mute/Unmute** - Toggle your microphone
   - **Hold/Resume** - Put call on hold
7. Click **"End Call"** when finished
8. Call is logged to correspondence

**During Call:**
- Call duration timer shows elapsed time
- Patient name and number displayed
- Call status indicator (Connecting, Connected, etc.)

**Tips:**
- Ensure Twilio is configured with valid credentials
- Call recordings are stored automatically (if enabled)
- All calls logged with duration and timestamp

---

### 📹 Video Call

**Steps:**
1. Click the **"Video Call"** button
2. Select a patient from the dropdown
3. Click **"Start Video Call"**
4. Video interface loads with your camera preview
5. Share the join link with patient:
   - Click **"Copy"** to copy link
   - Click **"Send SMS"** to text link to patient
6. Patient joins via the link
7. Video consultation proceeds
8. Use controls during call:
   - **🎤 Microphone** - Mute/unmute audio
   - **📹 Camera** - Enable/disable video
   - **☎️ End Call** - Terminate session
9. Call ends and is logged automatically

**Video Interface:**
- **Left panel:** Patient's video (remote)
- **Right panel:** Your video (local)
- **Bottom:** Controls and call duration
- **Below video:** Patient join link with sharing options

**Tips:**
- Ensure camera and microphone permissions are granted
- Patient needs no account - just clicks the link
- Video quality adjusts automatically to bandwidth
- All video sessions logged with duration
- Join link expires after 2 hours

---

## 📊 Viewing Communications

### Filter Options

**Channel Filter:**
- All Channels
- 📱 SMS Only
- 📧 Email Only
- 📞 Voice Calls
- 📹 Video Calls

**Direction Filter:**
- All Directions
- ⬇️ Inbound (received)
- ⬆️ Outbound (sent)

**Patient Search:**
- Type patient name or email to filter

**Workflow Status:**
- ⏳ Pending
- ✅ Completed
- 🔔 Follow-up Needed
- ✔️ No Action Required

### Communication Cards

Each communication shows:
- **Channel badge** (color-coded)
- **Direction badge** (inbound/outbound)
- **Patient name** (clickable to patient record)
- **Message preview** (first 100 characters)
- **Timestamp** (AEDT timezone)
- **Status** (delivered, failed, sent)
- **Workflow status dropdown** (update status inline)

**Color Codes:**
- 🟢 Green = SMS
- 🔵 Blue = Email
- 🟣 Purple = Voice Call
- 🩷 Pink = Video Call

---

## 🔔 Notifications & Status

### SMS Status
- **Queued** - SMS sent to Twilio
- **Sent** - SMS dispatched
- **Delivered** - SMS received by patient
- **Failed** - SMS delivery failed (see error message)

### Call Status
- **Connecting** - Initiating call
- **Ringing** - Phone is ringing
- **Answered** - Call connected
- **Completed** - Call ended
- **Failed** - Call failed (see error message)

### Video Call Status
- **Connected** - Video session active
- **Waiting** - Waiting for patient to join
- **Completed** - Session ended

---

## 🎨 Best Practices

### SMS Messages
- Keep messages concise (160 chars)
- Include appointment details clearly
- Use professional tone
- Include practice name/contact info

### Phone Calls
- Verify patient phone number before calling
- Use mute when needed (background noise)
- Take notes during call (use patient detail page)
- End call properly to ensure logging

### Video Calls
- Test camera/microphone before patient joins
- Ensure good lighting for video quality
- Use professional background
- Send join link via SMS for easy access
- Confirm patient received link before starting

---

## 🔧 Troubleshooting

### SMS Not Sending
- ✅ Check Twilio credentials in Settings
- ✅ Verify patient has valid phone number
- ✅ Check phone number format (+61 for Australia)
- ✅ Review error message for details

### Call Not Connecting
- ✅ Verify Twilio Voice is configured
- ✅ Check patient phone number is correct
- ✅ Ensure Twilio account has credit
- ✅ Check for error messages

### Video Not Working
- ✅ Grant camera/microphone permissions
- ✅ Check Twilio Video credentials
- ✅ Ensure patient has stable internet
- ✅ Try refreshing the page
- ✅ Check browser compatibility (Chrome, Firefox, Safari)

### Patient Can't Join Video
- ✅ Verify join link was sent correctly
- ✅ Check link hasn't expired (2 hour limit)
- ✅ Ensure patient has camera/microphone
- ✅ Ask patient to grant browser permissions
- ✅ Try different browser

---

## 📱 Mobile Usage

All communication features work on mobile devices:
- Touch-friendly buttons and controls
- Responsive modal designs
- Mobile camera/microphone support
- Copy/paste join links easily

---

## 🔐 Privacy & Security

- All communications encrypted in transit
- Call recordings stored securely via Twilio
- Patient data access controlled by permissions
- Video tokens expire automatically
- All communications logged for audit trail

---

## 💡 Quick Tips

1. **Batch Communications:** Use filters to find patients needing follow-up
2. **Video Links:** Send link before starting call so patient is ready
3. **Status Updates:** Update workflow status to track follow-ups
4. **Patient Records:** Click patient name to view full record
5. **Keyboard Shortcuts:** Press ESC to close modals
6. **Background Click:** Click outside modal to close (if no active call)

---

## 📞 Support

For technical issues:
- Check Settings page for Twilio configuration
- Review error messages in correspondence list
- Contact system administrator
- Check Twilio dashboard for account status

---

## 🎉 Enjoy!

The Communications page provides a complete, centralized hub for all patient communications. Use it to stay connected with your patients efficiently and professionally.

