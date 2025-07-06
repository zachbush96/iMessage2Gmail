#!/usr/bin/env python3
"""
====================================================================
 iMessage ⇄ Gmail Bridge with Test Harness
====================================================================
"""
from __future__ import annotations
import os, sys, time, json, uuid, sqlite3, imaplib, smtplib, signal, logging
from datetime import datetime, date, time as dtime, timedelta
from email.mime.text import MIMEText
from email.header import Header
import email
import subprocess
import argparse
from typing import Dict, Tuple, List

# ────────────────  CONFIG  ────────────────
GMAIL_USER   = "zachbush96@gmail.com"
GMAIL_PASS   = "<APP_PASSWORD_HERE>"
SMTP_SERVER  = "smtp.gmail.com"; SMTP_PORT = 587
IMAP_SERVER  = "imap.gmail.com"; IMAP_PORT = 993
POLL_SECONDS = 30

SCHEDULE: List[Tuple[int,str,str]] = [
    (2, "19:00", "07:30"),
    (3, "19:00", "07:30"),
    (6, "07:00", "19:30"),
]

CHAT_DB = os.path.expanduser("~/Library/Messages/chat.db")
STATE_FILE = os.path.expanduser("~/.imessage_gmail_state.json")

# ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class Bridge:
    def __init__(self):
        self.last_rowid: int = 0
        self.pending: Dict[str, Dict] = {}
        self.paused: bool = False
        self.command_handlers = {
            "!status": self.cmd_status,
            "!pause": self.cmd_pause,
            "!resume": self.cmd_resume,
            "!stop": self.cmd_stop,
        }
        self.load_state()
        signal.signal(signal.SIGINT, self.save_and_exit)
        signal.signal(signal.SIGTERM, self.save_and_exit)

    def in_window(self, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        wd = now.weekday()
        for w, start_s, end_s in SCHEDULE:
            if wd != w: continue
            start_t = dtime.fromisoformat(start_s)
            end_t   = dtime.fromisoformat(end_s)
            start_dt = datetime.combine(now.date(), start_t)
            end_dt   = datetime.combine(now.date(), end_t)
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
            return start_dt <= now <= end_dt
        return False

    def load_state(self):
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            self.last_rowid = data.get("last_rowid", 0)
            logger.debug(f"Loaded state, last_rowid={self.last_rowid}")
        except FileNotFoundError:
            self.last_rowid = 0
            logger.debug("State file not found, starting fresh")

    def save_state(self):
        with open(STATE_FILE, "w") as f:
            json.dump({"last_rowid": self.last_rowid}, f)
        logger.debug(f"Saved state, last_rowid={self.last_rowid}")

    def save_and_exit(self, *_):
        self.save_state()
        sys.exit(0)

    def get_new_messages(self) -> List[Tuple[int,str,str]]:
        conn = sqlite3.connect(f"file:{CHAT_DB}?mode=ro&nolock=1", uri=True)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.rowid, h.id, m.text
            FROM message m
            JOIN handle h ON m.handle_id = h.rowid
            WHERE m.rowid > ? AND m.is_from_me = 0
            ORDER BY m.rowid ASC
            """, (self.last_rowid,)
        )
        rows = cur.fetchall()
        conn.close()
        logger.debug(f"Found {len(rows)} new messages")
        return rows

    def smtp_send(self, subject: str, body: str, recipient: str):
        logger.debug(f"Sending email subj={subject}")
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = GMAIL_USER
        msg["To"] = recipient
        msg["Subject"] = Header(subject, "utf-8")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASS)
            server.send_message(msg)

    def imap_search_subject(self, mailbox, subj_token: str):
        result, data = mailbox.search(None, f'(UNSEEN SUBJECT "{subj_token}")')
        return data[0].split() if result == "OK" else []

    def check_commands(self, mailbox=None):
        own = False
        if mailbox is None:
            mailbox = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            mailbox.login(GMAIL_USER, GMAIL_PASS)
            own = True
        mailbox.select("INBOX")
        for cmd, handler in self.command_handlers.items():
            ids = self.imap_search_subject(mailbox, cmd)
            if ids:
                mailbox.fetch(ids[-1], '(RFC822)')
                mailbox.store(ids[-1], '+FLAGS', '\\Seen')
                logger.info(f"Processing command {cmd}")
                handler()
                break
        if own:
            mailbox.logout()

    def poll_for_reply(self, token: str) -> str | None:
        with imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT) as box:
            box.login(GMAIL_USER, GMAIL_PASS)
            while True:
                box.select("INBOX")
                ids = self.imap_search_subject(box, token)
                if ids:
                    res, msg_data = box.fetch(ids[-1], '(RFC822)')
                    msg = email.message_from_bytes(msg_data[0][1])
                    body = self._extract_body(msg).strip()
                    box.store(ids[-1], '+FLAGS', '\\Seen')
                    logger.debug(f"Received reply for {token}")
                    return body
                # also check for command emails while waiting
                try:
                    self.check_commands(box)
                except Exception as e:
                    logger.error(f"Command check error: {e}")
                time.sleep(POLL_SECONDS)

    @staticmethod
    def _extract_body(msg):
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain' and not part.get_content_disposition():
                    return part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8')
        else:
            return msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8')
        return ""

    def send_imessage(self, handle: str, text: str):
        logger.debug(f"Sending iMessage to {handle}")
        script = f'''on run argv\n    set theBuddy to item 1 of argv\n    set theMessage to item 2 of argv\n    tell application "Messages"\n        set targetService to 1st service whose service type = iMessage\n        set targetBuddy to buddy theBuddy of targetService\n        send theMessage to targetBuddy\n    end tell\nend run'''
        subprocess.run(["osascript", "-e", script, handle, text], check=True)

    # ──────────────── COMMANDS ────────────────
    def cmd_status(self):
        status = "paused" if self.paused else "running"
        body = f"Bridge is currently {status}. Pending messages: {len(self.pending)}"
        self.smtp_send("Bridge Status", body, GMAIL_USER)

    def cmd_pause(self):
        self.paused = True
        self.smtp_send("Bridge Paused", "Forwarding has been paused", GMAIL_USER)

    def cmd_resume(self):
        self.paused = False
        self.smtp_send("Bridge Resumed", "Forwarding has been resumed", GMAIL_USER)

    def cmd_stop(self):
        self.smtp_send("Bridge Stopping", "Bridge is stopping", GMAIL_USER)
        self.save_and_exit()

    def run(self):
        logger.info("Bridge started")
        while True:
            if not self.in_window():
                time.sleep(60)
                continue

            if not self.pending:
                try:
                    self.check_commands()
                except Exception as e:
                    logger.error(f"Command check error: {e}")

            if self.paused:
                time.sleep(5)
                continue

            for rowid, handle, text in self.get_new_messages():
                token = f"MSGID:{rowid}"
                subj = f"[{token}] {handle}"
                body = f"Incoming from {handle}\n\n{text}"
                try:
                    self.smtp_send(subj, body, GMAIL_USER)
                except Exception as e:
                    logger.error(f"SMTP error: {e}")
                    continue
                self.pending[token] = {"rowid": rowid, "handle": handle}
                self.last_rowid = max(self.last_rowid, rowid)
                self.save_state()

            for token, meta in list(self.pending.items()):
                reply = None
                try:
                    reply = self.poll_for_reply(token)
                except Exception as e:
                    logger.error(f"IMAP error: {e}")
                if reply:
                    try:
                        self.send_imessage(meta['handle'], reply)
                    except Exception as e:
                        logger.error(f"iMessage send error: {e}")
                    del self.pending[token]
            time.sleep(5)

# ───────────────────────────────────────────────────────────────────

def run_tests():
    import unittest, tempfile, shutil, types

    class TestBridge(unittest.TestCase):
        def setUp(self):
            # create temp db and state file
            self.tmpdir = tempfile.mkdtemp()
            global CHAT_DB, STATE_FILE
            self.orig_db = CHAT_DB
            self.orig_state = STATE_FILE
            # override paths
            Bridge.CHAT_DB = os.path.join(self.tmpdir, 'chat.db')
            CHAT_DB = Bridge.CHAT_DB
            STATE_FILE = os.path.join(self.tmpdir, 'state.json')
            # init sqlite schema
            conn = sqlite3.connect(CHAT_DB)
            cur = conn.cursor()
            cur.execute('CREATE TABLE handle (rowid INTEGER PRIMARY KEY, id TEXT)')
            cur.execute('CREATE TABLE message (rowid INTEGER PRIMARY KEY, handle_id INTEGER, text TEXT, is_from_me INTEGER)')
            cur.execute('INSERT INTO handle VALUES (1, "+1234567890")')
            cur.execute('INSERT INTO message VALUES (1,1,"Test",0)')
            conn.commit(); conn.close()
            # patch smtp_send and send_imessage
            self.sent_emails = []
            self.sent_msgs = []
            Bridge.smtp_send = lambda self,sbj,bd,rcp,test=self: test.sent_emails.append((sbj,bd,rcp))
            Bridge.send_imessage = lambda self,h,text,test=self: test.sent_msgs.append((h,text))
            # patch poll_for_reply to immediately return a canned reply
            Bridge.poll_for_reply = lambda self,token: "Reply body"
            # run only a single iteration
            def run_once(self):
                for rowid, handle, text in self.get_new_messages():
                    token = f"MSGID:{rowid}"
                    subj = f"[{token}] {handle}"
                    body = f"Incoming from {handle}\n\n{text}"
                    self.smtp_send(subj, body, GMAIL_USER)
                    reply = self.poll_for_reply(token)
                    if reply:
                        self.send_imessage(handle, reply)
                return
            self.orig_run = Bridge.run
            Bridge.run = run_once

        def tearDown(self):
            shutil.rmtree(self.tmpdir)
            Bridge.run = self.orig_run

        def test_forward_and_reply(self):
            b = Bridge()
            # single run iteration
            new = b.get_new_messages()
            self.assertEqual(len(new), 1)
            b.run()  # will forward and immediately reply
            # assert email sent and message replied
            self.assertTrue(self.sent_emails)
            self.assertTrue(self.sent_msgs)

    suite = unittest.TestLoader().loadTestsFromTestCase(TestBridge)
    unittest.TextTestRunner(verbosity=2).run(suite)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run tests")
    args = parser.parse_args()
    if args.test:
        run_tests()
    else:
        Bridge().run()
