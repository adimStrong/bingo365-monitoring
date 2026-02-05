"""
Real-Time Report Scheduler for BINGO365 Monitoring
Schedules multiple report sends throughout the day using APScheduler
"""
import os
import sys
import signal
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from config import REALTIME_REPORT_ENABLED, REALTIME_SEND_TIMES
from realtime_reporter import send_realtime_report, send_text_only_report

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), 'realtime_report.log'))
    ]
)
logger = logging.getLogger(__name__)


def job_listener(event):
    """Listen for job execution events"""
    if event.exception:
        logger.error(f"Job {event.job_id} failed with exception: {event.exception}")
    else:
        logger.info(f"Job {event.job_id} executed successfully")


def send_scheduled_report():
    """
    Wrapper function for scheduled report sending.
    Includes error handling and logging.
    """
    try:
        now = datetime.now()
        logger.info(f"Starting scheduled report at {now.strftime('%Y-%m-%d %H:%M:%S')}")

        # Determine if this is a screenshot-capable time (during working hours)
        # Screenshots only during 6 AM - 11 PM, text-only for 3 AM
        hour = now.hour
        if hour == 3:
            # 3 AM overnight check - text only (faster, no need for visual)
            logger.info("Overnight report - sending text only")
            success = send_text_only_report()
        else:
            # Regular report with screenshot
            success = send_realtime_report(send_screenshot=True, send_text=True)

        if success:
            logger.info("Scheduled report completed successfully")
        else:
            logger.error("Scheduled report completed with errors")

        return success

    except Exception as e:
        logger.error(f"Scheduled report failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_immediate_report():
    """Send a report immediately (for testing)"""
    logger.info("Sending immediate report...")
    return send_realtime_report(send_screenshot=True, send_text=True)


def setup_scheduler():
    """
    Set up the APScheduler with all configured send times.

    Returns:
        BlockingScheduler: Configured scheduler instance
    """
    scheduler = BlockingScheduler(
        timezone='Asia/Manila',  # Philippine timezone
        job_defaults={
            'coalesce': True,  # Combine missed executions
            'max_instances': 1,  # Only one instance at a time
            'misfire_grace_time': 300,  # 5 minute grace period for missed jobs
        }
    )

    # Add job listener
    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    # Schedule all send times from config
    for time_config in REALTIME_SEND_TIMES:
        hour = time_config['hour']
        minute = time_config['minute']
        label = time_config['label']

        job_id = f'report_{hour:02d}_{minute:02d}'

        scheduler.add_job(
            send_scheduled_report,
            CronTrigger(hour=hour, minute=minute),
            id=job_id,
            name=f'KPI Report at {label}',
            replace_existing=True
        )

        logger.info(f"Scheduled job: {label} ({job_id})")

    return scheduler


def print_schedule():
    """Print the current schedule"""
    print("\n" + "=" * 50)
    print("Real-Time Report Schedule (Asia/Manila)")
    print("=" * 50)

    for time_config in REALTIME_SEND_TIMES:
        hour = time_config['hour']
        minute = time_config['minute']
        label = time_config['label']
        print(f"  {label:12} - Daily at {hour:02d}:{minute:02d}")

    print("=" * 50 + "\n")


def graceful_shutdown(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info("Received shutdown signal, stopping scheduler...")
    sys.exit(0)


def main():
    """Main entry point for the scheduler"""
    import argparse

    parser = argparse.ArgumentParser(description='Real-Time KPI Report Scheduler')
    parser.add_argument('--run-now', action='store_true', help='Send report immediately and exit')
    parser.add_argument('--text-only', action='store_true', help='Send text-only report (with --run-now)')
    parser.add_argument('--show-schedule', action='store_true', help='Show schedule and exit')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon (start scheduler)')

    args = parser.parse_args()

    # Check if real-time reporting is enabled
    if not REALTIME_REPORT_ENABLED:
        logger.warning("Real-time reporting is disabled in config. Set REALTIME_REPORT_ENABLED = True to enable.")
        if not args.run_now:
            return

    # Handle command-line options
    if args.show_schedule:
        print_schedule()
        return

    if args.run_now:
        if args.text_only:
            send_text_only_report()
        else:
            send_immediate_report()
        return

    # Start the scheduler (daemon mode or default)
    print_schedule()
    logger.info("Starting Real-Time Report Scheduler...")

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    scheduler = setup_scheduler()

    try:
        logger.info("Scheduler started. Press Ctrl+C to exit.")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
