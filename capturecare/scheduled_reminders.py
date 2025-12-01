"""
Scheduled Reminder Service
Runs reminder checks periodically using the schedule library
"""

import schedule
import time
import logging
from datetime import datetime
from capturecare.appointment_reminder_service import AppointmentReminderService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_reminder_check():
    """Run reminder check and send reminders as needed"""
    logger.info("Starting appointment reminder check...")
    
    try:
        # Need to import app context
        from capturecare.web_dashboard import create_app
        app = create_app()
        
        with app.app_context():
            reminder_service = AppointmentReminderService()
            stats = reminder_service.check_and_send_reminders()
            
            logger.info(f"Reminder check complete: {stats}")
            return stats
    except Exception as e:
        logger.error(f"Error in reminder check: {e}", exc_info=True)
        return None


def run_scheduler():
    """Run the reminder scheduler"""
    # Run reminder check every 15 minutes
    schedule.every(15).minutes.do(run_reminder_check)
    
    # Also run immediately on start
    logger.info("Running initial reminder check...")
    run_reminder_check()
    
    logger.info("Reminder scheduler started. Checking every 15 minutes...")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute for pending tasks


if __name__ == "__main__":
    run_scheduler()

