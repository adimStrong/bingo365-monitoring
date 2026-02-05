"""
Channel Data Loader for FB and Google Channel ROI Dashboard
Loads data from Google Sheets containing FB Summary and Google Summary
"""
import os
import sys
import json
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    CHANNEL_ROI_SHEET_ID, CHANNEL_ROI_SERVICE_ACCOUNT,
    CHANNEL_FB_SHEET, CHANNEL_GOOGLE_SHEET,
    CHANNEL_DATE_FORMAT, GOOGLE_REPORT_SECTIONS,
    CHANNEL_FB_COLUMNS,
    CHANNEL_GOOGLE_DAILY_ROI_COLUMNS,
    CHANNEL_GOOGLE_ROLL_BACK_COLUMNS,
    CHANNEL_GOOGLE_VIOLET_COLUMNS,
    CHANNEL_FB_HEADER_ROW, CHANNEL_FB_DATA_START_ROW,
    FACEBOOK_ADS_CREDENTIALS_FILE
)


def get_google_client():
    """
    Get authenticated Google Sheets client using service account.

    Returns:
        gspread.Client: Authenticated gspread client
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']

        # Try environment variable first (for Railway/cloud deployment)
        google_creds_json = os.getenv('GOOGLE_CREDENTIALS')
        if google_creds_json:
            try:
                creds_dict = json.loads(google_creds_json)
                creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
                print("[OK] Using GOOGLE_CREDENTIALS environment variable")
            except json.JSONDecodeError as e:
                print(f"[ERROR] Error parsing GOOGLE_CREDENTIALS JSON: {e}")
                return None
        else:
            # Fall back to credentials file (local development)
            creds_file = os.path.join(os.path.dirname(__file__), FACEBOOK_ADS_CREDENTIALS_FILE)
            if not os.path.exists(creds_file):
                print(f"[WARNING] Credentials file not found: {creds_file}")
                st.warning("No Google credentials found. Set GOOGLE_CREDENTIALS env var or add credentials.json file.")
                return None
            creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
            print("[OK] Using local credentials file")

        client = gspread.authorize(creds)
        return client

    except Exception as e:
        print(f"[ERROR] Failed to get Google client: {e}")
        import traceback
        traceback.print_exc()
        return None


def parse_date(date_str):
    """
    Parse date from various formats including MM/DD/YYYY.

    Args:
        date_str: Date string to parse

    Returns:
        datetime or None
    """
    if pd.isna(date_str) or str(date_str).strip() == '':
        return None

    date_str = str(date_str).strip()

    # Skip header rows
    if any(keyword in date_str.upper() for keyword in ['MONTH', 'DATE', 'GOOGLE', 'CHANNEL', 'REPORT']):
        return None

    # Current year for dates without year
    current_year = datetime.now().year

    formats = [
        '%m/%d/%Y',    # 9/21/2025
        '%m/%d/%y',    # 9/21/25
        '%Y-%m-%d',    # 2025-09-21
        '%d/%m/%Y',    # 21/9/2025
        '%m-%d-%Y',    # 9-21-2025
        '%B %d, %Y',   # September 21, 2025
        '%b %d, %Y',   # Sep 21, 2025
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Handle 2-digit year
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            return dt
        except:
            continue

    return None


def parse_numeric(value, default=0):
    """Parse numeric value from string, handling currency symbols and commas."""
    if pd.isna(value) or value == '' or value is None:
        return default
    try:
        # Remove currency symbols, commas, and whitespace
        cleaned = str(value).replace(',', '').replace('$', '').replace('₱', '').replace('%', '').strip()
        return float(cleaned) if cleaned else default
    except:
        return default


def is_section_header(row):
    """Check if a row is a section header (like 'GOOGLE CHANNEL REPORT (DAILY ROI)').

    Note: Headers are in column B (index 1), not column A.
    """
    if not row or len(row) < 2:
        return False

    # Check column B (index 1) where headers are located
    cell_b = str(row[1]).strip().upper() if len(row) > 1 else ''
    cell_a = str(row[0]).strip().upper()

    # Check both columns for section headers
    for cell in [cell_b, cell_a]:
        if any(section.upper() in cell for section in GOOGLE_REPORT_SECTIONS):
            return True
    return False


def get_section_name(row):
    """Extract section name from header row.

    Note: Headers are in column B (index 1), not column A.
    """
    if not row or len(row) < 2:
        return None

    # Check column B (index 1) first, then column A
    cell_b = str(row[1]).strip() if len(row) > 1 else ''
    cell_a = str(row[0]).strip()

    for cell in [cell_b, cell_a]:
        for section in GOOGLE_REPORT_SECTIONS:
            if section.upper() in cell.upper():
                return section
    return None


@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_fb_channel_data():
    """
    Load Facebook Summary daily data from Google Sheet.

    Actual sheet structure (FB Summary):
    - Row 2: Section header "FACEBOOK CHANNEL REPORT (DAILY ROI)"
    - Row 3: Column headers (DATE, COST, REGISTER, FIRST DEPOSIT, etc.)
    - Row 5+: Data rows (starting at CHANNEL_FB_DATA_START_ROW)
    - Columns start at B (index 1)

    Returns:
        DataFrame with columns: date, register, ftd, ftd_recharge,
        avg_recharge, conversion_ratio, cost, cpr, cpftd, roas, cpm
    """
    try:
        client = get_google_client()
        if client is None:
            return pd.DataFrame()

        spreadsheet = client.open_by_key(CHANNEL_ROI_SHEET_ID)
        worksheet = spreadsheet.worksheet(CHANNEL_FB_SHEET['name'])

        all_data = worksheet.get_all_values()

        # Data starts at CHANNEL_FB_DATA_START_ROW (1-based, so subtract 1 for 0-based index)
        data_start_idx = CHANNEL_FB_DATA_START_ROW - 1

        if len(all_data) <= data_start_idx:
            print(f"[WARNING] FB Summary sheet has no data (only {len(all_data)} rows, need {data_start_idx + 1})")
            return pd.DataFrame()

        # Get data rows starting from the correct position
        data_rows = all_data[data_start_idx:]

        records = []
        cols = CHANNEL_FB_COLUMNS

        for row_idx, row in enumerate(data_rows):
            # Need enough columns (at least up to the highest column index)
            max_col = max(cols.values())
            if len(row) <= max_col:
                continue

            # Parse date from the 'date' column (index 1 = column B)
            date_val = parse_date(row[cols['date']])
            if not date_val:
                continue

            # Get cost to check if this is a valid data row
            cost_val = parse_numeric(row[cols['cost']])

            records.append({
                'date': date_val,
                'register': int(parse_numeric(row[cols['register']])),
                'ftd': int(parse_numeric(row[cols['ftd']])),
                'ftd_recharge': parse_numeric(row[cols['ftd_recharge']]),
                'avg_recharge': parse_numeric(row[cols['avg_recharge']]),
                'conversion_ratio': parse_numeric(row[cols['conversion_ratio']]),
                'cost': cost_val,
                'cpr': parse_numeric(row[cols['cpr']]),
                'cpftd': parse_numeric(row[cols['cpftd']]),
                'roas': parse_numeric(row[cols['roas']]),
                'cpm': parse_numeric(row[cols['cpm']]),
                'channel': 'Facebook',
                'deposit_amount': parse_numeric(row[cols['ftd_recharge']]),  # For compatibility
            })

        if not records:
            print("[WARNING] No valid records found in FB Summary")
            return pd.DataFrame()

        df = pd.DataFrame(records)
        print(f"[OK] Loaded {len(df)} FB Summary records")
        return df

    except Exception as e:
        print(f"[ERROR] Failed to load FB channel data: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_google_channel_data():
    """
    Load Google Summary with 3 report sections from Google Sheet.

    The sheet has 3 sections in DIFFERENT COLUMNS:
    1. DAILY ROI: Columns B-L (index 1-11)
    2. ROLL BACK: Columns N-W (index 13-22)
    3. VIOLET: Columns Y-AE (index 24-30)

    Data starts at row 4 (index 3).

    Returns:
        dict: {'daily_roi': DataFrame, 'roll_back': DataFrame, 'violet': DataFrame}
    """
    try:
        client = get_google_client()
        if client is None:
            return {'daily_roi': pd.DataFrame(), 'roll_back': pd.DataFrame(), 'violet': pd.DataFrame()}

        spreadsheet = client.open_by_key(CHANNEL_ROI_SHEET_ID)
        worksheet = spreadsheet.worksheet(CHANNEL_GOOGLE_SHEET['name'])

        all_data = worksheet.get_all_values()

        # Data starts at row 4 (index 3)
        data_start_idx = 3

        if len(all_data) <= data_start_idx:
            print("[WARNING] Google Summary sheet has no data")
            return {'daily_roi': pd.DataFrame(), 'roll_back': pd.DataFrame(), 'violet': pd.DataFrame()}

        data_rows = all_data[data_start_idx:]
        result = {}

        # Parse DAILY ROI (Columns B-L)
        cols = CHANNEL_GOOGLE_DAILY_ROI_COLUMNS
        records = []
        for row in data_rows:
            if len(row) <= max(cols.values()):
                continue
            date_val = parse_date(row[cols['date']])
            if not date_val:
                continue
            records.append({
                'date': date_val,
                'register': int(parse_numeric(row[cols['register']])),
                'ftd': int(parse_numeric(row[cols['ftd']])),
                'ftd_recharge': parse_numeric(row[cols['ftd_recharge']]),
                'avg_recharge': parse_numeric(row[cols['avg_recharge']]),
                'conversion_ratio': parse_numeric(row[cols.get('conversion_ratio', 7)]) if 'conversion_ratio' in cols else 0,
                'cost': parse_numeric(row[cols['cost']]),
                'cpr': parse_numeric(row[cols['cpr']]),
                'cpftd': parse_numeric(row[cols.get('cpftd', 9)]) if 'cpftd' in cols else 0,
                'roas': parse_numeric(row[cols['roas']]),
                'cpm': parse_numeric(row[cols.get('cpm', 11)]) if 'cpm' in cols else 0,
                'channel': 'Google',
                'section': 'daily_roi',
                'deposit_amount': parse_numeric(row[cols['ftd_recharge']]),
            })
        result['daily_roi'] = pd.DataFrame(records) if records else pd.DataFrame()
        print(f"[OK] Loaded {len(records)} Google Daily ROI records")

        # Parse ROLL BACK (Columns N-W)
        cols = CHANNEL_GOOGLE_ROLL_BACK_COLUMNS
        records = []
        for row in data_rows:
            if len(row) <= max(cols.values()):
                continue
            date_val = parse_date(row[cols['date']])
            if not date_val:
                continue
            records.append({
                'date': date_val,
                'register': int(parse_numeric(row[cols['register']])),
                'ftd': int(parse_numeric(row[cols['ftd']])),
                'ftd_recharge': parse_numeric(row[cols['ftd_recharge']]),
                'avg_recharge': parse_numeric(row[cols['avg_recharge']]),
                'conversion_ratio': 0,
                'cost': parse_numeric(row[cols['cost']]),
                'cpr': parse_numeric(row[cols['cpr']]),
                'cpftd': parse_numeric(row[cols.get('cpftd', 20)]) if 'cpftd' in cols else 0,
                'roas': parse_numeric(row[cols['roas']]),
                'cpm': parse_numeric(row[cols.get('cpm', 22)]) if 'cpm' in cols else 0,
                'channel': 'Google',
                'section': 'roll_back',
                'deposit_amount': parse_numeric(row[cols['ftd_recharge']]),
            })
        result['roll_back'] = pd.DataFrame(records) if records else pd.DataFrame()
        print(f"[OK] Loaded {len(records)} Google Roll Back records")

        # Parse VIOLET (Columns Y-AE) - Different structure!
        cols = CHANNEL_GOOGLE_VIOLET_COLUMNS
        records = []
        for row in data_rows:
            if len(row) <= max(cols.values()):
                continue
            date_val = parse_date(row[cols['date']])
            if not date_val:
                continue
            records.append({
                'date': date_val,
                'register': 0,  # Violet doesn't have register
                'ftd': int(parse_numeric(row[cols['ftd']])),  # FIRST RECHARGE
                'ftd_recharge': parse_numeric(row[cols['ftd_recharge']]),  # RECHARGE AMOUNT
                'avg_recharge': parse_numeric(row[cols['avg_recharge']]),  # ARPPU
                'conversion_ratio': 0,
                'cost': parse_numeric(row[cols['cost']]),
                'cpr': parse_numeric(row[cols['cpr']]),  # COST PER RECHARGE
                'cpftd': 0,
                'roas': parse_numeric(row[cols['roas']]),
                'cpm': 0,
                'channel': 'Google',
                'section': 'violet',
                'deposit_amount': parse_numeric(row[cols['ftd_recharge']]),
            })
        result['violet'] = pd.DataFrame(records) if records else pd.DataFrame()
        print(f"[OK] Loaded {len(records)} Google Violet records")

        return result

    except Exception as e:
        print(f"[ERROR] Failed to load Google channel data: {e}")
        import traceback
        traceback.print_exc()
        return {'daily_roi': pd.DataFrame(), 'roll_back': pd.DataFrame(), 'violet': pd.DataFrame()}


def combine_all_channel_data():
    """
    Combine FB and all Google channel data into a single DataFrame.

    Returns:
        DataFrame with all channel data combined
    """
    all_data = []

    # Load FB data
    fb_df = load_fb_channel_data()
    if not fb_df.empty:
        fb_df['section'] = 'FB Summary'
        all_data.append(fb_df)

    # Load Google data
    google_data = load_google_channel_data()
    for key, df in google_data.items():
        if not df.empty:
            all_data.append(df)

    if not all_data:
        return pd.DataFrame()

    combined = pd.concat(all_data, ignore_index=True)
    return combined


def aggregate_daily(df):
    """
    Aggregate data by date (daily summary).

    Args:
        df: DataFrame with channel data

    Returns:
        DataFrame aggregated by date
    """
    if df.empty or 'date' not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df['date_only'] = pd.to_datetime(df['date']).dt.date

    agg_df = df.groupby('date_only').agg({
        'register': 'sum',
        'ftd': 'sum',
        'deposit_amount': 'sum',
        'cost': 'sum',
    }).reset_index()

    # Calculate derived metrics
    agg_df['cpr'] = agg_df.apply(lambda x: x['cost'] / x['register'] if x['register'] > 0 else 0, axis=1)
    agg_df['roas'] = agg_df.apply(lambda x: x['deposit_amount'] / x['cost'] if x['cost'] > 0 else 0, axis=1)

    agg_df = agg_df.sort_values('date_only')
    return agg_df


def aggregate_weekly(df):
    """
    Aggregate data by week.

    Args:
        df: DataFrame with channel data

    Returns:
        DataFrame aggregated by week
    """
    if df.empty or 'date' not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    df['week'] = df['date'].dt.isocalendar().week
    df['year'] = df['date'].dt.isocalendar().year
    df['week_label'] = df.apply(lambda x: f"{x['year']}-W{x['week']:02d}", axis=1)

    agg_df = df.groupby('week_label').agg({
        'register': 'sum',
        'ftd': 'sum',
        'deposit_amount': 'sum',
        'cost': 'sum',
    }).reset_index()

    # Calculate derived metrics
    agg_df['cpr'] = agg_df.apply(lambda x: x['cost'] / x['register'] if x['register'] > 0 else 0, axis=1)
    agg_df['roas'] = agg_df.apply(lambda x: x['deposit_amount'] / x['cost'] if x['cost'] > 0 else 0, axis=1)

    agg_df = agg_df.sort_values('week_label')
    return agg_df


def aggregate_monthly(df):
    """
    Aggregate data by month.

    Args:
        df: DataFrame with channel data

    Returns:
        DataFrame aggregated by month
    """
    if df.empty or 'date' not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    df['month'] = df['date'].dt.to_period('M')

    agg_df = df.groupby('month').agg({
        'register': 'sum',
        'ftd': 'sum',
        'deposit_amount': 'sum',
        'cost': 'sum',
    }).reset_index()

    # Calculate derived metrics
    agg_df['cpr'] = agg_df.apply(lambda x: x['cost'] / x['register'] if x['register'] > 0 else 0, axis=1)
    agg_df['roas'] = agg_df.apply(lambda x: x['deposit_amount'] / x['cost'] if x['cost'] > 0 else 0, axis=1)

    # Convert period to string for display
    agg_df['month_str'] = agg_df['month'].astype(str)
    agg_df = agg_df.sort_values('month')

    return agg_df


def aggregate_by_channel(df):
    """
    Aggregate data by channel (FB vs Google).

    Args:
        df: DataFrame with channel data

    Returns:
        DataFrame aggregated by channel
    """
    if df.empty or 'channel' not in df.columns:
        return pd.DataFrame()

    agg_df = df.groupby('channel').agg({
        'register': 'sum',
        'ftd': 'sum',
        'deposit_amount': 'sum',
        'cost': 'sum',
    }).reset_index()

    # Calculate derived metrics
    agg_df['cpr'] = agg_df.apply(lambda x: x['cost'] / x['register'] if x['register'] > 0 else 0, axis=1)
    agg_df['roas'] = agg_df.apply(lambda x: x['deposit_amount'] / x['cost'] if x['cost'] > 0 else 0, axis=1)

    return agg_df


def get_date_range(df):
    """Get min and max dates from dataframe."""
    if df.empty or 'date' not in df.columns:
        return None, None

    df['date'] = pd.to_datetime(df['date'])
    min_date = df['date'].min()
    max_date = df['date'].max()

    return min_date, max_date


def refresh_channel_data():
    """Clear cache to force data refresh."""
    load_fb_channel_data.clear()
    load_google_channel_data.clear()


# Test functions
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Channel Data Loader Test')
    parser.add_argument('--fb', action='store_true', help='Test FB Summary loading')
    parser.add_argument('--google', action='store_true', help='Test Google Summary loading')
    parser.add_argument('--all', action='store_true', help='Test all data loading')

    args = parser.parse_args()

    if args.fb or args.all:
        print("\n" + "=" * 50)
        print("Testing FB Summary Loading")
        print("=" * 50)
        fb_df = load_fb_channel_data()
        if not fb_df.empty:
            print(f"Loaded {len(fb_df)} records")
            print(fb_df.head())
        else:
            print("No data loaded")

    if args.google or args.all:
        print("\n" + "=" * 50)
        print("Testing Google Summary Loading")
        print("=" * 50)
        google_data = load_google_channel_data()
        for key, df in google_data.items():
            if not df.empty:
                print(f"\n{key}: {len(df)} records")
                print(df.head())
            else:
                print(f"\n{key}: No data")

    if args.all:
        print("\n" + "=" * 50)
        print("Testing Combined Data")
        print("=" * 50)
        combined = combine_all_channel_data()
        if not combined.empty:
            print(f"Total records: {len(combined)}")
            print("\nBy Channel:")
            print(aggregate_by_channel(combined))
