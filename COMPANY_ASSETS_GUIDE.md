# 📁 Company Assets Feature - User Guide

**Date:** December 16, 2025  
**Version:** 1.0  
**Status:** ✅ RESTORED & ENHANCED

---

## 🎯 Overview

The **Company Assets** feature provides a centralized repository for all company-wide documents, files, and resources that need to be accessible to all staff members. This includes forms, policies, training materials, clinical guidelines, and links to external resources like Google Docs.

---

## ✨ Features

### Asset Types

1. **File Uploads**
   - Upload PDFs, Word documents, Excel spreadsheets, PowerPoint presentations
   - Support for images (JPG, PNG, GIF, WebP)
   - ZIP archives for bundled resources
   - **Maximum file size:** 50MB per file

2. **External Links**
   - Link to Google Docs, Google Sheets, Google Slides
   - Link to external websites or resources
   - Automatically validates URLs

### Organization

- **Categories:** Organize assets into categories (Forms, Policies, Training, Resources, etc.)
- **Tags:** Add comma-separated tags for easy searching
- **Pin Important Assets:** Pin frequently accessed items to the top of the list
- **Search:** Full-text search across titles, descriptions, and tags
- **Filter by Category:** Quickly filter to specific types of content

---

## 📱 How to Use

### Accessing Company Assets

1. Log in to CaptureCare
2. Click **"Company Assets"** in the left sidebar menu (below Communications)
3. The assets library will display all available resources

### Adding a New Asset

#### **Option 1: Upload a File**

1. Click the **"+ Add Asset"** button (top right)
2. Select **"Upload File"** as the asset type
3. Fill in the details:
   - **Title** (required): Descriptive name for the asset
   - **Description** (optional): Brief explanation of what it is
   - **Category** (optional): Select from dropdown or leave blank
   - **Tags** (optional): Add comma-separated keywords
4. Click **"Choose File"** and select your document
5. Click **"Add Asset"**

**Supported File Types:**
- Documents: PDF, DOC, DOCX, TXT
- Spreadsheets: XLS, XLSX
- Presentations: PPT, PPTX
- Images: JPG, JPEG, PNG, GIF, WebP
- Archives: ZIP

#### **Option 2: Add a Link**

1. Click the **"+ Add Asset"** button
2. Select **"Add Link"** as the asset type
3. Fill in the details:
   - **Title** (required): Name of the resource
   - **Description** (optional): What the link contains
   - **Category** (optional): Select from dropdown
   - **Tags** (optional): Keywords for searching
   - **Link URL** (required): Full URL including https://
4. Click **"Add Asset"**

**Example Links:**
- Google Docs: `https://docs.google.com/document/d/...`
- Google Sheets: `https://sheets.google.com/spreadsheets/d/...`
- Websites: `https://example.com/resource`

### Managing Assets

#### **Viewing an Asset**
- **Files:** Click the **"Download"** button to download the file
- **Links:** Click the **"Open Link"** button to open in a new tab

#### **Pinning an Asset**
1. Click the **three-dot menu (⋮)** on any asset card
2. Select **"Pin"** to move it to the top of the list
3. Pinned assets show a yellow badge and appear first

#### **Editing an Asset**
1. Click the **three-dot menu (⋮)** on the asset card
2. Select **"Edit"**
3. Update the title, description, category, or tags
4. Click **"Save Changes"**

*Note: You cannot change the file or link URL after creation. To update a file, delete and re-upload it.*

#### **Deleting an Asset**
1. Click the **three-dot menu (⋮)** on the asset card
2. Select **"Delete"**
3. Confirm the deletion

⚠️ **Warning:** Deleting an asset permanently removes the file from the system. This action cannot be undone.

### Searching and Filtering

#### **Search**
- Use the search bar at the top to find assets by:
  - Title
  - Description
  - Tags
- Search is case-insensitive and searches across all fields

#### **Filter by Category**
- Use the category dropdown to show only assets from a specific category
- Select **"All Categories"** to show everything

#### **Clear Filters**
- Click the **"Clear"** button to reset all filters and show all assets

---

## 🎨 Asset Categories

Suggested categories for organizing your assets:

- **Forms** - Patient forms, consent forms, intake documents
- **Policies** - Company policies, procedures, protocols
- **Training** - Training materials, onboarding documents, guides
- **Resources** - Reference materials, clinical guidelines, charts
- **Guidelines** - Clinical practice guidelines, treatment protocols
- **Templates** - Document templates, letterheads, report templates
- **Marketing** - Brochures, flyers, promotional materials
- **Other** - Miscellaneous items

*You can create your own categories by typing a custom name when adding an asset.*

---

## 💡 Use Cases

### Clinical Operations
- Store patient consent forms for quick access
- Link to clinical practice guidelines
- Share treatment protocols and procedures
- Maintain medication interaction charts

### Administrative
- Company policies and procedures
- Employee handbook
- Emergency contact lists
- Insurance information and forms

### Training & Development
- Onboarding checklists
- Training manuals and videos
- Equipment operation guides
- Software tutorials

### Marketing & Communications
- Practice brochures and flyers
- Logo and brand assets
- Patient education materials
- Social media templates

---

## 🔒 Security & Permissions

- **Access:** All logged-in staff members can view and download assets
- **Upload:** All logged-in staff members can upload new assets
- **Edit/Delete:** Any staff member can edit or delete any asset
- **Audit Trail:** System tracks who uploaded each asset and when

### File Storage

- **Local Development:** Files stored in `capturecare/static/uploads/company_assets/`
- **Production:** Files stored on the application server filesystem
- **Naming:** Files renamed with timestamp to prevent conflicts
- **Security:** Filenames sanitized, file types validated

---

## 🔧 Database Structure

### `company_assets` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `title` | VARCHAR(200) | Asset title |
| `description` | TEXT | Optional description |
| `asset_type` | VARCHAR(50) | 'file' or 'link' |
| `category` | VARCHAR(100) | Organization category |
| `file_path` | VARCHAR(500) | Path to uploaded file |
| `file_name` | VARCHAR(255) | Original filename |
| `file_type` | VARCHAR(50) | MIME type |
| `file_size` | INTEGER | File size in bytes |
| `link_url` | TEXT | External link URL |
| `tags` | VARCHAR(500) | Comma-separated tags |
| `is_pinned` | BOOLEAN | Pin to top |
| `created_by_id` | INTEGER | User who created it |
| `created_at` | TIMESTAMP | Creation date |
| `updated_at` | TIMESTAMP | Last update date |

---

## 📦 Migration & Setup

### Running the Migration

To set up the company_assets table in your database:

#### **Local Development (SQLite)**
```bash
cd "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"
python3 scripts/add_company_assets.py
```

#### **Production (Cloud SQL PostgreSQL)**
```bash
# Via Cloud SQL Proxy
psql -h localhost -p 5434 -U postgres -d capturecare -f migrations/add_company_assets.sql
```

The migration:
- ✅ Creates the `company_assets` table
- ✅ Adds necessary indexes for performance
- ✅ Sets up automatic timestamp updates
- ✅ Creates the upload directory
- ✅ Safe to run multiple times (idempotent)

---

## 🐛 Troubleshooting

### "File type not allowed"
- Check that your file has one of the supported extensions
- Ensure the file isn't corrupted or empty

### "File size exceeds 50MB limit"
- Compress large files or split into multiple parts
- Consider using a link to cloud storage for very large files

### "Asset not found" when downloading
- File may have been manually deleted from filesystem
- Check server logs for file path issues
- Re-upload the file if necessary

### Upload directory doesn't exist
- Run the migration script: `python3 scripts/add_company_assets.py`
- Or manually create: `mkdir -p capturecare/static/uploads/company_assets`

---

## 🚀 Next Steps

### Recommended Initial Assets

Consider adding these common assets to get started:

1. **Patient Consent Form** (PDF)
2. **Privacy Policy** (Link to Google Doc)
3. **Staff Handbook** (PDF)
4. **Emergency Procedures** (PDF)
5. **Clinical Guidelines** (Links to external resources)
6. **Equipment Manuals** (PDFs)
7. **Contact Lists** (Excel or PDF)
8. **Training Materials** (Various formats)

### Best Practices

- ✅ Use clear, descriptive titles
- ✅ Add detailed descriptions for context
- ✅ Tag assets with relevant keywords
- ✅ Keep categories consistent
- ✅ Pin frequently accessed items
- ✅ Regularly review and update outdated assets
- ✅ Delete obsolete files to reduce clutter

---

## 📞 Support

If you encounter any issues or have questions about Company Assets:
1. Check this guide first
2. Review the troubleshooting section
3. Check server logs for error messages
4. Contact your system administrator

---

**Happy organizing! 🎉**

