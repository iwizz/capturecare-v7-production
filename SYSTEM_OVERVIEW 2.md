# CaptureCare V7 - System Overview

## What We've Built

CaptureCare V7 is a **comprehensive healthcare management platform** that helps medical practices manage patients, track health data, schedule appointments, and provide personalized health insights using artificial intelligence.

### Core Features

**Patient Management**
- Complete patient registration and profile management
- Store patient contact information, medical history, and notes
- Track all patient communications (emails, SMS, phone calls, video consultations)
- View patient billing and invoices

**Health Data Integration**
- Connect to Withings health devices (scales, blood pressure monitors, activity trackers)
- Automatically sync health data from devices (weight, heart rate, blood pressure, sleep, activity)
- Display health data in interactive charts and graphs
- Set target ranges for health metrics based on patient age and conditions

**Appointment Scheduling**
- Interactive calendar system with month, week, and day views
- Schedule appointments with multiple practitioners
- Block time slots for capacity management
- Drag-and-drop appointment rescheduling
- Automatic SMS notifications when appointments are changed

**AI-Powered Health Analysis**
- Generate personalized health reports using OpenAI GPT-4
- Analyze health trends and provide recommendations
- Create patient-friendly reports, clinical SOAP notes, and video scripts
- Generate AI avatar videos explaining health reports (HeyGen integration)

**Practice Management Integration**
- Connect to Cliniko practice management system
- Automatically match patients between systems
- Sync treatment notes and patient data
- Google Calendar integration for appointment synchronization

**Communication & Notifications**
- Send SMS messages via Twilio
- Send email notifications via SMTP
- Make voice calls with transcription
- Video consultations using Twilio Video
- Track all patient communications in one place

**Billing & Payments**
- Create invoices for patients
- Process payments via Stripe
- Set up recurring subscriptions
- Track invoice status and payment history

**Data Storage & Reporting**
- Store all data in secure database
- Export data to Google Sheets for reporting
- Generate comprehensive health reports
- Track webhook activity and system logs

---

## Systems & Technologies Used

### Backend Framework
- **Flask** - Python web framework that powers the entire application
- **SQLAlchemy** - Database toolkit for managing patient and health data
- **Python 3.11+** - Programming language

### Database
- **SQLite** - Used for local development (lightweight, file-based database)
- **PostgreSQL** - Used in production (enterprise-grade database with better security and performance)

### External Services & APIs

**Health Data**
- **Withings API** - Connects to Withings health devices (scales, monitors, trackers)
- Uses OAuth2 authentication for secure device authorization

**Practice Management**
- **Cliniko API** - Integrates with Cliniko practice management system
- Automatically matches and syncs patient data

**Artificial Intelligence**
- **OpenAI GPT-4** - Powers AI health analysis and report generation
- **xAI (Grok)** - Alternative AI model for health insights
- **HeyGen API** - Creates AI avatar videos for patient health reports

**Communication Services**
- **Twilio** - Handles SMS messages, voice calls, and video consultations
- **SMTP (Gmail/Email Server)** - Sends email notifications and health reports

**Payment Processing**
- **Stripe** - Processes patient payments, invoices, and subscriptions

**Cloud Services**
- **Google Cloud Platform**
  - Google Cloud Secret Manager - Securely stores API keys and passwords
  - Google Cloud Storage - Stores configuration files
- **Google Sheets API** - Exports health data to spreadsheets
- **Google Calendar API** - Syncs appointments with Google Calendar

### Frontend Technologies
- **HTML5/CSS3/JavaScript** - Standard web technologies
- **Chart.js** - Creates interactive health data visualizations
- **Tailwind CSS** - Modern styling framework
- **Font Awesome** - Icons and visual elements

### Development & Deployment
- **Flask-Migrate** - Database migration tool
- **Gunicorn** - Production web server
- **Docker** - Containerization for deployment
- **Google Cloud Build** - Automated deployment pipeline

---

## Security Features

### User Authentication & Authorization

**Password Security**
- All passwords are **hashed** using Werkzeug's secure password hashing
- Passwords are never stored in plain text
- Uses industry-standard bcrypt-style hashing algorithm
- Password setup tokens expire after a set time period

**Session Management**
- Secure session cookies with HttpOnly flag (prevents JavaScript access)
- Session cookies expire after 24 hours of inactivity
- Sessions are stored securely on the server
- Automatic logout when session expires

**User Roles & Access Control**
- Role-based access control (Admin, Practitioner, Nurse, Receptionist)
- Different users have different permissions
- Admin users can manage all system settings
- Practitioners can manage their own patients and appointments
- Login required for all protected pages

### Data Protection

**API Key Management**
- API keys stored in **Google Cloud Secret Manager** (production)
- Environment variables for local development
- Never hardcoded in source code
- Separate configuration files for sensitive data

**Database Security**
- SQL injection protection via SQLAlchemy ORM
- Database connections use secure protocols
- Production database (PostgreSQL) has access controls
- Database backups recommended for production

**OAuth2 Authentication**
- Secure OAuth2 flow for Withings device authorization
- Access tokens stored securely
- Token refresh mechanism for expired tokens
- Tokens never exposed to frontend JavaScript

### Communication Security

**HTTPS/SSL**
- Production deployments use HTTPS encryption
- All data transmitted over encrypted connections
- Secure cookie settings for production

**Email Security**
- SMTP authentication required
- Secure email transmission (TLS/SSL)
- Email credentials stored securely

**SMS & Voice Security**
- Twilio API uses secure authentication tokens
- Phone numbers validated before sending messages
- Call recordings and transcriptions stored securely

### Application Security

**Input Validation**
- All user inputs are validated and sanitized
- Prevents malicious code injection
- Database queries use parameterized statements

**Error Handling**
- Secure error messages (don't expose system details)
- Logging system tracks errors without exposing sensitive data
- Production mode disables debug information

**CORS (Cross-Origin Resource Sharing)**
- Configured to allow only trusted domains
- Prevents unauthorized access from other websites

**Webhook Security**
- Webhook endpoints validate incoming requests
- Duplicate detection prevents replay attacks
- All webhook activity is logged for auditing

### Compliance & Best Practices

**Data Privacy**
- Patient data is isolated by user permissions
- Only authorized users can access patient information
- Audit logging tracks who accessed what data

**Production Security Settings**
- Debug mode disabled in production
- Secure session cookies enabled
- Secret keys are randomly generated
- Environment-specific configuration

**Secret Management**
- Production uses Google Cloud Secret Manager
- Local development uses `.env` files (not committed to git)
- API keys rotated regularly
- Separate credentials for each environment

---

## Security Recommendations for Production

1. **Use HTTPS** - Always use SSL/TLS certificates in production
2. **Database Encryption** - Enable database-level encryption for sensitive data
3. **Regular Updates** - Keep all dependencies updated for security patches
4. **Backup Strategy** - Regular automated backups of patient data
5. **Access Logging** - Monitor and log all access to patient data
6. **Two-Factor Authentication** - Consider adding 2FA for admin accounts
7. **Rate Limiting** - Implement rate limiting on API endpoints
8. **Security Audits** - Regular security audits and penetration testing
9. **HIPAA Compliance** - Ensure all practices meet healthcare data regulations
10. **Incident Response Plan** - Have a plan for security incidents

---

## Summary

CaptureCare V7 is a **secure, comprehensive healthcare management system** that:

✅ **Manages** patients, appointments, and health data  
✅ **Integrates** with multiple health devices and practice management systems  
✅ **Uses** modern web technologies and cloud services  
✅ **Protects** data with password hashing, secure sessions, and encrypted communications  
✅ **Complies** with security best practices for healthcare applications  

The system is designed to be both powerful for healthcare providers and secure for patient data protection.

---

*Last Updated: January 2025*

