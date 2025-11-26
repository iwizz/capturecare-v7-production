# CaptureCare V7 - Healthcare Data Integration Platform

A comprehensive Flask-based healthcare management system integrating Withings health devices, Cliniko practice management, Google Sheets data consolidation, and AI-powered health insights.

## Features

- **Patient Management**: Complete patient registration and profile management
- **Withings Integration**: OAuth2-based device authorization and real-time health data synchronization
- **Cliniko Integration**: Automatic patient matching and treatment note synchronization
- **Google Sheets**: Automated data consolidation and cloud storage
- **AI Health Analysis**: OpenAI GPT-4 powered personalized health insights and reports
- **Email Notifications**: Automated health report delivery via SMTP
- **Interactive Dashboard**: Real-time health data visualization with medical-grade charts
- **Scheduled Sync**: Automated daily data synchronization

## Quick Start

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   - Copy `capturecare.env` and update with your API credentials
   - Add Withings API credentials
   - Add Cliniko API key
   - Add OpenAI API key
   - Add Google Sheets service account credentials (optional)
   - Add email SMTP credentials (optional)

3. **Run the Application**:
   ```bash
   python web_dashboard.py
   ```

4. **Access Dashboard**:
   - Open http://localhost:5000 in your browser
   - Add patients, authorize Withings devices, and sync health data

## API Configuration Required

### Withings Health API
- Sign up at: https://developer.withings.com
- Create OAuth2 application
- Add credentials to `WITHINGS_CLIENT_ID` and `WITHINGS_CLIENT_SECRET`

### Cliniko API
- Get API key from your Cliniko account settings
- Add to `CLINIKO_API_KEY`

### OpenAI API
- Get API key from: https://platform.openai.com
- Add to `OPENAI_API_KEY`

### Google Sheets (Optional)
- Create service account in Google Cloud Console
- Add credentials JSON to `GOOGLE_SHEETS_CREDENTIALS`

### Email SMTP (Optional)
- Use Gmail app password or other SMTP service
- Add credentials to SMTP configuration

## Project Structure

```
capturecare/
├── web_dashboard.py          # Main Flask application
├── models.py                 # Database models
├── config.py                 # Configuration management
├── withings_auth.py          # Withings OAuth2 authentication
├── fetch_withings_data.py    # Health data fetching
├── patient_matcher.py        # Cliniko integration
├── google_sheet_writer.py    # Google Sheets integration
├── ai_health_reporter.py     # AI health analysis
├── email_sender.py           # Email notifications
├── sync_health_data.py       # Data synchronization
├── scheduled_sync.py         # Automated scheduling
├── templates/                # HTML templates
├── tokens/                   # OAuth tokens storage
└── capturecare.env           # Environment configuration
```

## Usage

### Add a Patient
1. Navigate to "Add Patient"
2. Fill in patient information
3. System will auto-match with Cliniko if configured

### Authorize Withings Device
1. Go to patient detail page
2. Click "Connect Withings"
3. Complete OAuth2 authorization
4. Device will be linked automatically

### Sync Health Data
1. On patient page, click "Sync Data"
2. Data will be fetched from Withings
3. Automatically saved to database
4. Optionally synced to Google Sheets

### Generate AI Report
1. Click "Generate Health Report"
2. AI analyzes patient's health data
3. Personalized insights and recommendations generated
4. Report can be printed or emailed

## Security Notes

### Development Environment
- OAuth tokens stored in `tokens/` directory (plaintext)
- API keys in environment file
- SQLite database in project directory

### Production Recommendations
1. **Token Storage**: Use encrypted storage or database-backed secret management
2. **API Keys**: Use secure secret manager (AWS Secrets Manager, Azure Key Vault, etc.)
3. **Database**: Switch to PostgreSQL with proper access controls
4. **File Permissions**: Restrict access to tokens/ directory
5. **HTTPS**: Always use HTTPS in production
6. **Authentication**: Implement user authentication and session management

### Cliniko Authentication
- Uses Basic Authentication with base64-encoded API key
- Format: `Basic base64(api_key:)` (note the colon after key)

## License

Copyright © 2025 CaptureCare Health System

# Local Setup Troubleshooting

If you encounter issues like a blank screen in the browser or "Address already in use" errors when starting the local server, follow these steps:

1. **Kill Stuck Processes on Port 5000**:
   - Run: `lsof -i :5000` to check.
   - Then: `kill -9 $(lsof -ti :5000)`.

2. **Recreate Virtual Environment with Python 3.11**:
   - `cd "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"`
   - `rm -rf venv`
   - `/opt/homebrew/bin/python3.11 -m venv venv`
   - `source venv/bin/activate`
   - `pip install --upgrade pip`

3. **Pin Dependencies**:
   - Ensure `requirements.txt` has:
     ```
     flask==3.0.3
     werkzeug==3.0.3
     ```
   - `pip install -r requirements.txt`

4. **Start Server**:
   - `export FLASK_APP=capturecare/web_dashboard.py ; export FLASK_ENV=development`
   - `flask run --host=0.0.0.0 --port=5000`

5. **Open in Browser**:
   - `open http://127.0.0.1:5000`

For a one-liner restart:  
```
kill -9 $(lsof -ti :5000) ; cd "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version" ; rm -rf venv ; /opt/homebrew/bin/python3.11 -m venv venv ; source venv/bin/activate ; pip install --upgrade pip ; sed -i '' 's/flask.*/flask==3.0.3/' requirements.txt ; sed -i '' 's/werkzeug.*/werkzeug==3.0.3/' requirements.txt ; pip install -r requirements.txt ; export FLASK_APP=capturecare/web_dashboard.py ; export FLASK_ENV=development ; flask run --host=0.0.0.0 --port=5000
```
