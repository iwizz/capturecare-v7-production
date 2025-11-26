# Capture Care - Digital Health Management System

A comprehensive healthcare practice management system with AI-powered health reporting, patient data integration, and communication tools.

## 🚀 Features

### Patient Management
- Complete patient records with health data tracking
- Integration with Withings health devices
- Health metrics visualization with Chart.js
- Target range monitoring and alerts
- Patient notes with subject lines and previews

### Calendar & Appointments
- Month, Week, and Day calendar views
- Practitioner availability management
- Appointment scheduling with drag-and-drop
- SMS notifications for appointment changes
- Blocked time slots for capacity management

### AI Health Reporting
- **Grok 3** (xAI) or **GPT-4** (OpenAI) powered health analysis
- Patient-friendly health reports
- Clinical SOAP notes
- AI avatar video scripts for HeyGen
- Automated health insights and recommendations

### Communication
- **Twilio Integration:**
  - SMS notifications
  - Voice calls with recording
  - Video consultations (uses same credentials as SMS)
  - Call summaries via Voice Insights API
- Email notifications via SMTP
- Two-way SMS messaging

### Integrations
- **Withings API:** Health device data sync (weight, blood pressure, heart rate, sleep, activity)
- **Cliniko API:** Practice management integration
- **Stripe API:** Billing and invoicing
- **Google Sheets API:** Data export
- **Google Calendar API:** Appointment sync
- **HeyGen API:** AI avatar video generation

### Security
- Secure credential management
- Environment variable configuration
- Webhook signature validation
- Session management
- Password hashing

## 📋 Requirements

- Python 3.11+
- PostgreSQL (production) or SQLite (development)
- Twilio account (for SMS/Voice/Video)
- OpenAI or xAI API key (for AI features)
- Withings API credentials (optional)
- Cliniko API key (optional)
- Stripe API key (optional)

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone https://github.com/YOUR_USERNAME/capture-care-system.git
cd capture-care-system
```

### 2. Set Up Virtual Environment
```bash
./setup_venv.sh
```

### 3. Configure Environment Variables
Copy `capturecare/capturecare.env.example` to `capturecare/capturecare.env` and fill in your credentials:
- `TWILIO_ACCOUNT_SID` - Twilio Account SID
- `TWILIO_AUTH_TOKEN` - Twilio Auth Token
- `TWILIO_PHONE_NUMBER` - Twilio phone number
- `OPENAI_API_KEY` or `XAI_API_KEY` - AI API key
- `WITHINGS_CLIENT_ID` and `WITHINGS_CLIENT_SECRET` - Withings credentials
- `SMTP_SERVER`, `SMTP_USERNAME`, `SMTP_PASSWORD` - Email settings
- And more...

### 4. Initialize Database
```bash
cd scripts
python3 init_db.py
python3 create_admin.py
```

### 5. Start the Server
```bash
./start_server.sh
```

The application will be available at `http://localhost:5000`

## 📁 Project Structure

```
capture-care-system/
├── capturecare/          # Main application code
│   ├── templates/        # HTML templates
│   ├── static/           # CSS, JS, images
│   ├── models.py         # Database models
│   ├── web_dashboard.py  # Flask routes and API
│   └── ...
├── scripts/              # Utility scripts
├── migrations/           # Database migrations
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## 🔧 Configuration

All configuration is managed through:
1. Environment variables (`.env` file or system environment)
2. Settings page in the web interface (`/settings`)

Key configuration areas:
- **API Keys:** OpenAI/xAI, Twilio, Withings, Cliniko, Stripe
- **Email:** SMTP server settings
- **Database:** PostgreSQL connection string
- **Features:** Enable/disable integrations

## 📚 Documentation

- `README_SETUP.md` - Detailed setup instructions
- `SCRIPTS_README.md` - Script usage guide
- `CHANGELOG_IMPROVEMENTS.md` - Feature history

## 🔐 Security Notes

- Never commit `.env` files or `capturecare.env` to version control
- Database files (`.db`) are excluded from git
- API keys should be stored as environment variables
- Use HTTPS in production
- Regularly update dependencies

## 🚀 Deployment

### Production Checklist
- [ ] Set `DATABASE_URL` to PostgreSQL
- [ ] Configure all API keys in environment variables
- [ ] Set `SECRET_KEY` for session security
- [ ] Enable HTTPS
- [ ] Set up proper logging
- [ ] Configure webhook URLs for Twilio
- [ ] Set up database backups

## 📝 License

[Your License Here]

## 👥 Support

For issues and questions, please open an issue on GitHub.

---

**Last Updated:** $(date '+%Y-%m-%d')
**Version:** 1.0.0

