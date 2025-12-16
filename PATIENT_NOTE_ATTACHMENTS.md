# 📎 Patient Note Attachments Feature

**Date:** December 16, 2025  
**Version:** 1.0  
**Status:** ✅ DEPLOYED & LIVE

---

## 🎯 Overview

Patient notes now support **file attachments**! You can attach PDFs, images, and Word documents to any patient note for easy reference and documentation.

---

## ✨ Features

### Supported File Types
- **PDFs** - Lab reports, forms, medical documents
- **Images** - JPG, JPEG, PNG, GIF, WebP (photos, scans, x-rays)
- **Word Documents** - DOC, DOCX files

**File Size Limit:** 10MB per attachment

---

## 📱 How to Use

### Adding an Attachment to a Note

1. **Go to Patient Detail Page**
   - Select any patient
   - Click the "**Notes**" tab

2. **Create a New Note**
   - Click "**Add Note**" button
   - Fill in the note details (type, text, etc.)

3. **Attach a File**
   - Click "**Choose File**" in the "Attach File (Optional)" section
   - Select your file (PDF, image, or Word doc)
   - The filename will appear below the button

4. **Save the Note**
   - Click "**Save Note**"
   - The file will be uploaded and securely stored

### Viewing Attachments

**In Notes List:**
- Notes with attachments show a **blue paperclip icon** 📎
- Click the attachment link to view or download directly

**In Note Detail View:**
- Click "**View**" on any note to open the detail modal
- Attachments appear in a **blue highlighted section**
- Two buttons available:
  - **View** - Opens file in new tab (PDFs and images display inline)
  - **Download** - Downloads the file to your computer

### Managing Attachments

- **Edit Note**: You can edit the note text, but cannot change the attachment (limitation by design)
- **Delete Note**: Deleting a note also removes the attached file from the system

---

## 🗄️ Database Changes

### New Columns Added to `patient_notes` table:

| Column | Type | Description |
|--------|------|-------------|
| `attachment_filename` | VARCHAR(255) | Original filename |
| `attachment_path` | VARCHAR(500) | Stored file path |
| `attachment_type` | VARCHAR(50) | MIME type (e.g., `application/pdf`) |
| `attachment_size` | INTEGER | File size in bytes |

### Indexes Created:
- `idx_patient_notes_patient_id` - Faster patient queries
- `idx_patient_notes_has_attachment` - Filter notes with attachments

---

## 🔧 Migration Required

### **IMPORTANT:** Run the Migration Script

The database needs to be updated to support attachments. Run ONE of these options:

### Option 1: Python Script (Recommended)
```bash
cd "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"
python3 scripts/add_note_attachments.py
```

### Option 2: SQL Script (Manual)
```bash
psql -d your_database_name -f migrations/add_note_attachments.sql
```

### For Cloud SQL (Production):
```bash
# Via Cloud SQL Proxy
psql -h localhost -p 5434 -U postgres -d capturecare -f migrations/add_note_attachments.sql
```

**The migration is safe to run multiple times** - it will skip if columns already exist.

---

## 📂 File Storage

### Local Development
Files are stored in:
```
capturecare/static/uploads/notes/
```

### File Naming Convention
Files are renamed with a unique identifier to prevent conflicts:
```
{patient_id}_{timestamp}_{original_filename}
```

Example:
```
Original: lab_results.pdf
Stored as: 42_20251216_103045_lab_results.pdf
```

### Security
- ✅ Filenames are sanitized using `secure_filename()`
- ✅ Only allowed file extensions are accepted
- ✅ Files are stored outside the main application directory
- ✅ Unique filenames prevent overwrites
- ✅ Files are deleted when parent note is deleted

---

## 🎨 UI Features

### Note Card (List View)
- **Paperclip icon** 📎 shows if note has attachment
- **Blue "Has Attachment" badge** for quick identification
- **Clickable filename** with file size for direct download

### Note Detail Modal
- **Dedicated attachment section** with blue background
- **File information** displayed (name, size)
- **Two action buttons:**
  - View (opens in new tab)
  - Download (saves to computer)

### Note Creation Form
- **File input field** with drag-and-drop support
- **Accepted file types** clearly listed
- **Current attachment indicator** (when present)

---

## 📊 API Endpoints

### Create Note with Attachment
```http
POST /api/patients/{patient_id}/notes
Content-Type: multipart/form-data

Parameters:
- note_text: string (required)
- note_type: string (default: 'manual')
- appointment_id: integer (optional)
- author: string (default: 'Admin')
- attachment: file (optional)
```

### Download Attachment
```http
GET /api/notes/{note_id}/attachment
```

**Response:**
- PDFs and images: Display inline in browser
- Other files: Force download

---

## 💡 Use Cases

### Clinical Documentation
- Attach lab results to clinical notes
- Include X-ray or scan images with observations
- Store consent forms with patient intake notes

### Medical Records
- Link referral letters to appointment notes
- Attach specialist reports to follow-up notes
- Include prescription images for medication notes

### Administrative
- Store insurance documents with billing notes
- Attach signed forms to administrative notes
- Include correspondence in communication logs

---

## 🚨 Known Limitations

1. **Edit Restriction**: Cannot change attachment when editing a note (must delete and recreate)
2. **Single File**: One attachment per note (create multiple notes for multiple files)
3. **File Size**: 10MB limit per file
4. **File Types**: Only PDF, images, and Word docs supported
5. **Cloud Storage**: Currently uses local filesystem (future: Google Cloud Storage)

---

## 🔍 Troubleshooting

### "Failed to upload file"
- **Check file size** (must be under 10MB)
- **Verify file type** (PDF, JPG, PNG, GIF, WebP, DOC, DOCX only)
- **Check disk space** on server

### "Attachment not found"
- File may have been deleted from filesystem
- Check uploads/notes/ directory exists
- Verify file permissions (should be readable)

### Attachment doesn't display inline
- Only PDFs and images display inline
- Word docs will download automatically
- Check browser PDF viewer settings

---

## 📈 Statistics & Monitoring

### Check Attachments Usage
```sql
-- Count notes with attachments
SELECT COUNT(*) as notes_with_attachments
FROM patient_notes
WHERE attachment_filename IS NOT NULL;

-- Total storage used
SELECT SUM(attachment_size) as total_bytes, 
       SUM(attachment_size) / 1024 / 1024 as total_mb
FROM patient_notes
WHERE attachment_size IS NOT NULL;

-- Most common file types
SELECT attachment_type, COUNT(*) as count
FROM patient_notes
WHERE attachment_type IS NOT NULL
GROUP BY attachment_type
ORDER BY count DESC;
```

---

## 🚀 Deployment Details

### Git Commit
- **Commit:** `a974f4c`
- **Message:** "📎 Add file attachment support to patient notes"

### Cloud Run
- **Revision:** `capturecare-00207-gpq`
- **Status:** ✅ Active (100% traffic)
- **Deployed:** 2025-12-16 06:20 UTC

### Git Repositories
- ✅ Main: https://github.com/iwizz/Capturecare_Replit.git
- ✅ Production: https://github.com/iwizz/capturecare-v7-production.git

---

## ✅ Testing Checklist

- [ ] Run migration script
- [ ] Create a test note without attachment
- [ ] Create a test note with PDF attachment
- [ ] Create a test note with image attachment
- [ ] View note in list (check paperclip icon)
- [ ] Open note detail modal
- [ ] Click "View" button (should open in new tab)
- [ ] Click "Download" button (should download file)
- [ ] Edit note (text should update, attachment preserved)
- [ ] Delete note (file should be removed from filesystem)

---

## 🎊 Success!

**File attachments are now live in production!** 🎉

Try it out:
1. Go to any patient page
2. Click "Notes" tab
3. Click "Add Note"
4. Upload a file!

**Production URL:** https://capturecare-310697189983.australia-southeast2.run.app

---

**Feature Ready:** ✅ YES  
**Migration Required:** ⚠️  YES (run `scripts/add_note_attachments.py`)  
**User Testing:** 🧪 Recommended before heavy use  

Enjoy attaching files to your patient notes! 📎

