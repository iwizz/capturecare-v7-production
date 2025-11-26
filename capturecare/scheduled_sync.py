import schedule
import time
from datetime import datetime
from sync_health_data import HealthDataSynchronizer
from config import Config
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_daily_sync():
    logger.info("Starting daily health data sync...")
    config = Config()
    synchronizer = HealthDataSynchronizer(config)
    
    results = synchronizer.sync_all_patients(days_back=1)
    
    for result in results:
        logger.info(f"Synced {result['patient_name']}: {result['result']}")
    
    logger.info("Daily sync completed")

def run_scheduler():
    schedule.every().day.at("06:00").do(run_daily_sync)
    
    logger.info("Scheduler started. Daily sync scheduled for 6:00 AM")
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    run_scheduler()
