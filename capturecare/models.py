from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class Patient(db.Model):
    __tablename__ = 'patients'
    
    id = db.Column(db.Integer, primary_key=True)
    clinician_id = db.Column(db.Integer, nullable=True)
    withings_user_id = db.Column(db.String(100), unique=True, nullable=True)
    cliniko_patient_id = db.Column(db.String(100), unique=True, nullable=True)
    
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    
    phone = db.Column(db.String(20), nullable=True)
    mobile = db.Column(db.String(20), nullable=True)
    sex = db.Column(db.String(20), nullable=True)
    
    address_line1 = db.Column(db.String(200), nullable=True)
    address_line2 = db.Column(db.String(200), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    postcode = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    
    emergency_contact_name = db.Column(db.String(200), nullable=True)
    emergency_contact_phone = db.Column(db.String(20), nullable=True)
    emergency_contact_email = db.Column(db.String(120), nullable=True)
    emergency_contact_relationship = db.Column(db.String(100), nullable=True)
    emergency_contact_consent = db.Column(db.Boolean, default=False)
    
    gp_name = db.Column(db.String(200), nullable=True)
    gp_address = db.Column(db.String(200), nullable=True)
    gp_phone = db.Column(db.String(20), nullable=True)
    has_gp = db.Column(db.Boolean, default=False)
    
    current_medications = db.Column(db.Text, nullable=True)
    owns_smart_device = db.Column(db.Boolean, default=False)
    health_focus_areas = db.Column(db.Text, nullable=True)
    
    occupation = db.Column(db.String(100), nullable=True)
    medicare_number = db.Column(db.String(50), nullable=True)
    dva_number = db.Column(db.String(50), nullable=True)
    
    notes = db.Column(db.Text, nullable=True)
    medical_alerts = db.Column(db.Text, nullable=True)
    terms_consent = db.Column(db.Boolean, default=False)
    
    withings_access_token = db.Column(db.Text, nullable=True)
    withings_refresh_token = db.Column(db.Text, nullable=True)
    withings_token_expiry = db.Column(db.DateTime, nullable=True)
    
    stripe_customer_id = db.Column(db.String(100), unique=True, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    health_data = db.relationship('HealthData', backref='patient', lazy=True, cascade='all, delete-orphan')
    devices = db.relationship('Device', backref='patient', lazy=True, cascade='all, delete-orphan')
    target_ranges = db.relationship('TargetRange', backref='patient', lazy=True, cascade='all, delete-orphan')
    appointments = db.relationship('Appointment', backref='patient', lazy=True, cascade='all, delete-orphan')
    patient_notes = db.relationship('PatientNote', backref='patient', lazy=True, cascade='all, delete-orphan')
    invoices = db.relationship('Invoice', backref='patient', lazy=True, cascade='all, delete-orphan')
    correspondence = db.relationship('PatientCorrespondence', backref='patient', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Patient {self.first_name} {self.last_name}>'

class HealthData(db.Model):
    __tablename__ = 'health_data'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    
    measurement_type = db.Column(db.String(50), nullable=False)
    value = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False)
    source = db.Column(db.String(50), nullable=False)
    device_source = db.Column(db.String(20), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<HealthData {self.measurement_type}: {self.value}>'

class Device(db.Model):
    __tablename__ = 'devices'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    
    device_type = db.Column(db.String(50), nullable=False)
    device_id = db.Column(db.String(100), unique=True, nullable=False)
    device_model = db.Column(db.String(100), nullable=True)
    
    last_sync = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='active')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Device {self.device_type}: {self.device_model}>'

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    
    # Profile fields
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    role = db.Column(db.String(50), default='practitioner')  # admin, practitioner, nurse, receptionist
    
    # Calendar settings
    calendar_color = db.Column(db.String(7), default='#00698f')  # Hex color for calendar display
    google_calendar_id = db.Column(db.String(200), nullable=True)  # For multi-calendar sync
    
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    
    # Password setup for new users
    password_setup_token = db.Column(db.String(100), nullable=True)
    password_setup_token_expires = db.Column(db.DateTime, nullable=True)
    password_set = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    appointments = db.relationship('Appointment', backref='assigned_practitioner', lazy=True, foreign_keys='Appointment.practitioner_id')
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    @property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username
    
    def set_password(self, password):
        """Hash and set the password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)
    
    def get_id(self):
        """Override UserMixin get_id to return string"""
        return str(self.id)

class TargetRange(db.Model):
    __tablename__ = 'target_ranges'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    
    measurement_type = db.Column(db.String(50), nullable=False)
    target_mode = db.Column(db.String(10), default='range')
    
    min_value = db.Column(db.Float, nullable=True)
    max_value = db.Column(db.Float, nullable=True)
    target_value = db.Column(db.Float, nullable=True)
    unit = db.Column(db.String(20), nullable=True)
    
    source = db.Column(db.String(10), default='manual')
    auto_apply_ai = db.Column(db.Boolean, default=False)
    
    suggested_min = db.Column(db.Float, nullable=True)
    suggested_max = db.Column(db.Float, nullable=True)
    suggested_value = db.Column(db.Float, nullable=True)
    last_ai_generated_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('patient_id', 'measurement_type', name='_patient_metric_uc'),)
    
    def __repr__(self):
        if self.target_mode == 'single':
            return f'<TargetRange {self.measurement_type}: {self.target_value}>'
        return f'<TargetRange {self.measurement_type}: {self.min_value}-{self.max_value}>'

class Appointment(db.Model):
    __tablename__ = 'appointments'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    practitioner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Assigned practitioner
    
    title = db.Column(db.String(200), nullable=False)
    appointment_type = db.Column(db.String(100), nullable=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=60)
    
    location = db.Column(db.String(200), nullable=True)
    practitioner = db.Column(db.String(100), nullable=True)  # Deprecated: use practitioner_id instead
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), default='scheduled')
    
    google_calendar_event_id = db.Column(db.String(200), nullable=True)
    outlook_calendar_event_id = db.Column(db.String(200), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    patient_notes = db.relationship('PatientNote', backref='appointment', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Appointment {self.title} at {self.start_time}>'
    
    def to_calendar_event(self):
        """Convert appointment to FullCalendar event format"""
        return {
            'id': self.id,
            'title': f"{self.patient.first_name} {self.patient.last_name} - {self.title}",
            'start': self.start_time.isoformat(),
            'end': self.end_time.isoformat(),
            'backgroundColor': self.assigned_practitioner.calendar_color if self.assigned_practitioner else '#00698f',
            'borderColor': self.assigned_practitioner.calendar_color if self.assigned_practitioner else '#00698f',
            'extendedProps': {
                'patient_id': self.patient_id,
                'patient_name': f"{self.patient.first_name} {self.patient.last_name}",
                'practitioner_id': self.practitioner_id,
                'practitioner_name': self.assigned_practitioner.full_name if self.assigned_practitioner else 'Unassigned',
                'appointment_type': self.appointment_type,
                'location': self.location,
                'notes': self.notes,
                'status': self.status
            }
        }

class PatientNote(db.Model):
    __tablename__ = 'patient_notes'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=True)
    
    subject = db.Column(db.String(200), nullable=True)  # Subject/title for the note
    note_text = db.Column(db.Text, nullable=False)
    note_type = db.Column(db.String(50), default='manual')  # manual, ai_report, soap, clinical, call_summary, heygen_video
    author = db.Column(db.String(100), nullable=True)  # Who created the note
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<PatientNote {self.id} for Patient {self.patient_id}>'

class WebhookLog(db.Model):
    __tablename__ = 'webhook_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    success = db.Column(db.Boolean, nullable=False)
    patient_id = db.Column(db.Integer, nullable=True)
    patient_name = db.Column(db.String(200), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    request_data = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<WebhookLog {self.id} - {"Success" if self.success else "Failed"}>'

class UserAvailability(db.Model):
    __tablename__ = 'user_availability'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Recurring weekly schedule
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = db.Column(db.Time, nullable=False)  # e.g., 09:00
    end_time = db.Column(db.Time, nullable=False)  # e.g., 17:00
    
    # Optional: specific date overrides (for vacations, etc.)
    specific_date = db.Column(db.Date, nullable=True)
    is_available = db.Column(db.Boolean, default=True)  # False for blocked time/vacation
    
    notes = db.Column(db.String(200), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<UserAvailability User {self.user_id} - Day {self.day_of_week}>'

class AvailabilityPattern(db.Model):
    __tablename__ = 'availability_patterns'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    title = db.Column(db.String(100), nullable=False)  # e.g., "Morning Shift", "Lunch Break"
    
    # Frequency options: daily, weekly, weekdays, custom
    frequency = db.Column(db.String(20), nullable=False, default='weekly')  # daily, weekly, weekdays, custom
    
    # For weekly patterns: which days (0=Mon, 6=Sun). Stored as JSON array or bitmask
    weekdays = db.Column(db.String(50), nullable=True)  # e.g., "0,1,2,3,4" for weekdays or "1" for Tuesday
    
    # Time range
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    
    # Optional validity period
    valid_from = db.Column(db.Date, nullable=True)  # Pattern starts from this date
    valid_until = db.Column(db.Date, nullable=True)  # Pattern ends on this date
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    
    # Display and notes
    color = db.Column(db.String(7), nullable=True)  # Hex color for visual identification
    notes = db.Column(db.String(500), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to User
    user = db.relationship('User', backref='availability_patterns', lazy=True)
    
    def __repr__(self):
        return f'<AvailabilityPattern {self.id}: {self.title} ({self.frequency})>'

class AvailabilityException(db.Model):
    __tablename__ = 'availability_exceptions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Specific date to block or override
    exception_date = db.Column(db.Date, nullable=False)
    
    # Type: holiday, vacation, blocked, custom_hours
    exception_type = db.Column(db.String(20), nullable=False, default='blocked')
    
    # Is this a full day block or partial?
    is_all_day = db.Column(db.Boolean, default=True)
    
    # If partial day, specify times
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    
    # Description
    reason = db.Column(db.String(200), nullable=True)  # e.g., "Christmas Holiday", "Dentist Appointment"
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to User
    user = db.relationship('User', backref='availability_exceptions', lazy=True)
    
    def __repr__(self):
        return f'<AvailabilityException {self.id}: {self.exception_date} - {self.reason}>'

class Invoice(db.Model):
    __tablename__ = 'invoices'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    
    # Invoice details
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    invoice_type = db.Column(db.String(20), nullable=False)  # one_off, recurring
    status = db.Column(db.String(20), default='draft')  # draft, sent, paid, overdue, cancelled
    
    # Amounts
    subtotal = db.Column(db.Float, default=0.0)
    tax_amount = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, nullable=False)
    amount_paid = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='AUD')
    
    # Dates
    invoice_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    paid_date = db.Column(db.Date, nullable=True)
    
    # Recurring details (if applicable)
    is_recurring = db.Column(db.Boolean, default=False)
    recurring_frequency = db.Column(db.String(20), nullable=True)  # weekly, monthly, quarterly, yearly
    recurring_start_date = db.Column(db.Date, nullable=True)
    recurring_end_date = db.Column(db.Date, nullable=True)
    next_billing_date = db.Column(db.Date, nullable=True)
    
    # Stripe integration
    stripe_invoice_id = db.Column(db.String(100), unique=True, nullable=True)
    stripe_payment_intent_id = db.Column(db.String(100), nullable=True)
    stripe_subscription_id = db.Column(db.String(100), nullable=True)
    stripe_hosted_invoice_url = db.Column(db.String(500), nullable=True)
    stripe_invoice_pdf = db.Column(db.String(500), nullable=True)
    
    # Additional info
    description = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    items = db.relationship('InvoiceItem', backref='invoice', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Invoice {self.invoice_number}: ${self.total_amount} ({self.status})>'

class InvoiceItem(db.Model):
    __tablename__ = 'invoice_items'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float, nullable=False)
    tax_rate = db.Column(db.Float, default=0.0)  # Tax percentage (e.g., 10 for 10% GST)
    amount = db.Column(db.Float, nullable=False)  # quantity * unit_price
    
    # Item metadata
    item_type = db.Column(db.String(50), nullable=True)  # consultation, treatment, product, etc.
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<InvoiceItem {self.description}: ${self.amount}>'

class PatientCorrespondence(db.Model):
    __tablename__ = 'patient_correspondence'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Who sent/received it
    
    # Message details
    channel = db.Column(db.String(20), nullable=False)  # 'email', 'sms', or 'voice'
    direction = db.Column(db.String(20), nullable=False)  # 'outbound' or 'inbound'
    subject = db.Column(db.String(200), nullable=True)  # For emails, null for SMS/voice
    body = db.Column(db.Text, nullable=False)  # Message content or call transcript
    
    # Contact info
    recipient_email = db.Column(db.String(120), nullable=True)  # For emails
    recipient_phone = db.Column(db.String(20), nullable=True)  # For SMS/voice
    sender_email = db.Column(db.String(120), nullable=True)  # For inbound emails
    sender_phone = db.Column(db.String(20), nullable=True)  # For inbound SMS/voice
    
    # Voice call specific fields
    call_duration = db.Column(db.Integer, nullable=True)  # Call duration in seconds
    recording_url = db.Column(db.Text, nullable=True)  # URL to call recording
    call_sid = db.Column(db.String(200), nullable=True)  # Twilio Call SID
    transcription_status = db.Column(db.String(50), nullable=True)  # pending, completed, failed
    
    # Delivery tracking
    status = db.Column(db.String(50), nullable=True)  # delivered, failed, sent, queued, etc.
    external_id = db.Column(db.String(200), nullable=True)  # Twilio SID or email message ID
    error_message = db.Column(db.Text, nullable=True)  # If delivery failed
    
    # Workflow tracking
    workflow_status = db.Column(db.String(50), default='pending')  # pending, completed, follow_up_needed, no_action_required
    
    # Metadata
    related_appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=True)
    message_metadata = db.Column(db.Text, nullable=True)  # JSON for additional data
    
    # Timestamps
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Soft delete
    is_deleted = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<Correspondence {self.channel} {self.direction} to Patient {self.patient_id}>'

class CommunicationWebhookLog(db.Model):
    __tablename__ = 'communication_webhook_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    webhook_type = db.Column(db.String(20), nullable=False)  # 'sms', 'email', or 'voice'
    direction = db.Column(db.String(20), default='inbound')  # Always inbound for webhooks
    
    # Request details
    from_phone = db.Column(db.String(20), nullable=True)  # For SMS
    to_phone = db.Column(db.String(20), nullable=True)  # For SMS
    from_email = db.Column(db.String(120), nullable=True)  # For Email
    to_email = db.Column(db.String(120), nullable=True)  # For Email
    
    message_body = db.Column(db.Text, nullable=True)
    message_subject = db.Column(db.String(200), nullable=True)  # For email
    
    # Processing results
    success = db.Column(db.Boolean, default=False)
    patient_matched = db.Column(db.Boolean, default=False)
    patient_id = db.Column(db.Integer, nullable=True)
    patient_name = db.Column(db.String(200), nullable=True)
    
    # Error tracking
    error_message = db.Column(db.Text, nullable=True)
    
    # Raw data for debugging
    raw_request_data = db.Column(db.Text, nullable=True)  # JSON dump of all request data
    
    # External IDs
    external_id = db.Column(db.String(200), nullable=True)  # Twilio SID or email message ID
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<CommunicationWebhookLog {self.webhook_type} - {"Success" if self.success else "Failed"}>'

class NotificationTemplate(db.Model):
    """Stores customizable notification templates for appointments"""
    __tablename__ = 'notification_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    template_type = db.Column(db.String(50), nullable=False)  # 'sms' or 'email'
    template_name = db.Column(db.String(100), nullable=False)  # 'appointment_confirmation', 'appointment_update', etc.
    is_predefined = db.Column(db.Boolean, default=False)  # True for system templates, False for custom
    is_active = db.Column(db.Boolean, default=True)
    
    # Template content
    subject = db.Column(db.String(200), nullable=True)  # For email only
    message = db.Column(db.Text, nullable=False)  # SMS message or email body
    
    # Metadata
    description = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<NotificationTemplate {self.template_type}/{self.template_name}>'
