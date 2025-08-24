import tweepy
import requests
import json
import random
import time
from datetime import datetime
import os

class QuranBot:
    def __init__(self):
        # Load Twitter API keys from GitHub Secrets
        self.api_key = os.getenv("API_KEY")
        self.api_secret = os.getenv("API_SECRET")
        self.access_token = os.getenv("ACCESS_TOKEN")
        self.access_token_secret = os.getenv("ACCESS_TOKEN_SECRET")

        # Initialize Twitter API
        self.setup_twitter_api()

        # Quran API base URL
        self.quran_api_base = "https://api.alquran.cloud/v1"

        # Monthly limit
        self.MONTHLY_VERSE_LIMIT = 400

        # State file
        self.state_file = "quran_bot_state.json"
        self.load_state()

        
    def setup_twitter_api(self):
        """Initialize Twitter API connection"""
        print("🔄 Attempting to authenticate with X API...")
        
        try:
            print("📝 OAuth 1.0a authentication...")
            self.client = tweepy.Client(
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret,
                wait_on_rate_limit=True
            )
            
            # Test the connection
            me = self.client.get_me()
            if me.data:
                print(f"✅ Authentication successful!")
                print(f"🤖 Connected as: @{me.data.username}")
                return
                
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            
    def load_state(self):
        """Load bot state from file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    self.state = json.load(f)
            else:
                self.state = self.create_initial_state()
        except Exception as e:
            print(f"⚠️ Error loading state: {e}")
            self.state = self.create_initial_state()
    
    def create_initial_state(self):
        """Create initial state for the bot"""
        current_date = datetime.now()
        
        return {
            'current_chapter': self.select_monthly_chapter(),
            'current_verse_number': 1,
            'verses_posted_this_month': 0,
            'current_month': current_date.month,
            'current_year': current_date.year,
            'last_post_time': None,
            'chapter_verse_count': None  # Will be loaded when needed
        }
    
    def select_monthly_chapter(self):
        """Select a chapter for the current month (can have 400+ verses)"""
        # Chapters with enough verses for 400 posts
        large_chapters = [2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 16, 17, 18, 20, 21, 26, 37]
        return random.choice(large_chapters)
    
    def save_state(self):
        """Save bot state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"❌ Error saving state: {e}")
    
    def check_month_reset(self):
        """Check if we need to reset for a new month"""
        current_date = datetime.now()
        current_month = current_date.month
        current_year = current_date.year
        
        if (current_month != self.state['current_month'] or 
            current_year != self.state['current_year']):
            
            print(f"📅 New month detected! Starting fresh...")
            
            # Reset for new month
            self.state['current_chapter'] = self.select_monthly_chapter()
            self.state['current_verse_number'] = 1
            self.state['verses_posted_this_month'] = 0
            self.state['current_month'] = current_month
            self.state['current_year'] = current_year
            self.state['chapter_verse_count'] = None
            
            print(f"📖 Selected chapter {self.state['current_chapter']} for this month")
            self.save_state()
    
    def can_post_now(self):
        """Check if we can post now (hourly limit and monthly limit)"""
        current_time = datetime.now()
        
        # Check monthly limit
        if self.state['verses_posted_this_month'] >= self.MONTHLY_VERSE_LIMIT:
            print(f"🛑 Monthly limit of {self.MONTHLY_VERSE_LIMIT} verses reached!")
            return False
        
        # Check if an hour has passed since last post
        if self.state['last_post_time']:
            last_post = datetime.fromisoformat(self.state['last_post_time'])
            time_diff = current_time - last_post
            
            if time_diff.total_seconds() < 3600:  # 1 hour = 3600 seconds
                minutes_remaining = int((3600 - time_diff.total_seconds()) / 60)
                print(f"⏰ Must wait {minutes_remaining} more minutes before next post")
                return False
        
        return True
    
    def get_chapter_info(self):
        """Get information about the current chapter"""
        try:
            if not self.state['chapter_verse_count']:
                surah_info_url = f"{self.quran_api_base}/surah/{self.state['current_chapter']}"
                response = requests.get(surah_info_url)
                data = response.json()
                
                if data['code'] == 200:
                    self.state['chapter_verse_count'] = data['data']['numberOfAyahs']
                    self.save_state()
                    return data['data']
                    
        except Exception as e:
            print(f"❌ Error getting chapter info: {e}")
            return None
    
    def get_next_verse(self):
        """Get the next sequential verse from current chapter"""
        try:
            chapter = self.state['current_chapter']
            verse = self.state['current_verse_number']
            
            # Get chapter info if not cached
            chapter_info = self.get_chapter_info()
            if not chapter_info:
                return None
            
            # Check if we've reached the end of the chapter
            if verse > self.state['chapter_verse_count']:
                print(f"📖 Reached end of chapter {chapter}, cycling back to verse 1")
                verse = 1
                self.state['current_verse_number'] = 1
            
            # Get the verse in Arabic and English
            arabic_url = f"{self.quran_api_base}/ayah/{chapter}:{verse}"
            english_url = f"{self.quran_api_base}/ayah/{chapter}:{verse}/en.sahih"
            
            arabic_response = requests.get(arabic_url)
            english_response = requests.get(english_url)
            
            arabic_data = arabic_response.json()
            english_data = english_response.json()
            
            if arabic_data['code'] == 200 and english_data['code'] == 200:
                verse_data = {
                    'arabic': arabic_data['data']['text'],
                    'english': english_data['data']['text'],
                    'surah_name': arabic_data['data']['surah']['englishName'],
                    'surah_number': chapter,
                    'ayah_number': verse,
                    'reference': f"Surah {arabic_data['data']['surah']['englishName']} ({chapter}:{verse})"
                }
                return verse_data
                
        except Exception as e:
            print(f"❌ Error fetching verse: {e}")
            return None
    
    def format_tweet(self, verse_data):
        """Format the verse data into a tweet"""
        if not verse_data:
            return None
            
        # Create the tweet text
        tweet = f"{verse_data['arabic']}\n\n"
        tweet += f'"{verse_data["english"]}"\n\n'
        tweet += f"— {verse_data['reference']}"
        
        # Handle Twitter's 280 character limit
        if len(tweet) > 280:
            # Calculate available space for English translation
            base_length = len(verse_data['arabic']) + len(verse_data['reference']) + len('\n\n""\n\n— ')
            available_chars = 280 - base_length - 3  # -3 for "..."
            
            if available_chars > 20:  # Ensure we have reasonable space
                truncated_english = verse_data['english'][:available_chars] + "..."
                
                tweet = f"{verse_data['arabic']}\n\n"
                tweet += f'"{truncated_english}"\n\n'
                tweet += f"— {verse_data['reference']}"
        
        return tweet
    
    def post_verse(self):
        """Get next verse and post it to Twitter"""
        try:
            # Check if we can post
            if not self.can_post_now():
                return False
            
            print(f"🔄 Fetching verse {self.state['current_verse_number']} from chapter {self.state['current_chapter']}...")
            verse_data = self.get_next_verse()
            
            if verse_data:
                tweet_text = self.format_tweet(verse_data)
                
                if tweet_text:
                    # Check if client is available
                    if not hasattr(self, 'client'):
                        print("❌ Twitter client not initialized")
                        return False
                    
                    # Post the tweet
                    response = self.client.create_tweet(text=tweet_text)
                    if response.data:
                        # Update state
                        self.state['current_verse_number'] += 1
                        self.state['verses_posted_this_month'] += 1
                        self.state['last_post_time'] = datetime.now().isoformat()
                        self.save_state()
                        
                        print(f"✅ Successfully posted verse: {verse_data['reference']}")
                        print(f"📊 Progress: {self.state['verses_posted_this_month']}/{self.MONTHLY_VERSE_LIMIT} verses this month")
                        print(f"🔗 Tweet ID: {response.data['id']}")
                        return True
                    else:
                        print("❌ Failed to post tweet - no response data")
                        return False
                else:
                    print("❌ Failed to format tweet")
                    return False
            else:
                print("❌ Failed to fetch verse")
                return False
                
        except Exception as e:
            print(f"❌ Error posting tweet: {e}")
            return False
    
    def run_bot(self):
        """Run the bot once"""
        print(f"🕐 Bot started at {datetime.now()}")
        print(f"📖 Current chapter: {self.state['current_chapter']}")
        print(f"📄 Next verse: {self.state['current_verse_number']}")
        print(f"📊 Monthly progress: {self.state['verses_posted_this_month']}/{self.MONTHLY_VERSE_LIMIT}")
        
        # Check for month reset
        self.check_month_reset()
        
        # Try to post
        success = self.post_verse()
        
        if success:
            print("✅ Bot run completed successfully!")
        else:
            print("❌ Bot run completed with issues!")
            
        return success

# For running the bot once
def main():
    bot = QuranBot()
    bot.run_bot()

if __name__ == "__main__":
    main()

# For continuous running (run every hour)
def run_continuously():
    """Run the bot every hour"""
    bot = QuranBot()
    
    while True:
        print(f"\n{'='*60}")
        print(f"🕐 Starting hourly cycle at {datetime.now()}")
        
        success = bot.post_verse()
        
        if success:
            print("✅ Verse posted successfully!")
        else:
            print("❌ Skipped or failed to post verse")
        
        # Calculate next run time
        next_run = datetime.now() + timedelta(hours=1)
        print(f"😴 Sleeping for 1 hour...")
        print(f"⏰ Next post scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Sleep for 1 hour (3600 seconds)
        time.sleep(3600)

# Alternative: Run with precise hourly timing
def run_on_schedule():
    """Run the bot at the top of each hour"""
    import schedule
    
    bot = QuranBot()
    
    def job():
        print(f"\n{'='*60}")
        print(f"🕐 Scheduled run at {datetime.now()}")
        bot.run_bot()
    
    # Schedule to run at the top of every hour
    schedule.every().hour.at(":00").do(job)
    
    print("📅 Bot scheduled to run every hour at :00")
    print("🔄 Waiting for scheduled times...")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute
