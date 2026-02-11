"""
Standalone script to send daily T+1 report to Telegram
Designed to be run by Windows Task Scheduler at 2pm daily
"""
import sys
import os

# Add the project directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from data_loader import load_facebook_ads_data
from daily_report import generate_facebook_ads_section
from config import DAILY_REPORT_ENABLED
from telegram_reporter import TelegramReporter

def send_report():
    """Load data from INDIVIDUAL KPI sheet, generate report, and send to Telegram"""
    if not DAILY_REPORT_ENABLED:
        print("[DISABLED] Daily report sending is disabled in config.py")
        return False

    print("Loading Facebook Ads data from INDIVIDUAL KPI sheet...")
    fb_ads_df = load_facebook_ads_data()

    if fb_ads_df is None or fb_ads_df.empty:
        print("[ERROR] No Facebook Ads data loaded!")
        return False

    # T+1 reporting: yesterday's data
    yesterday = (datetime.now() - timedelta(days=1)).date()

    print(f"Generating T+1 report for {yesterday}...")
    report = f"📊 <b>BINGO365 T+1 Report</b> - {yesterday.strftime('%b %d, %Y')}\n"
    report += f"<i>vs Last 7 Days Average</i>\n\n"
    report += generate_facebook_ads_section(fb_ads_df, yesterday)
    report += '\n@xxxadsron @Adsbasty'

    print("Sending to Telegram...")
    try:
        reporter = TelegramReporter()
        result = reporter.send_message(report)
        print('[OK] Report sent to KPI Ads group!')
        return True
    except Exception as e:
        print(f"[ERROR] {e}")
        return False

if __name__ == "__main__":
    send_report()
