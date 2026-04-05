"""
Telegram Bot for Job Application Approval
Human-in-the-loop workflow: approve/reject each application via inline buttons.
"""

import os
import asyncio
from typing import Callable, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

load_dotenv()


class ApprovalBot:
    """
    Telegram bot for human-in-the-loop job application approval.
    
    Flow:
    1. Agent finds job, generates cover letter
    2. Bot sends job details + cover letter to you
    3. You tap Approve/Reject/Edit
    4. Agent proceeds based on your choice
    """
    
    def __init__(
        self,
        token: str = None,
        chat_id: str = None,
        on_approve: Callable = None,
        on_reject: Callable = None,
        on_edit: Callable = None
    ):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")
        if not self.chat_id:
            raise ValueError("TELEGRAM_CHAT_ID not set")
        
        # Callbacks for approval actions
        self.on_approve = on_approve
        self.on_reject = on_reject
        self.on_edit = on_edit
        
        # Pending approvals: job_id -> job_data
        self.pending: Dict[int, Dict] = {}
        
        # Build application
        self.app = Application.builder().token(self.token).build()
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup command and callback handlers"""
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("stats", self.cmd_stats))
        self.app.add_handler(CommandHandler("pending", self.cmd_pending))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "🤖 *Job Hunter Bot Active*\n\n"
            "I'll send you jobs for approval before applying.\n\n"
            "Commands:\n"
            "/status - Check bot status\n"
            "/stats - Application statistics\n"
            "/pending - View pending approvals",
            parse_mode="Markdown"
        )
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        pending_count = len(self.pending)
        await update.message.reply_text(
            f"✅ Bot is running\n"
            f"📋 Pending approvals: {pending_count}"
        )
    
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command - placeholder for DB integration"""
        await update.message.reply_text(
            "📊 Stats coming soon...\n"
            "(Will show application counts, response rates, etc.)"
        )
    
    async def cmd_pending(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show all pending approvals"""
        if not self.pending:
            await update.message.reply_text("No pending approvals.")
            return
        
        for job_id, job in self.pending.items():
            await self._send_approval_request(job, resend=True)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
        # Parse callback data: action_jobid
        data = query.data
        parts = data.split("_")
        
        if len(parts) < 2:
            return
        
        action = parts[0]
        job_id = int(parts[1])
        
        if job_id not in self.pending:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("⚠️ This job is no longer pending.")
            return
        
        job = self.pending[job_id]
        
        if action == "approve":
            await self._handle_approve(query, job_id, job)
        elif action == "reject":
            await self._handle_reject(query, job_id, job)
        elif action == "edit":
            await self._handle_edit(query, job_id, job)
        elif action == "view":
            await self._handle_view_cover(query, job_id, job)
    
    async def _handle_approve(self, query, job_id: int, job: Dict):
        """Process approval"""
        del self.pending[job_id]
        
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"✅ *Approved*: {job['title']} @ {job['company']}\n"
            "Submitting application...",
            parse_mode="Markdown"
        )
        
        if self.on_approve:
            await self.on_approve(job_id, job)
    
    async def _handle_reject(self, query, job_id: int, job: Dict):
        """Process rejection"""
        del self.pending[job_id]
        
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"❌ *Rejected*: {job['title']} @ {job['company']}",
            parse_mode="Markdown"
        )
        
        if self.on_reject:
            await self.on_reject(job_id, job)
    
    async def _handle_edit(self, query, job_id: int, job: Dict):
        """Request cover letter edit"""
        await query.message.reply_text(
            "✏️ Send your edited cover letter as a reply.\n"
            "(Feature coming soon - for now, approve or reject)"
        )
        
        if self.on_edit:
            await self.on_edit(job_id, job)
    
    async def _handle_view_cover(self, query, job_id: int, job: Dict):
        """Show full cover letter"""
        cover = job.get("cover_letter", "No cover letter generated")
        
        # Split if too long
        if len(cover) > 4000:
            cover = cover[:4000] + "...(truncated)"
        
        await query.message.reply_text(
            f"📝 *Cover Letter*\n\n{cover}",
            parse_mode="Markdown"
        )
    
    def _format_job_message(self, job: Dict) -> str:
        """Format job details for Telegram message"""
        score = job.get("score", 0)
        score_emoji = "🟢" if score >= 0.8 else "🟡" if score >= 0.6 else "🔴"
        
        msg = (
            f"🎯 *New Job Match*\n\n"
            f"*{job.get('title', 'Unknown Title')}*\n"
            f"🏢 {job.get('company', 'Unknown Company')}\n"
            f"📍 {job.get('location', 'Unknown Location')}\n"
            f"{score_emoji} Score: {score:.0%}\n"
        )
        
        if job.get("salary_min") or job.get("salary_max"):
            salary = ""
            if job.get("salary_min"):
                salary += f"€{job['salary_min']:,}"
            if job.get("salary_max"):
                salary += f" - €{job['salary_max']:,}"
            msg += f"💰 {salary}\n"
        
        if job.get("url"):
            msg += f"\n🔗 [View Job]({job['url']})\n"
        
        # Truncated description
        desc = job.get("description", "")[:500]
        if desc:
            msg += f"\n📄 _{desc}..._"
        
        return msg
    
    def _get_approval_keyboard(self, job_id: int) -> InlineKeyboardMarkup:
        """Create inline keyboard for approval"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{job_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{job_id}")
            ],
            [
                InlineKeyboardButton("📝 View Cover Letter", callback_data=f"view_{job_id}"),
                InlineKeyboardButton("✏️ Edit", callback_data=f"edit_{job_id}")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    async def _send_approval_request(self, job: Dict, resend: bool = False):
        """Send job approval request to Telegram"""
        job_id = job.get("id") or job.get("job_id")
        
        message = self._format_job_message(job)
        keyboard = self._get_approval_keyboard(job_id)
        
        await self.app.bot.send_message(
            chat_id=self.chat_id,
            text=message,
            reply_markup=keyboard,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    
    async def request_approval(self, job: Dict) -> None:
        """
        Queue a job for approval.
        
        Args:
            job: Job dict with id, title, company, description, score, cover_letter
        """
        job_id = job.get("id") or job.get("job_id")
        self.pending[job_id] = job
        await self._send_approval_request(job)
    
    async def send_notification(self, message: str):
        """Send a simple notification message"""
        await self.app.bot.send_message(
            chat_id=self.chat_id,
            text=message,
            parse_mode="Markdown"
        )
    
    def run(self):
        """Start the bot (blocking)"""
        print(f"Starting Telegram bot...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)
    
    async def start_async(self):
        """Start the bot asynchronously"""
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    async def stop_async(self):
        """Stop the bot"""
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()


# Standalone test
if __name__ == "__main__":
    async def on_approve(job_id, job):
        print(f"APPROVED: {job['title']} @ {job['company']}")
    
    async def on_reject(job_id, job):
        print(f"REJECTED: {job['title']} @ {job['company']}")
    
    bot = ApprovalBot(on_approve=on_approve, on_reject=on_reject)
    
    # Test sending a job
    async def test():
        await bot.start_async()
        await bot.request_approval({
            "id": 1,
            "title": "AI Research Engineer",
            "company": "ESET",
            "location": "Bratislava, Slovakia",
            "score": 0.87,
            "description": "We're looking for an AI Research Engineer to work on malware detection...",
            "url": "https://example.com/job/1",
            "cover_letter": "Dear Hiring Manager,\n\nI am excited to apply..."
        })
        # Keep running
        await asyncio.Event().wait()
    
    asyncio.run(test())
