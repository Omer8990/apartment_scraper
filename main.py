import os
from datetime import datetime, timedelta
from facebook_scraper import get_posts
import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, filters
import json
import logging
from dotenv import load_dotenv
import re
import time
from langdetect import detect
# from hebrew_numbers import gematria_to_int

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class HebrewApartmentMonitor:
    def __init__(self):
        # Initialize with environment variables
        self.telegram_token = os.getenv('TELEGRAM_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        # Facebook groups for Tel Aviv apartments
        self.fb_groups = [
            '287564448778602',  # First group
            '184920528370332',  # Second group
            'tlvrent',          # Third group
            '2092819334342645'  # Fourth group
        ]
        
        # Hebrew-specific search terms
        self.search_terms = {
            'rooms': ['חדרים', 'חד\'', 'חד'],
            'price': ['₪', 'ש"ח', 'שח'],
            'locations': {
                'תל אביב': ['תל אביב', 'תא', 'ת"א'],
                'פלורנטין': ['פלורנטין', 'פלורנתין'],
                'רוטשילד': ['רוטשילד'],
                # Add more neighborhoods as needed
            }
        }
        
        # Criteria for filtering apartments
        self.criteria = {
            'max_price': 8000,  # In NIS
            'min_rooms': 2,
            'locations': ['תל אביב', 'פלורנטין'],  # Default locations
            'last_check': datetime.now() - timedelta(hours=24)
        }
        
        # Initialize Telegram bot
        self.bot = telegram.Bot(token=self.telegram_token)
        
    def extract_price(self, text):
        """Extract price from Hebrew text"""
        # Common price patterns in Israeli listings
        price_patterns = [
            r'(\d{1,3}(,\d{3})*)\s*(₪|ש"ח|שח)',  # 5,000 ₪
            r'(\d+)\s*אלף',  # X thousand
            r'(\d+)k',  # Price in K
        ]
        
        for pattern in price_patterns:
            match = re.search(pattern, text)
            if match:
                price_str = match.group(1).replace(',', '')
                try:
                    price = float(price_str)
                    # If price is in thousands (k)
                    if 'אלף' in text[match.start():match.end()] or 'k' in text[match.start():match.end()]:
                        price *= 1000
                    return price
                except ValueError:
                    continue
        return None

    def extract_rooms(self, text):
        """Extract number of rooms from Hebrew text"""
        # Pattern for X rooms/X.5 rooms in Hebrew
        room_patterns = [
            r'(\d+(?:\.\d)?)\s*חדרים',
            r'(\d+(?:\.\d)?)\s*חד\'?',
            r'דירת\s*(\d+(?:\.\d)?)',
        ]
        
        for pattern in room_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None

    def check_match_criteria(self, post):
        """Check if a post matches the search criteria"""
        text = post['text']
        
        # Extract price
        price = self.extract_price(text)
        if not price or price > self.criteria['max_price']:
            return False
            
        # Extract rooms
        rooms = self.extract_rooms(text)
        if not rooms or rooms < self.criteria['min_rooms']:
            return False
            
        # Check location
        location_found = False
        for location in self.criteria['locations']:
            if any(term in text for term in self.search_terms['locations'].get(location, [])):
                location_found = True
                break
        if not location_found:
            return False
            
        return True
        
    def format_message(self, post):
        """Format the post information for Telegram message"""
        price = self.extract_price(post['text'])
        rooms = self.extract_rooms(post['text'])
        
        message = (
            f"🏠 דירה חדשה!\n\n"
            f"💰 מחיר: {price:,.0f} ₪\n"
            f"🔑 חדרים: {rooms}\n\n"
            f"📝 תיאור:\n{post['text'][:300]}...\n\n"
            f"🔗 לינק: {post['post_url']}\n"
            f"⏰ פורסם: {post['time']}\n"
        )
        return message
        
    def scan_groups(self):
        """Scan Facebook groups for new apartment posts"""
        try:
            for group_id in self.fb_groups:
                for post in get_posts(group_id, pages=10):
                    # Check if post is newer than last check
                    if post['time'] > self.criteria['last_check']:
                        if self.check_match_criteria(post):
                            message = self.format_message(post)
                            self.bot.send_message(
                                chat_id=self.chat_id,
                                text=message,
                                parse_mode='HTML'
                            )
            
            self.criteria['last_check'] = datetime.now()
            
        except Exception as e:
            logger.error(f"Error scanning groups: {str(e)}")
            
    def start_monitoring(self):
        """Start the monitoring process"""
        updater = Updater(self.telegram_token, use_context=True)
        dp = updater.dispatcher
        
        # Command handlers
        dp.add_handler(CommandHandler("start", self.cmd_start))
        dp.add_handler(CommandHandler("update_criteria", self.cmd_update_criteria))
        dp.add_handler(CommandHandler("add_location", self.cmd_add_location))
        
        # Start the bot
        updater.start_polling()
        logger.info("Bot started monitoring...")
        
        # Run the apartment scanning job every 15 minutes
        while True:
            self.scan_groups()
            time.sleep(900)  # Wait for 15 minutes
            
    def cmd_start(self, update, context):
        """Handle the /start command"""
        update.message.reply_text(
            "🏠 ברוכים הבאים לבוט חיפוש הדירות!\n"
            "אני אעדכן אותך כשאמצא דירות שמתאימות לקריטריונים שלך."
        )
        
    def cmd_update_criteria(self, update, context):
        """Handle the /update_criteria command"""
        try:
            args = context.args
            if len(args) >= 2:
                self.criteria['max_price'] = float(args[0])
                self.criteria['min_rooms'] = float(args[1])
                update.message.reply_text("הקריטריונים עודכנו בהצלחה!")
            else:
                update.message.reply_text(
                    "אנא ספק קריטריונים בפורמט:\n"
                    "/update_criteria מחיר_מקסימלי מספר_חדרים_מינימלי"
                )
        except ValueError:
            update.message.reply_text("פורמט לא תקין. אנא נסה שוב.")

    def cmd_add_location(self, update, context):
        """Handle the /add_location command"""
        if len(context.args) > 0:
            location = ' '.join(context.args)
            if location not in self.criteria['locations']:
                self.criteria['locations'].append(location)
                update.message.reply_text(f"השכונה {location} נוספה לחיפוש!")
            else:
                update.message.reply_text("השכונה כבר קיימת ברשימת החיפוש.")
        else:
            update.message.reply_text("אנא ספק שם שכונה להוספה")

if __name__ == "__main__":
    # Create .env file with the following variables:
    # TELEGRAM_TOKEN=your_telegram_bot_token
    # TELEGRAM_CHAT_ID=your_chat_id
    
    monitor = HebrewApartmentMonitor()
    monitor.start_monitoring()
