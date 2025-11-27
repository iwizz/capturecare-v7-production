import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)

class EmailSender:
    def __init__(self, smtp_server, smtp_port, username, password, from_email):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        # Store password, handling spaces and special characters (fix non-breaking spaces)
        # CRITICAL: Do NOT strip() - preserve spaces in Gmail app passwords
        if password:
            # Replace non-breaking spaces (\xa0) with regular spaces, but keep all other spaces
            self.password = password.replace('\xa0', ' ').replace('\u00a0', ' ')
        else:
            self.password = ''
        self.from_email = from_email
        
        # Log configuration status (without exposing password)
        if all([self.smtp_server, self.username, self.password]):
            logger.info(f"✅ EmailSender initialized - Server: {self.smtp_server}:{self.smtp_port}, From: {self.from_email}")
        else:
            logger.warning(f"⚠️ EmailSender partially configured - Server: {self.smtp_server}, Username: {self.username}, Password: {'Set' if self.password else 'Missing'}")
    
    def send_health_report(self, to_email, patient_name, report_content, subject=None, attachments=None):
        """
        Send health report email with optional file attachments.
        
        Args:
            to_email: Recipient email address
            patient_name: Patient's name
            report_content: HTML content of the report
            subject: Optional email subject
            attachments: List of dict with keys 'filename' and 'content' (bytes)
        """
        if not all([self.smtp_server, self.username, self.password]):
            logger.warning("Email configuration incomplete, skipping send")
            return False
        
        try:
            if subject is None:
                subject = f"Health Report for {patient_name} - {datetime.now().strftime('%B %d, %Y')}"
            
            msg = MIMEMultipart('mixed')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email
            
            # Create alternative part for text and HTML
            msg_alternative = MIMEMultipart('alternative')
            
            html_body = self._create_html_email(patient_name, report_content)
            text_body = f"Health Report for {patient_name}\n\n{report_content}"
            
            part1 = MIMEText(text_body, 'plain')
            part2 = MIMEText(html_body, 'html')
            
            msg_alternative.attach(part1)
            msg_alternative.attach(part2)
            msg.attach(msg_alternative)
            
            # Add attachments if provided
            if attachments:
                for attachment in attachments:
                    filename = attachment.get('filename', 'attachment')
                    content = attachment.get('content')
                    
                    if content:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(content)
                        encoders.encode_base64(part)
                        part.add_header('Content-Disposition', f'attachment; filename= {filename}')
                        msg.attach(part)
                        logger.info(f"Attached file: {filename}")
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                logger.info(f"📨 Connected to SMTP server {self.smtp_server}:{self.smtp_port}")
                server.starttls()
                logger.info(f"🔐 TLS started")
                
                # CRITICAL: Do NOT strip() - preserve spaces in Gmail app passwords
                # Only replace non-breaking spaces with regular spaces
                smtp_password = self.password.replace('\xa0', ' ') if self.password else ''
                
                logger.info(f"🔑 Logging in as {self.username}...")
                server.login(self.username, smtp_password)
                logger.info(f"✅ Login successful")
                
                logger.info(f"📤 Sending message to {to_email}...")
                server.send_message(msg)
                logger.info(f"✅ Message sent successfully")
            
            logger.info(f"✅ Health report sent to {to_email} with {len(attachments) if attachments else 0} attachments")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"❌ SMTP Authentication failed: {e}")
            logger.error(f"   Check your SMTP username and password (app password for Gmail)")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"❌ SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Error sending email: {e}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")
            return False
    
    def send_notification(self, to_email, subject, message):
        if not all([self.smtp_server, self.username, self.password]):
            logger.warning("Email configuration incomplete, skipping send")
            return False
        
        try:
            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email
            
            body = MIMEText(message, 'plain')
            msg.attach(body)
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                logger.info(f"📨 Connected to SMTP server {self.smtp_server}:{self.smtp_port}")
                server.starttls()
                logger.info(f"🔐 TLS started")
                
                # CRITICAL: Do NOT strip() - preserve spaces in Gmail app passwords
                # Only replace non-breaking spaces with regular spaces
                smtp_password = self.password.replace('\xa0', ' ') if self.password else ''
                
                logger.info(f"🔑 Logging in as {self.username}...")
                server.login(self.username, smtp_password)
                logger.info(f"✅ Login successful")
                
                logger.info(f"📤 Sending notification to {to_email}...")
                server.send_message(msg)
                logger.info(f"✅ Message sent successfully")
            
            logger.info(f"✅ Notification sent to {to_email}")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"❌ SMTP Authentication failed: {e}")
            logger.error(f"   Check your SMTP username and password (app password for Gmail)")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"❌ SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Error sending notification: {e}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")
            return False
    
    def _create_html_email(self, patient_name, report_content):
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', Arial, sans-serif;
                    line-height: 1.6;
                    color: #3e4044;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f4f5f7;
                }}
                .header {{
                    background: linear-gradient(135deg, #265063 0%, #00698f 100%);
                    color: white;
                    padding: 30px 20px;
                    text-align: center;
                    border-radius: 8px 8px 0 0;
                }}
                .logo {{
                    max-width: 280px;
                    margin-bottom: 15px;
                }}
                .content {{
                    background-color: #ffffff;
                    padding: 35px;
                    border-radius: 0 0 8px 8px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }}
                .report-section {{
                    background-color: #f4f5f7;
                    padding: 25px;
                    margin: 20px 0;
                    border-left: 4px solid #00698f;
                    border-radius: 4px;
                }}
                .footer {{
                    text-align: center;
                    color: #96b7c8;
                    font-size: 12px;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 2px solid #e3dfd6;
                }}
                .tagline {{
                    color: #96b7c8;
                    font-size: 14px;
                    margin-top: 5px;
                }}
                h1 {{
                    margin: 0;
                    font-size: 26px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>CaptureCare<sup style="font-size: 12px;">®</sup></h1>
                <p class="tagline">Humanising Digital Health</p>
                <p style="margin-top: 20px; font-size: 18px;">Health Report for {patient_name}</p>
            </div>
            <div class="content">
                <p>Dear {patient_name},</p>
                <p>Here is your latest health analysis based on your recent health data:</p>
                <div class="report-section">
                    {report_content.replace(chr(10), '<br>')}
                </div>
                <p>This report is automatically generated based on your latest health metrics. 
                Please consult with your healthcare provider for medical advice.</p>
            </div>
            <div class="footer">
                <p><strong>CaptureCare<sup>®</sup></strong> - Humanising Digital Health</p>
                <p>Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                <p style="margin-top: 10px; font-size: 11px;">This is an automated health report. Please consult your healthcare provider for medical advice.</p>
            </div>
        </body>
        </html>
        """
        return html
