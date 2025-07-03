# Credit Card Payment Reminder App

A Python application that automatically scans your emails for credit card statements and sends reminders before payment deadlines.

## Features

- **Email Scanning**: Automatically scans emails from major banks (Chase, Discover, Citi, Amex)
- **Payment Detection**: Extracts due dates, minimum payments, and card information
- **Smart Reminders**: Sends alerts 7, 3, and 1 days before due dates
- **Database Storage**: Tracks payment information and reminder status
- **Configurable**: Easy configuration through JSON file

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Email Access**:
   - Update `config.json` with your email credentials
   - For Gmail, use App Passwords instead of regular password
   - Enable IMAP access in your email settings

3. **Run the Application**:
   ```bash
   python main.py or pipenv run python main.py
   ```

## Configuration

The app creates a `config.json` file with the following structure:

```json
{
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
```

## Supported Banks

- Chase
- Discover
- Citi
- American Express

## Security Notes

- Use App Passwords for Gmail
- Keep your config.json file secure
- Consider using environment variables for sensitive data

## Usage

The app runs in two modes:
- **Test Mode**: Run once to scan and check reminders
- **Production Mode**: Continuous scheduling with daily scans

## Database

The app uses SQLite to store payment information locally in `reminders.db`.