#!/usr/bin/env python3
"""
Credit Card Payment Reminder App
Scans emails/SMS for credit card payment deadlines and sends reminders
"""

import imaplib
import email
import re
import sqlite3
import schedule
import time
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import os

@dataclass
class PaymentInfo:
    bank_name: str
    card_last_four: str
    due_date: datetime
    minimum_amount: float
    total_amount: float
    email_source: str

class CreditCardParser:
    def __init__(self):
        self.patterns = {
            'chase': {
                'due_date': r'payment\s+due\s+(\w+\s+\d{1,2},\s+\d{4})',
                'minimum': r'minimum\s+payment\s+due\s*\$?([\d,]+\.?\d*)',
                'card_ending': r'ending\s+in\s+(\d{4})',
                'total_balance': r'new\s+balance\s*\$?([\d,]+\.?\d*)'
            },
            'discover': {
                'due_date': r'payment\s+due\s+date\s*:?\s*(\w+\s+\d{1,2},\s+\d{4})',
                'minimum': r'minimum\s+payment\s*:?\s*\$?([\d,]+\.?\d*)',
                'card_ending': r'account\s+ending\s+in\s+(\d{4})',
                'total_balance': r'new\s+balance\s*:?\s*\$?([\d,]+\.?\d*)'
            },
            'citi': {
                'due_date': r'payment\s+due\s+(\w+\s+\d{1,2},\s+\d{4})',
                'minimum': r'minimum\s+payment\s+due\s*\$?([\d,]+\.?\d*)',
                'card_ending': r'account\s+ending\s+(\d{4})',
                'total_balance': r'new\s+balance\s*\$?([\d,]+\.?\d*)'
            },
            'amex': {
                'due_date': r'payment\s+due\s+(\w+\s+\d{1,2},\s+\d{4})',
                'minimum': r'minimum\s+payment\s*\$?([\d,]+\.?\d*)',
                'card_ending': r'card\s+ending\s+in\s+(\d{4})',
                'total_balance': r'new\s+balance\s*\$?([\d,]+\.?\d*)'
            }
        }
    
    def parse_email(self, email_content: str, subject: str) -> Optional[PaymentInfo]:
        email_lower = email_content.lower()
        subject_lower = subject.lower()
        
        # Identify bank
        bank = self._identify_bank(email_lower, subject_lower)
        if not bank:
            return None
        
        patterns = self.patterns[bank]
        
        # Extract information
        due_date = self._extract_due_date(email_lower, patterns['due_date'])
        minimum_amount = self._extract_amount(email_lower, patterns['minimum'])
        card_ending = self._extract_card_ending(email_lower, patterns['card_ending'])
        total_balance = self._extract_amount(email_lower, patterns['total_balance'])
        
        if due_date and minimum_amount and card_ending:
            return PaymentInfo(
                bank_name=bank,
                card_last_four=card_ending,
                due_date=due_date,
                minimum_amount=minimum_amount,
                total_amount=total_balance or 0,
                email_source=subject
            )
        
        return None
    
    def _identify_bank(self, email_content: str, subject: str) -> Optional[str]:
        bank_indicators = {
            'chase': ['chase', 'jpmorgan'],
            'discover': ['discover'],
            'citi': ['citi', 'citibank'],
            'amex': ['american express', 'amex']
        }
        
        for bank, indicators in bank_indicators.items():
            if any(indicator in email_content or indicator in subject for indicator in indicators):
                return bank
        
        return None
    
    def _extract_due_date(self, text: str, pattern: str) -> Optional[datetime]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                date_str = match.group(1)
                return datetime.strptime(date_str, '%B %d, %Y')
            except ValueError:
                try:
                    return datetime.strptime(date_str, '%b %d, %Y')
                except ValueError:
                    return None
        return None
    
    def _extract_amount(self, text: str, pattern: str) -> Optional[float]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(',', '')
            try:
                return float(amount_str)
            except ValueError:
                return None
        return None
    
    def _extract_card_ending(self, text: str, pattern: str) -> Optional[str]:
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1) if match else None

class EmailScanner:
    def __init__(self, email_config: dict):
        self.email_config = email_config
        self.parser = CreditCardParser()
    
    def scan_emails(self, days_back: int = 30) -> List[PaymentInfo]:
        payments = []
        
        try:
            mail = imaplib.IMAP4_SSL(self.email_config['imap_server'])
            mail.login(self.email_config['username'], self.email_config['password'])
            mail.select('inbox')
            
            # Search for emails from the last 30 days
            date_criteria = (datetime.now() - timedelta(days=days_back)).strftime('%d-%b-%Y')
            
            search_criteria = [
                'SINCE', date_criteria,
                'OR', 'FROM', 'chase.com',
                'OR', 'FROM', 'discover.com',
                'OR', 'FROM', 'citi.com',
                'OR', 'FROM', 'americanexpress.com',
                'SUBJECT', 'statement'
            ]
            
            status, messages = mail.search(None, *search_criteria)
            
            for num in messages[0].split():
                status, msg = mail.fetch(num, '(RFC822)')
                email_message = email.message_from_bytes(msg[0][1])
                
                subject = email_message['Subject']
                body = self._get_email_body(email_message)
                
                if body:
                    payment_info = self.parser.parse_email(body, subject)
                    if payment_info:
                        payments.append(payment_info)
            
            mail.close()
            mail.logout()
            
        except Exception as e:
            print(f"Error scanning emails: {e}")
        
        return payments
    
    def _get_email_body(self, email_message) -> str:
        body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode()
                    break
        else:
            body = email_message.get_payload(decode=True).decode()
        return body

class ReminderSystem:
    def __init__(self, db_path: str = "reminders.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY,
                bank_name TEXT,
                card_last_four TEXT,
                due_date TEXT,
                minimum_amount REAL,
                total_amount REAL,
                email_source TEXT,
                reminder_sent BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def store_payment(self, payment: PaymentInfo):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO payments 
            (bank_name, card_last_four, due_date, minimum_amount, total_amount, email_source)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            payment.bank_name,
            payment.card_last_four,
            payment.due_date.isoformat(),
            payment.minimum_amount,
            payment.total_amount,
            payment.email_source
        ))
        
        conn.commit()
        conn.close()
    
    def get_upcoming_payments(self, days_ahead: int = 7) -> List[PaymentInfo]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() + timedelta(days=days_ahead)).isoformat()
        
        cursor.execute('''
            SELECT bank_name, card_last_four, due_date, minimum_amount, total_amount, email_source
            FROM payments
            WHERE due_date <= ? AND reminder_sent = 0
            ORDER BY due_date
        ''', (cutoff_date,))
        
        payments = []
        for row in cursor.fetchall():
            payment = PaymentInfo(
                bank_name=row[0],
                card_last_four=row[1],
                due_date=datetime.fromisoformat(row[2]),
                minimum_amount=row[3],
                total_amount=row[4],
                email_source=row[5]
            )
            payments.append(payment)
        
        conn.close()
        return payments
    
    def mark_reminder_sent(self, payment: PaymentInfo):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE payments
            SET reminder_sent = 1
            WHERE bank_name = ? AND card_last_four = ? AND due_date = ?
        ''', (payment.bank_name, payment.card_last_four, payment.due_date.isoformat()))
        
        conn.commit()
        conn.close()

class NotificationSender:
    def __init__(self, config: dict):
        self.config = config
    
    def send_email_reminder(self, payment: PaymentInfo, recipient: str):
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config['smtp_username']
            msg['To'] = recipient
            msg['Subject'] = f"Credit Card Payment Reminder - {payment.bank_name}"
            
            body = f"""
            Credit Card Payment Reminder
            
            Bank: {payment.bank_name.upper()}
            Card ending in: {payment.card_last_four}
            Due Date: {payment.due_date.strftime('%B %d, %Y')}
            Minimum Payment: ${payment.minimum_amount:.2f}
            Total Balance: ${payment.total_amount:.2f}
            
            Days until due: {(payment.due_date - datetime.now()).days}
            
            Please make your payment before the due date to avoid late fees.
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
            server.starttls()
            server.login(self.config['smtp_username'], self.config['smtp_password'])
            text = msg.as_string()
            server.sendmail(self.config['smtp_username'], recipient, text)
            server.quit()
            
            print(f"Reminder sent for {payment.bank_name} card ending in {payment.card_last_four}")
            
        except Exception as e:
            print(f"Error sending email reminder: {e}")

class CreditCardReminderApp:
    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.email_scanner = EmailScanner(self.config['email'])
        self.reminder_system = ReminderSystem()
        self.notification_sender = NotificationSender(self.config['notifications'])
    
    def _load_config(self, config_path: str) -> dict:
        if not os.path.exists(config_path):
            self._create_default_config(config_path)
        
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def _create_default_config(self, config_path: str):
        default_config = {
            "email": {
                "imap_server": "imap.gmail.com",
                "username": "your_email@gmail.com",
                "password": "your_app_password"
            },
            "notifications": {
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_username": "your_email@gmail.com",
                "smtp_password": "your_app_password",
                "recipient": "your_email@gmail.com"
            },
            "reminder_days": [7, 3, 1],
            "scan_frequency_hours": 24
        }
        
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        print(f"Created default config at {config_path}. Please update with your credentials.")
    
    def scan_and_store_payments(self):
        print("Scanning emails for credit card statements...")
        payments = self.email_scanner.scan_emails()
        
        for payment in payments:
            self.reminder_system.store_payment(payment)
            print(f"Stored payment info: {payment.bank_name} - {payment.card_last_four}")
        
        print(f"Found and stored {len(payments)} payment records")
    
    def check_and_send_reminders(self):
        print("Checking for upcoming payments...")
        
        for days_ahead in self.config['reminder_days']:
            payments = self.reminder_system.get_upcoming_payments(days_ahead)
            
            for payment in payments:
                days_until_due = (payment.due_date - datetime.now()).days
                
                if days_until_due <= days_ahead:
                    self.notification_sender.send_email_reminder(
                        payment, 
                        self.config['notifications']['recipient']
                    )
                    self.reminder_system.mark_reminder_sent(payment)
    
    def run_scheduler(self):
        print("Starting Credit Card Payment Reminder App...")
        
        # Schedule tasks
        schedule.every().day.at("09:00").do(self.scan_and_store_payments)
        schedule.every().day.at("08:00").do(self.check_and_send_reminders)
        
        # Run initial scan
        self.scan_and_store_payments()
        
        # Keep the scheduler running
        while True:
            schedule.run_pending()
            time.sleep(3600)  # Check every hour

def main():
    app = CreditCardReminderApp()
    
    # For testing, run once
    app.scan_and_store_payments()
    app.check_and_send_reminders()
    
    # For production, run scheduler
    # app.run_scheduler()

if __name__ == "__main__":
    main()