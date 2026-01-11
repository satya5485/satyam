#!/usr/bin/env python3
"""
Telegram Mass Reporting Bot - Advanced Version
Use with caution and only for legitimate reporting purposes
"""

import asyncio
import random
import logging
import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
import configparser
import sys
import os

from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.types import InputReportReasonSpam, InputReportReasonFake, InputReportReasonViolence
from telethon.tl.types import InputReportReasonChildAbuse, InputReportReasonPornography
from telethon.tl.types import InputReportReasonCopyright, InputReportReasonOther

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('report_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class ReportConfig:
    """Configuration for reporting"""
    channel_username: str
    max_reports_per_account: int
    reports_per_day: int
    delay_between_reports: tuple  # (min, max) seconds
    use_proxy: bool
    proxy_config: Optional[Dict]

@dataclass
class Account:
    """Telegram account information"""
    name: str
    api_id: int
    api_hash: str
    phone: str
    proxy: Optional[Dict] = None
    enabled: bool = True
    last_report_time: Optional[datetime] = None
    reports_today: int = 0

class MassReportBot:
    def __init__(self, config_path: str = 'config.ini'):
        self.config_path = config_path
        self.accounts: List[Account] = []
        self.report_config: Optional[ReportConfig] = None
        self.clients: Dict[str, TelegramClient] = {}
        self.running = False
        
        # Report reasons mapping
        self.report_reasons = {
            'spam': InputReportReasonSpam(),
            'fake': InputReportReasonFake(),
            'violence': InputReportReasonViolence(),
            'child_abuse': InputReportReasonChildAbuse(),
            'pornography': InputReportReasonPornography(),
            'copyright': InputReportReasonCopyright(),
            'other': InputReportReasonOther()
        }
        
        # Detailed report descriptions
        self.reason_descriptions = {
            'spam': """This channel is actively promoting and distributing illegal game cheats for Battlegrounds Mobile India (BGMI). They are:

1. Selling fake/working hacks for monetary gain
2. Distributing malicious software (aimbots, wallhacks, speed hacks)
3. Violating BGMI Terms of Service and End User License Agreement
4. Facilitating unfair gameplay and ruining the gaming experience
5. Possibly distributing malware through fake cheat software

This violates:
- Telegram Terms of Service (Section 8: Prohibited Services)
- Indian IT Act, 2000
- Game publisher's intellectual property rights""",
            
            'fake': """Channel operators are impersonating legitimate game service providers and scamming users:

1. Pretending to be official BGMI representatives
2. Taking payments for non-existent or non-functional hacks
3. Stealing user credentials through fake login pages
4. Distributing ransomware disguised as game modifications
5. Engaging in financial fraud with fake refund policies

Evidence of fraudulent activity can be provided upon request.""",
            
            'violence': """Content promotes violence through:

1. Encouraging harassment of legitimate players
2. Promoting tools for griefing and bullying in-game
3. Creating toxic gaming environment
4. Violating community guidelines against hate speech and harassment""",
            
            'copyright': """Distributing unauthorized modifications of copyrighted game software:

1. Reverse engineering and modifying game code without permission
2. Distributing cracked/pirated versions of game assets
3. Violating Krafton's intellectual property rights
4. Circumventing anti-cheat mechanisms (TenProtect/BattlEye)"""
        }
        
        self.load_config()
    
    def load_config(self):
        """Load configuration from file"""
        config = configparser.ConfigParser()
        
        if not os.path.exists(self.config_path):
            self.create_default_config()
            config.read(self.config_path)
        else:
            config.read(self.config_path)
        
        # Load accounts
        for section in config.sections():
            if section.startswith('ACCOUNT_'):
                try:
                    account = Account(
                        name=config[section]['name'],
                        api_id=int(config[section]['api_id']),
                        api_hash=config[section]['api_hash'],
                        phone=config[section]['phone'],
                        enabled=config.getboolean(section, 'enabled', fallback=True)
                    )
                    
                    # Load proxy if configured
                    if config.get(section, 'proxy', fallback=None):
                        proxy_parts = config[section]['proxy'].split(':')
                        if len(proxy_parts) == 4:
                            account.proxy = {
                                'proxy_type': 'socks5',
                                'addr': proxy_parts[0],
                                'port': int(proxy_parts[1]),
                                'username': proxy_parts[2],
                                'password': proxy_parts[3]
                            }
                    
                    self.accounts.append(account)
                except Exception as e:
                    logger.error(f"Error loading account {section}: {e}")
        
        # Load report configuration
        if 'REPORT' in config:
            self.report_config = ReportConfig(
                channel_username=config['REPORT']['channel_username'],
                max_reports_per_account=int(config['REPORT']['max_reports_per_account']),
                reports_per_day=int(config['REPORT']['reports_per_day']),
                delay_between_reports=(
                    int(config['REPORT']['min_delay']),
                    int(config['REPORT']['max_delay'])
                ),
                use_proxy=config.getboolean('REPORT', 'use_proxy', fallback=False),
                proxy_config=None
            )
    
    def create_default_config(self):
        """Create default configuration file"""
        config = configparser.ConfigParser()
        
        # Report configuration
        config['REPORT'] = {
            'channel_username': '@target_channel_username',
            'max_reports_per_account': '5',
            'reports_per_day': '50',
            'min_delay': '30',
            'max_delay': '120',
            'use_proxy': 'False'
        }
        
        # Account template
        config['ACCOUNT_1'] = {
            'name': 'Account 1',
            'api_id': 'YOUR_API_ID',
            'api_hash': 'YOUR_API_HASH',
            'phone': '+1234567890',
            'enabled': 'True',
            'proxy': ''  # ip:port:username:password
        }
        
        # Advanced settings
        config['ADVANCED'] = {
            'randomize_reasons': 'True',
            'rotate_accounts': 'True',
            'human_like_delays': 'True',
            'max_concurrent_sessions': '3',
            'save_report_logs': 'True'
        }
        
        with open(self.config_path, 'w') as f:
            config.write(f)
        logger.info(f"Created default config at {self.config_path}")
    
    async def initialize_client(self, account: Account) -> bool:
        """Initialize Telegram client for an account"""
        try:
            session_name = f"sessions/{account.name}"
            os.makedirs('sessions', exist_ok=True)
            
            if account.proxy:
                client = TelegramClient(
                    session_name,
                    account.api_id,
                    account.api_hash,
                    proxy=account.proxy
                )
            else:
                client = TelegramClient(
                    session_name,
                    account.api_id,
                    account.api_hash
                )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.info(f"Authorizing {account.name}...")
                await client.send_code_request(account.phone)
                
                # In a real bot, you'd get this from user input
                # For automation, you need to handle 2FA properly
                code = input(f"Enter code for {account.phone}: ")
                await client.sign_in(account.phone, code)
            
            self.clients[account.name] = client
            logger.info(f"Successfully initialized {account.name}")
            return True
            
        except SessionPasswordNeededError:
            logger.error(f"2FA enabled for {account.name}. Need password.")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize {account.name}: {e}")
            return False
    
    async def send_report(self, client: TelegramClient, account: Account, 
                         channel_username: str, reason_type: str) -> bool:
        """Send a single report"""
        try:
            # Get channel entity
            channel = await client.get_entity(channel_username)
            
            # Select reason
            reason = self.report_reasons.get(reason_type, InputReportReasonSpam())
            description = self.reason_descriptions.get(reason_type, "")
            
            # For 'other' reason, we need to provide description
            if reason_type == 'other':
                reason = InputReportReasonOther()
                # Set the description for other reason
                # Note: This might need adjustment based on Telethon version
                pass
            
            # Send report
            await client(ReportRequest(
                peer=channel,
                reason=reason,
                message=description[:512] if description else ""
            ))
            
            logger.info(f"[{account.name}] Reported {channel_username} for {reason_type}")
            account.reports_today += 1
            account.last_report_time = datetime.now()
            
            # Save report log
            self.save_report_log(account, channel_username, reason_type, "SUCCESS")
            
            return True
            
        except FloodWaitError as e:
            logger.warning(f"[{account.name}] Flood wait: {e.seconds} seconds")
            await asyncio.sleep(e.seconds + random.randint(5, 15))
            return False
        except Exception as e:
            logger.error(f"[{account.name}] Report failed: {e}")
            self.save_report_log(account, channel_username, reason_type, f"FAILED: {e}")
            return False
    
    def save_report_log(self, account: Account, channel: str, reason: str, status: str):
        """Save report log to file"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'account': account.name,
            'channel': channel,
            'reason': reason,
            'status': status
        }
        
        os.makedirs('logs', exist_ok=True)
        log_file = f"logs/reports_{datetime.now().strftime('%Y%m%d')}.json"
        
        try:
            # Load existing logs
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    logs = json.load(f)
            else:
                logs = []
            
            # Add new entry
            logs.append(log_entry)
            
            # Save
            with open(log_file, 'w') as f:
                json.dump(logs, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save log: {e}")
    
    async def smart_delay(self, account: Account):
        """Human-like delay between reports"""
        min_delay, max_delay = self.report_config.delay_between_reports
        
        # Add randomness
        delay = random.randint(min_delay, max_delay)
        
        # If account made many reports recently, increase delay
        if account.reports_today > 10:
            delay *= random.uniform(1.2, 1.8)
        
        # Random pauses (human behavior simulation)
        if random.random() < 0.1:  # 10% chance
            delay += random.randint(60, 300)
        
        logger.info(f"[{account.name}] Waiting {delay} seconds...")
        await asyncio.sleep(delay)
    
    def rotate_reasons(self) -> List[str]:
        """Get rotated list of report reasons"""
        base_reasons = ['spam', 'fake', 'violence', 'copyright', 'other']
        
        # Shuffle for randomness
        if random.choice([True, False]):
            random.shuffle(base_reasons)
        
        # Sometimes focus on specific reasons
        if random.random() < 0.3:
            return ['spam', 'spam', 'fake']  # Multiple spam reports
        
        return base_reasons
    
    async def report_worker(self, account: Account):
        """Worker process for a single account"""
        if not account.enabled:
            logger.info(f"[{account.name}] Account disabled, skipping...")
            return
        
        client = self.clients.get(account.name)
        if not client:
            logger.error(f"[{account.name}] No client available")
            return
        
        reports_sent = 0
        max_reports = self.report_config.max_reports_per_account
        
        while self.running and reports_sent < max_reports:
            try:
                # Check daily limit
                if account.reports_today >= self.report_config.reports_per_day:
                    logger.info(f"[{account.name}] Daily limit reached")
                    break
                
                # Get reasons for this batch
                reasons = self.rotate_reasons()
                
                for reason in reasons:
                    if not self.running or reports_sent >= max_reports:
                        break
                    
                    # Send report
                    success = await self.send_report(
                        client, account,
                        self.report_config.channel_username,
                        reason
                    )
                    
                    if success:
                        reports_sent += 1
                    
                    # Delay between reports
                    if reports_sent < max_reports:
                        await self.smart_delay(account)
                
                # Longer break between batches
                if reports_sent < max_reports and self.running:
                    batch_break = random.randint(300, 900)  # 5-15 minutes
                    logger.info(f"[{account.name}] Batch complete, resting {batch_break//60} minutes")
                    await asyncio.sleep(batch_break)
                    
            except Exception as e:
                logger.error(f"[{account.name}] Worker error: {e}")
                await asyncio.sleep(60)
        
        logger.info(f"[{account.name}] Finished. Sent {reports_sent} reports.")
    
    async def reset_daily_counts(self):
        """Reset daily report counts at midnight"""
        while self.running:
            now = datetime.now()
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
            sleep_time = (tomorrow - now).total_seconds()
            
            await asyncio.sleep(sleep_time)
            
            # Reset counts
            for account in self.accounts:
                account.reports_today = 0
            logger.info("Reset daily report counts")
    
    async def run(self):
        """Main execution method"""
        logger.info("Initializing Telegram Mass Reporting Bot...")
        
        # Initialize all accounts
        init_tasks = []
        for account in self.accounts:
            if account.enabled:
                init_tasks.append(self.initialize_client(account))
        
        results = await asyncio.gather(*init_tasks)
        successful_accounts = sum(results)
        
        if successful_accounts == 0:
            logger.error("No accounts initialized successfully!")
            return
        
        logger.info(f"Successfully initialized {successful_accounts} accounts")
        
        # Start reset timer
        reset_task = asyncio.create_task(self.reset_daily_counts())
        
        # Start reporting workers
        self.running = True
        worker_tasks = []
        
        for account in self.accounts:
            if account.name in self.clients:
                task = asyncio.create_task(self.report_worker(account))
                worker_tasks.append(task)
        
        try:
            # Run for specified duration or until stopped
            await asyncio.gather(*worker_tasks)
            
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.running = False
            reset_task.cancel()
            
            # Disconnect all clients
            for client in self.clients.values():
                await client.disconnect()
            
            logger.info("Bot stopped")

class TelegramReportBot:
    """Simplified version for bot integration"""
    
    def __init__(self):
        self.mass_bot = MassReportBot()
    
    async def start_reporting(self, channel_username: str):
        """Start reporting process for a channel"""
        if not self.mass_bot.report_config:
            return "Configuration not loaded"
        
        self.mass_bot.report_config.channel_username = channel_username
        await self.mass_bot.run()
        return "Reporting completed"
    
    def get_stats(self) -> Dict:
        """Get reporting statistics"""
        stats = {
            'total_accounts': len(self.mass_bot.accounts),
            'enabled_accounts': sum(1 for a in self.mass_bot.accounts if a.enabled),
            'total_reports_today': sum(a.reports_today for a in self.mass_bot.accounts),
            'active_clients': len(self.mass_bot.clients)
        }
        return stats

# Web interface for the bot (Flask example)
"""
from flask import Flask, request, jsonify
app = Flask(__name__)
bot = TelegramReportBot()

@app.route('/api/report', methods=['POST'])
def start_report():
    data = request.json
    channel = data.get('channel')
    
    if not channel:
        return jsonify({'error': 'Channel required'}), 400
    
    # Run in background
    asyncio.create_task(bot.start_reporting(channel))
    
    return jsonify({'status': 'started', 'channel': channel})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    return jsonify(bot.get_stats())

if __name__ == '__main__':
    app.run(port=5000)
"""

async def main():
    """Main function"""
    bot = MassReportBot()
    await bot.run()

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('sessions', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    # Run the bot
    asyncio.run(main())
