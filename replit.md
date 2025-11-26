# CaptureCare V7 - Healthcare Data Integration Platform

## Overview
CaptureCare V7 is a Flask-based healthcare management system designed to integrate and unify health data from various sources. Its core purpose is to provide seamless patient monitoring, leverage AI for health insights, and integrate with practice management workflows. The platform aims to streamline healthcare operations, offer personalized health recommendations, and enhance patient engagement through advanced data analysis and automated reporting.

## User Preferences
I want to develop this project using an an iterative approach, focusing on getting core functionalities working and then refining them. I prefer clear and concise explanations for any proposed changes or new features. When suggesting code modifications, please provide examples that adhere to best practices and maintain the existing architectural patterns. Do not make changes to the `tokens/` folder or the `capturecare.env` file directly; all configuration should be managed via Replit Secrets or the in-app settings page. Please ask for confirmation before implementing significant architectural changes or adding new, large dependencies.

## System Architecture

### Core Design Principles
CaptureCare V7 is built on a modular Python Flask architecture, emphasizing secure API key management via Replit Secrets and providing a responsive, interactive user interface. The system integrates diverse external healthcare and AI services to offer a unified patient data view and intelligent insights. All timestamps, logs, and dates use Australian Eastern Standard Time (AEST/AEDT).

### UI/UX Decisions
The frontend uses HTML5 and Tailwind CSS for a modern, responsive design. Interactive health data visualizations are powered by Chart.js, featuring professional healthcare color schemes and dynamic scaling. The dashboard and patient detail pages prioritize clarity, with patient search, filtering, and quick action buttons. Target range bands are incorporated into charts. The navigation sidebar is collapsible and its state persists via localStorage, offering full (256px) and compact (80px) modes on desktop/tablet, and an overlay on mobile.

### Technical Implementations
- **User Management**: Comprehensive user authentication and management with Flask-Login, password hashing, user roles, and secure access controls. New user accounts receive a welcome email with a secure token link to set their password.
- **User Availability Management**: Google Calendar-style availability system with recurring patterns, holiday/exception blocking, and a Team Availability Calendar via FullCalendar.js. Automatically displays Australian public holidays and highlights unavailable time slots.
- **Patient Management**: Full CRUD for patient profiles, including Cliniko-compatible fields, detailed health metrics, and an edit/view toggle.
- **Patient Notes System**: Full CRUD notes system with a timeline UI, appointment linking, various note types, author tracking, rich text formatting (Quill.js), and file attachments.
- **Appointment Scheduling**: Full appointment booking system with Google Calendar integration, multi-practitioner support, color-coded appointments, drag-and-drop rescheduling via FullCalendar.js. Features a Calendly-style interface with a two-column layout, clickable time slot buttons, duration-first selection, "Any Practitioner" option, and duration-aware availability checks.
- **Automated Notifications**: SMS (Twilio) and email (SMTP) confirmations for appointments, automated health report delivery, and welcome emails for new users.
- **Patient Correspondence Tracking System**: Comprehensive communication history system with automatic logging of all patient interactions (email, SMS, voice calls, video consultations). Features a unified correspondence tab on patient detail pages, a centralized communications dashboard, two-way SMS integration with Twilio webhooks, voice call integration with Twilio Voice API for outbound calls and transcription webhooks, and inbound email webhook integration. All communications are automatically logged with metadata and status tracking.
- **Twilio Video Telehealth Integration**: Complete video consultation system with Twilio Video SDK. Features a dedicated Video Call tab on patient detail pages, real-time video/audio streaming, mute/video toggle controls, call duration tracking, SMS invite functionality to send room links to patients, automatic logging of video sessions to correspondence history, and a public-facing patient video room page. Practitioners can start video calls, send SMS invites with room URLs, and manage video sessions directly from the patient detail page.
- **Patient Billing System**: Comprehensive Stripe-based billing integration for one-off invoices and recurring subscriptions. Includes customer management, invoice creation with customizable tax rates, recurring billing setup, and invoice management with status tracking and PDF downloads.
- **AI Health Analysis**: Utilizes OpenAI GPT-4 for personalized health insights, trend analysis, and automated health scoring, generating patient-friendly, clinical (SOAP), and video script reports.
- **HeyGen AI Avatar Videos**: Integration with HeyGen API v2 for generating personalized health report videos with customizable AI avatars and multi-language voice support.
- **Data Synchronization**: Real-time and scheduled synchronization of health data from integrated devices and platforms (e.g., Withings, including intraday heart rate tracking).
- **Secure Configuration**: Sensitive API keys managed through Replit Secrets and an in-app settings page with comprehensive API credential testing functionality and a live webhook activity log for debugging.
- **Interactive Charts**: Chart.js visualizes 22 health metrics with proper Y-axis scaling, date adapters, "no data" fallbacks, and target range bands. Heart rate charts include device source filtering.
- **Webhook Integration**: Public webhook endpoint (`/api/webhook/patient`) for receiving patient data from external forms, with automatic logging, duplicate detection, and validation.
- **API Endpoints**: Comprehensive web and API routes for managing core functionalities.

## External Dependencies

- **OpenAI (GPT-4)**: For AI-powered health analysis and report generation.
- **Withings API**: For integrating and synchronizing data from Withings health devices.
- **Cliniko API**: For practice management integration and patient matching.
- **Google Sheets API**: For data consolidation and reporting.
- **Google Calendar API**: For appointment synchronization.
- **SMTP Server (e.g., Gmail)**: For sending automated email notifications and health reports.
- **xAI (Grok)**: Alternative AI model integration.
- **HeyGen API v2**: For AI video avatar generation.
- **Twilio**: For SMS notifications, voice calls, call transcription, appointment confirmations, and video consultations (Twilio Video API).
- **Twilio Video SDK**: For secure, HIPAA-compliant video consultations between practitioners and patients.
- **Stripe API**: For patient billing, invoicing, and subscription management.