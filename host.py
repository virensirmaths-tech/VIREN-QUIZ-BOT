import asyncio
import re
from datetime import datetime
from telegram.ext import (
    Application, PollAnswerHandler, CommandHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler,
    ChatMemberHandler, CallbackQueryHandler
)
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8344828734:AAFBDD9uHkt8_09dTODMC4Riy6yKTPa4yl0"  # Replace with your token from BotFather

# ADMIN USER ID - Get yours from @userinfobot
ADMIN_USER_ID = 1845347130  # REPLACE WITH YOUR USER ID

# States for conversation
WAITING_FILE, WAITING_SUBJECT, WAITING_GROUPS = range(3)
# ======================================================


class QuizBot:
    def __init__(self, application):
        self.app = application
        self.bot = application.bot
        self.admin_id = ADMIN_USER_ID
        self.subjects = {}
        self.poll_mapping = {}
        self.leaderboard = {}
        self.managed_groups = set()
        self.temp_questions = {}
        
    def parse_questions(self, text):
        """Parse questions from text content"""
        questions = []
        pattern = r'Q\d+\.\s*(.+?)\s*A\.\s*(.+?)\s*B\.\s*(.+?)\s*C\.\s*(.+?)\s*D\.\s*(.+?)\s*Ans\.\s*([A-D])'
        matches = re.finditer(pattern, text, re.DOTALL)
        
        for match in matches:
            question_text = match.group(1).strip()
            options = [
                match.group(2).strip(),
                match.group(3).strip(),
                match.group(4).strip(),
                match.group(5).strip()
            ]
            correct_answer = match.group(6).strip()
            correct_index = ord(correct_answer) - ord('A')
            
            questions.append({
                'question': question_text,
                'options': options,
                'correct_answer': correct_index
            })
        
        return questions
    
    async def is_admin(self, user_id, chat_id=None):
        """Check if user is THE admin or group admin"""
        if user_id == self.admin_id:
            return True
        
        if chat_id:
            try:
                member = await self.bot.get_chat_member(chat_id, user_id)
                return member.status in ['creator', 'administrator']
            except:
                return False
        
        return False
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = update.effective_user.id
        chat_type = update.effective_chat.type
        
        if chat_type == "private":
            if user_id == self.admin_id:
                keyboard = [
                    ["📤 Upload Quiz", "📚 My Subjects"],
                    ["👥 My Groups", "📊 Dashboard"],
                    ["❓ Help"]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                await update.message.reply_text(
                    "👋 Welcome Admin!\n\n"
                    "🎯 Control your quiz bot from here:\n\n"
                    "📤 Upload Quiz - Send me a text file\n"
                    "📚 My Subjects - View all subjects\n"
                    "👥 My Groups - Manage groups\n"
                    "📊 Dashboard - View statistics\n\n"
                    "Let's get started!",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    "👋 Hello! I'm a Quiz Bot.\n\n"
                    "This bot is managed by an admin.\n"
                    "You can participate in quizzes posted in groups!"
                )
        else:
            await update.message.reply_text(
                "👋 Hello! I'm ready to host quizzes here!\n\n"
                "📝 Admins can use:\n"
                "/quiz - Start a quiz\n"
                "/leaderboard - View rankings\n"
                "/stats - View statistics\n\n"
                "Students can participate in quizzes!"
            )
    
    async def handle_file_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text file upload from admin"""
        user_id = update.effective_user.id
        
        if user_id != self.admin_id:
            return
        
        if not update.message.document:
            return
        
        file = update.message.document
        if not file.file_name.endswith('.txt'):
            await update.message.reply_text("❌ Please send a .txt file!")
            return
        
        try:
            file_obj = await file.get_file()
            file_content = await file_obj.download_as_bytearray()
            text = file_content.decode('utf-8')
            
            questions = self.parse_questions(text)
            
            if not questions:
                await update.message.reply_text(
                    "❌ No questions found in file!\n\n"
                    "Make sure format is:\n"
                    "Q1. Question? A. opt1 B. opt2 C. opt3 D. opt4 Ans. B"
                )
                return
            
            context.user_data['temp_questions'] = questions
            context.user_data['temp_filename'] = file.file_name
            
            await update.message.reply_text(
                f"✅ Found {len(questions)} questions!\n\n"
                f"📝 Enter subject name (e.g., Math, Science):"
            )
            
            return WAITING_SUBJECT
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error processing file: {e}")
            return ConversationHandler.END
    
    async def receive_subject_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive subject name for uploaded quiz"""
        subject = update.message.text.strip().lower()
        
        if not subject:
            await update.message.reply_text("❌ Please enter a valid subject name!")
            return WAITING_SUBJECT
        
        self.subjects[subject] = context.user_data['temp_questions']
        
        if not self.managed_groups:
            await update.message.reply_text(
                "❌ No groups available!\n\n"
                "Please add me to groups first and make me admin.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        keyboard = []
        for group_id in self.managed_groups:
            try:
                chat = await self.bot.get_chat(group_id)
                keyboard.append([f"✅ {chat.title}"])
            except:
                pass
        
        keyboard.append(["🚀 Post to All Groups"])
        keyboard.append(["❌ Cancel"])
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        context.user_data['current_subject'] = subject
        
        await update.message.reply_text(
            f"✅ Subject '{subject.upper()}' created with {len(self.subjects[subject])} questions!\n\n"
            f"📤 Select groups to post quiz:",
            reply_markup=reply_markup
        )
        
        return WAITING_GROUPS
    
    async def receive_group_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle group selection for posting quiz"""
        choice = update.message.text
        subject = context.user_data.get('current_subject')
        
        if choice == "❌ Cancel":
            await update.message.reply_text(
                "❌ Cancelled. Quiz saved but not posted.",
                reply_markup=ReplyKeyboardMarkup([
                    ["📤 Upload Quiz", "📚 My Subjects"],
                    ["👥 My Groups", "📊 Dashboard"]
                ], resize_keyboard=True)
            )
            return ConversationHandler.END
        
        target_groups = []
        
        if choice == "🚀 Post to All Groups":
            target_groups = list(self.managed_groups)
        else:
            for group_id in self.managed_groups:
                try:
                    chat = await self.bot.get_chat(group_id)
                    if f"✅ {chat.title}" == choice:
                        target_groups.append(group_id)
                        break
                except:
                    pass
        
        if not target_groups:
            await update.message.reply_text("❌ No valid groups selected!")
            return WAITING_GROUPS
        
        await update.message.reply_text(
            "🚀 Posting quiz...",
            reply_markup=ReplyKeyboardRemove()
        )
        
        success_count = 0
        for group_id in target_groups:
            result = await self.post_quiz_to_group(group_id, subject)
            if result:
                success_count += 1
        
        keyboard = [
            ["📤 Upload Quiz", "📚 My Subjects"],
            ["👥 My Groups", "📊 Dashboard"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"✅ Quiz posted successfully to {success_count}/{len(target_groups)} groups!\n\n"
            f"📊 Subject: {subject.upper()}\n"
            f"📝 Questions: {len(self.subjects[subject])}",
            reply_markup=reply_markup
        )
        
        return ConversationHandler.END
    
    async def post_quiz_to_group(self, group_id, subject):
        """Post quiz questions to a group"""
        if subject not in self.subjects:
            return False
        
        try:
            if group_id not in self.leaderboard:
                self.leaderboard[group_id] = {}
            if subject not in self.leaderboard[group_id]:
                self.leaderboard[group_id][subject] = {}
            
            questions = self.subjects[subject]
            
            await self.bot.send_message(
                chat_id=group_id,
                text=f"🎉 {subject.upper()} QUIZ STARTING! 🎉\n\n"
                     f"📝 Total Questions: {len(questions)}\n\n"
                     f"✨ Attempt any question anytime!\n"
                     f"🏆 Use /leaderboard to check rankings\n\n"
                     f"Good luck! 🍀"
            )
            
            await asyncio.sleep(3)
            
            for i, question in enumerate(questions, 1):
                await self.send_question(group_id, subject, i, question)
                if i < len(questions):
                    await asyncio.sleep(3)
            
            await self.bot.send_message(
                chat_id=group_id,
                text=f"✅ All {len(questions)} questions posted!\n\n"
                     f"📝 Attempt at your convenience\n"
                     f"🏆 Check rankings: /leaderboard"
            )
            
            return True
            
        except Exception as e:
            print(f"Error posting to group {group_id}: {e}")
            return False
    
    async def send_question(self, group_id, subject, q_num, question_data):
        """Send individual question"""
        try:
            question_text = f"📚 {subject.upper()} - Q{q_num}/{len(self.subjects[subject])}:\n\n{question_data['question']}"
            await self.bot.send_message(chat_id=group_id, text=question_text)
            
            await asyncio.sleep(2)
            
            poll_message = await self.bot.send_poll(
                chat_id=group_id,
                question=f"Q{q_num}: Select your answer",
                options=question_data['options'],
                type='quiz',
                correct_option_id=question_data['correct_answer'],
                is_anonymous=False
            )
            
            self.poll_mapping[poll_message.poll.id] = {
                'question_index': q_num - 1,
                'correct_answer': question_data['correct_answer'],
                'group_id': group_id,
                'subject': subject
            }
            
            return True
        except Exception as e:
            print(f"Error sending question: {e}")
            return False
    
    async def handle_poll_answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Track poll answers"""
        poll_answer = update.poll_answer
        poll_id = poll_answer.poll_id
        user = poll_answer.user
        
        if poll_id not in self.poll_mapping:
            return
        
        poll_info = self.poll_mapping[poll_id]
        group_id = poll_info['group_id']
        question_index = poll_info['question_index']
        correct_answer = poll_info['correct_answer']
        subject = poll_info['subject']
        
        if group_id not in self.leaderboard:
            self.leaderboard[group_id] = {}
        if subject not in self.leaderboard[group_id]:
            self.leaderboard[group_id][subject] = {}
        if user.id not in self.leaderboard[group_id][subject]:
            self.leaderboard[group_id][subject][user.id] = {
                'name': user.full_name,
                'username': user.username or '',
                'correct': 0,
                'wrong': 0,
                'answered': set()
            }
        
        user_stats = self.leaderboard[group_id][subject][user.id]
        
        if question_index in user_stats['answered']:
            return
        
        user_stats['answered'].add(question_index)
        
        if len(poll_answer.option_ids) > 0:
            selected_option = poll_answer.option_ids[0]
            if selected_option == correct_answer:
                user_stats['correct'] += 1
            else:
                user_stats['wrong'] += 1
    
    async def quiz_command_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /quiz command in group"""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        if not await self.is_admin(user_id, chat_id):
            await update.message.reply_text("⚠️ Only admins can start quizzes!")
            return
        
        if not self.subjects:
            await update.message.reply_text("❌ No subjects available! Admin needs to upload quizzes first.")
            return
        
        keyboard = []
        for subject in self.subjects.keys():
            keyboard.append([InlineKeyboardButton(
                f"📚 {subject.upper()} ({len(self.subjects[subject])} questions)",
                callback_data=f"start_quiz_{subject}_{chat_id}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📚 Select a subject to start:",
            reply_markup=reply_markup
        )
    
    async def handle_quiz_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle quiz start callback"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        if data.startswith("start_quiz_"):
            parts = data.split("_")
            subject = parts[2]
            group_id = int(parts[3])
            
            await query.edit_message_text(f"🚀 Starting {subject.upper()} quiz...")
            await self.post_quiz_to_group(group_id, subject)
    
    async def leaderboard_command_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /leaderboard in group"""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        if not await self.is_admin(user_id, chat_id):
            await update.message.reply_text("⚠️ Only admins can view leaderboard!")
            return
        
        if chat_id not in self.leaderboard or not self.leaderboard[chat_id]:
            await update.message.reply_text("📊 No quiz data available yet!")
            return
        
        if context.args:
            subject = context.args[0].lower()
            if subject in self.leaderboard[chat_id]:
                await self.show_leaderboard(chat_id, subject)
            else:
                await update.message.reply_text(f"❌ No data for subject '{subject}'!")
            return
        
        keyboard = []
        for subject in self.leaderboard[chat_id].keys():
            keyboard.append([InlineKeyboardButton(
                f"📊 {subject.upper()}",
                callback_data=f"leaderboard_{subject}_{chat_id}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📊 Select subject to view leaderboard:",
            reply_markup=reply_markup
        )
    
    async def handle_leaderboard_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle leaderboard callback"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        if data.startswith("leaderboard_"):
            parts = data.split("_")
            subject = parts[1]
            group_id = int(parts[2])
            
            await query.edit_message_text(f"📊 Loading {subject.upper()} leaderboard...")
            await self.show_leaderboard(group_id, subject)
    
    async def show_leaderboard(self, group_id, subject):
        """Display complete leaderboard"""
        try:
            if group_id not in self.leaderboard or subject not in self.leaderboard[group_id]:
                await self.bot.send_message(
                    chat_id=group_id,
                    text=f"😔 No participants for {subject.upper()} yet!"
                )
                return
            
            participants = self.leaderboard[group_id][subject]
            if not participants:
                await self.bot.send_message(
                    chat_id=group_id,
                    text=f"😔 No participants for {subject.upper()} yet!"
                )
                return
            
            sorted_users = sorted(
                participants.items(),
                key=lambda x: (x[1]['correct'], -x[1]['wrong']),
                reverse=True
            )
            
            top_text = f"🏆 {subject.upper()} - TOP 10 🏆\n"
            top_text += f"📅 {datetime.now().strftime('%B %d, %I:%M %p')}\n"
            top_text += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for rank, (user_id, stats) in enumerate(sorted_users[:10], 1):
                medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"{rank}."
                username = f"@{stats['username']}" if stats['username'] else stats['name']
                total = stats['correct'] + stats['wrong']
                accuracy = (stats['correct'] / total * 100) if total > 0 else 0
                
                top_text += f"{medal} {username}\n"
                top_text += f"   ✅ {stats['correct']} | ❌ {stats['wrong']} | 📊 {accuracy:.1f}%\n\n"
            
            await self.bot.send_message(chat_id=group_id, text=top_text)
            
            await asyncio.sleep(1)
            
            all_text = f"📋 ALL {subject.upper()} PARTICIPANTS\n"
            all_text += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            all_text += f"Total: {len(sorted_users)} participants\n\n"
            
            for user_id, stats in sorted_users:
                username = f"@{stats['username']}" if stats['username'] else stats['name']
                total = stats['correct'] + stats['wrong']
                
                all_text += f"• {username}\n"
                all_text += f"  ✅ {stats['correct']} | ❌ {stats['wrong']} | 📝 {total}/{len(self.subjects[subject])}\n\n"
                
                if len(all_text) > 3500:
                    await self.bot.send_message(chat_id=group_id, text=all_text)
                    all_text = ""
                    await asyncio.sleep(1)
            
            if all_text:
                await self.bot.send_message(chat_id=group_id, text=all_text)
                
        except Exception as e:
            print(f"Error showing leaderboard: {e}")
    
    async def stats_command_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats in group"""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        if not await self.is_admin(user_id, chat_id):
            await update.message.reply_text("⚠️ Only admins can view stats!")
            return
        
        if chat_id not in self.leaderboard or not self.leaderboard[chat_id]:
            await update.message.reply_text("📊 No data yet!")
            return
        
        stats_text = "📊 QUIZ STATISTICS\n"
        stats_text += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for subject, participants in self.leaderboard[chat_id].items():
            if subject in self.subjects:
                stats_text += f"📚 {subject.upper()}\n"
                stats_text += f"   👥 {len(participants)} participants\n"
                stats_text += f"   📝 {len(self.subjects[subject])} questions\n\n"
        
        await update.message.reply_text(stats_text)
    
    async def my_subjects_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle 'My Subjects' button"""
        if not self.subjects:
            await update.message.reply_text("📚 No subjects uploaded yet!")
            return
        
        text = "📚 YOUR SUBJECTS\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for subject, questions in self.subjects.items():
            text += f"📖 {subject.upper()}\n"
            text += f"   📝 {len(questions)} questions\n\n"
        
        await update.message.reply_text(text)
    
    async def my_groups_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle 'My Groups' button"""
        if not self.managed_groups:
            await update.message.reply_text(
                "👥 No groups yet!\n\n"
                "Add me to groups and make me admin."
            )
            return
        
        text = "👥 YOUR GROUPS\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for group_id in self.managed_groups:
            try:
                chat = await self.bot.get_chat(group_id)
                text += f"✅ {chat.title}\n"
                text += f"   ID: {group_id}\n\n"
            except:
                text += f"⚠️ Group {group_id} (Not accessible)\n\n"
        
        await update.message.reply_text(text)
    
    async def dashboard_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle 'Dashboard' button"""
        text = "📊 DASHBOARD\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        text += f"📚 Subjects: {len(self.subjects)}\n"
        text += f"👥 Groups: {len(self.managed_groups)}\n\n"
        
        total_participants = 0
        for group_data in self.leaderboard.values():
            for subject_data in group_data.values():
                total_participants += len(subject_data)
        
        text += f"👤 Total Participants: {total_participants}\n"
        
        await update.message.reply_text(text)
    
    async def handle_my_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Track when bot is added/removed from groups"""
        chat = update.my_chat_member.chat
        new_status = update.my_chat_member.new_chat_member.status
        
        if new_status in ["member", "administrator"]:
            self.managed_groups.add(chat.id)
            print(f"✅ Added to group: {chat.title} ({chat.id})")
        elif new_status in ["left", "kicked"]:
            self.managed_groups.discard(chat.id)
            print(f"❌ Removed from group: {chat.title} ({chat.id})")
    
    async def cancel_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel conversation"""
        keyboard = [
            ["📤 Upload Quiz", "📚 My Subjects"],
            ["👥 My Groups", "📊 Dashboard"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "❌ Cancelled.",
            reply_markup=reply_markup
        )
        return ConversationHandler.END


# Flask keep-alive for Render.com
from flask import Flask
import threading

app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "✅ Quiz Bot is Running!"

@app_flask.route('/health')
def health():
    return "OK"

def run_flask():
    app_flask.run(host='0.0.0.0', port=10000)

threading.Thread(target=run_flask, daemon=True).start()


async def post_init(application: Application):
    """Initialize bot"""
    print("=" * 50)
    print("  AUTOMATED TELEGRAM QUIZ BOT")
    print("=" * 50)
    print(f"\n✅ Bot started successfully!")
    print(f"👤 Admin ID: {ADMIN_USER_ID}")
    print(f"\n📱 Send me files in DM to create quizzes!")
    print(f"🤖 Press Ctrl+C to stop\n")


def main():
    """Main function"""
    application = Application.builder().token(BOT_TOKEN).build()
    bot = QuizBot(application)
    
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Document.TEXT & filters.ChatType.PRIVATE, bot.handle_file_upload)
        ],
        states={
            WAITING_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.receive_subject_name)],
            WAITING_GROUPS: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.receive_group_selection)],
        },
        fallbacks=[CommandHandler("cancel", bot.cancel_conversation)],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", bot.start_command))
    application.add_handler(CommandHandler("quiz", bot.quiz_command_group))
    application.add_handler(CommandHandler("leaderboard", bot.leaderboard_command_group))
    application.add_handler(CommandHandler("stats", bot.stats_command_group))
    application.add_handler(CallbackQueryHandler(bot.handle_quiz_callback, pattern="^start_quiz_"))
    application.add_handler(CallbackQueryHandler(bot.handle_leaderboard_callback, pattern="^leaderboard_"))
    application.add_handler(MessageHandler(
        filters.Regex("^📤 Upload Quiz$") & filters.ChatType.PRIVATE,
        lambda u, c: u.message.reply_text("📤 Send me a .txt file with questions!")
    ))
    application.add_handler(MessageHandler(
        filters.Regex("^📚 My Subjects$") & filters.ChatType.PRIVATE,
        bot.my_subjects_button
    ))
    application.add_handler(MessageHandler(
        filters.Regex("^👥 My Groups$") & filters.ChatType.PRIVATE,
        bot.my_groups_button
    ))
    application.add_handler(MessageHandler(
        filters.Regex("^📊 Dashboard$") & filters.ChatType.PRIVATE,
        bot.dashboard_button
    ))
    application.add_handler(PollAnswerHandler(bot.handle_poll_answer))
    application.add_handler(ChatMemberHandler(bot.handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    
    application.post_init = post_init
    
    print("\n🤖 Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()