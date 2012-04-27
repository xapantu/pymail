#! /usr/bin/env python2
# -*- coding: utf-8 -*-

from flask import Flask, render_template, session, request, redirect, url_for, jsonify
from email.parser import HeaderParser
from email.header import decode_header
import email
from email import utils as email_utils
import time
import sqlite3
import imaplib
from contextlib import closing
import re
import chardet
import datetime


app = Flask(__name__)


DATABASE = "db/main.sqlite"
DEBUG=True
SECRET_KEY="ah ah"
OFFLINE=False

app.config.from_object(__name__)

imap_accounts = {}

pat1 = re.compile(r"(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[#~!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)")
# skip mail adresses:
pat_emails = re.compile("( <([a-zA-Z.0-9@\-])+>)")
pat_f_emails = re.compile("( &lt;([a-zA-Z.0-9@\-])+&gt;)")


class EmailAccount(object):

    def __init__(self, host, name, password, database_name, mailboxes_synced):
        self.database_name = database_name
        self.mailboxes_synced = mailboxes_synced
        self.host = host
        self.name = name
        self.password = password
        self.open_db()
        self.load_imap_account()
        self.close_db()
    
    def load_imap_account(self):
        app.logger.debug("LOAD IMAP")
        mail = imaplib.IMAP4_SSL(self.host)
        mail.login(self.name, str(self.password))
        self.imap_mail = mail
        self.list_mailboxes()

    def list_mailboxes(self):
        status, mailboxes = self.imap_mail.list()
        self._mailboxes = []
        self._all_mailboxes = []
        self._unselected_mailboxes = []

        for mailbox in mailboxes:
            if "\\Noselect" in mailbox:
                continue
            mb = mailbox.split(" \"")[2].replace("\"", "")
            self._all_mailboxes.append((mb.replace("/", "%"), mb))
            if mb not in self.mailboxes_synced:
                self._unselected_mailboxes.append(mb)
            unread_count = 0 #self.get_unread_for_mailbox(mb)
            self._mailboxes.append((mb.replace("/", "%"), mb, unread_count))

        app.logger.debug("load imap accounts")

    def get_unread_for_mailbox(self, mailbox):
        cur = self.db.execute("select count(imapid) from mails " + self._get_where_no_mb() + " and mailbox = '" + mailbox + "' and seen = 0")
        return cur.fetchall()[0][0]

    def get_unselected_mailboxes(self):
        return self._unselected_mailboxes
    
    def get_all_mailboxes(self):
        return self._all_mailboxes

    def get_mailboxes(self):
        return self._mailboxes

    def open_db(self):
        self.db = sqlite3.connect(self.database_name)

    def close_db(self):
        self.db.close()
    
    def close_imap_account(self):
        mail.close()
        app.logger.debug("close imap")
        mail.logout()

    def load_mailbox(self, mailbox):
        mailbox = mailbox.replace("%", "/").replace("&amp;", "&").encode("utf-8")
        self.mailbox = mailbox
        try:
            self.imap_mail.select(mailbox) # connect to inbox.
        except imaplib.IMAP4.error: # maybe a timeout?
            self.load_imap_account()
            self.imap_mail.select(mailbox) # connect to inbox.

    def get_ns(self):
        return self.name + ":" + self.host

    def _get_order_by(self):
        return " order by date desc"

    """
    Open the DB, check what is the oldest message we have there, and download all the new ones.
    """
    def load_messages(self):
        cur = self.db.execute('select imapid from mails'
                             + self._get_where()
                             + ' order by imapid desc limit 1')
        
        last_imapid = 1
        last_entry = cur.fetchall()
        if len(last_entry) > 0: # if the database is empty, it can be 0
            last_imapid = last_entry[0][0] + 1
        else:
            app.logger.debug("Database empty")
        app.logger.debug("Fetch mails from: " + str(last_imapid))

        self.download_messages(last_imapid)

    """
    Put the content of the massage in the db if it is not already there, and returns it.
    """
    def _load_message_body(self, imapid):
        typ, data = self.imap_mail.uid("fetch", imapid, '(body.peek[])')
        msg = self._decode_full_proof(data[0][1], chardet.detect(data[0][1])["encoding"])
        self.db.executemany("update mails set fulltext = ? where imapid = %s" % (imapid), [(msg,)])
        self.db.commit()
        return msg

    def _format_message_from_db_row(self, entry):
        self.init_date()
        message = {}
        message["imapid"] = entry[0]
        message["fulltext"] = entry[1]
        message["encoding"] = entry[2]
        message["subject"] = entry[3]
        addr = email_utils.parseaddr(entry[4])
        message["sender"] = addr
        message["seen"] = entry[5]
        message["date"] = self.format_date(entry[6], True)
        message["mailbox"] = entry[7]

        encoding = "utf-8" # is this encoding stuff *really* necessary?
        if message["fulltext"] is not None: # yay, we even have the content!!
            if message["encoding"] is not None:
                encoding = message["encoding"]
        else:
            m = self.mailbox
            if message["mailbox"] != m:
                self.load_mailbox(message["mailbox"])
                message["fulltext"] = self._load_message_body(message["imapid"])
                self.load_mailbox(m)
            else:
                message["fulltext"] = self._load_message_body(message["imapid"])
        email_message = email.message_from_string(message["fulltext"].encode(encoding))
        content = self.get_content_from_message(email_message)[0]
        message["body"] = content
        return message

    """
    Return a dict with the message values (e.g. subject, sender, body...)
    """
    def load_message(self, imapid):
        cur = self.db.execute('select imapid, fulltext, encoding, subject, sender, seen, date, mailbox from mails'
                             + self._get_where()
                             + ' and imapid = ' + str(imapid))
        
        entry = cur.fetchall()
        if len(entry) is 0:
            self.download_messages(imapid)
            cur = self.db.execute('select imapid, fulltext, encoding, subject, sender, seen, date, mailbox from mails'
                                 + self._get_where()
                                 + ' and imapid = ' + str(imapid))
            
            entry = cur.fetchall()
            if len(entry) is 0:
                raise

        return self._format_message_from_db_row(entry[0])
   
    def update_flags(self, count):
        cur = self.db.execute('select imapid, seen, thrid from mails'
                             + self._get_where()
                             + ' order by imapid desc limit ' + str(count))
        entries = [dict(imapid=row[0], seen=row[1], thrid=row[2]) for row in cur.fetchall()]
        

        if len(entries) > 0:
            app.logger.debug("from %s to %s" % (entries[-1]["imapid"], entries[0]["imapid"]))
            typ, data = self.imap_mail.uid("fetch", str(entries[-1]["imapid"]) + ":" + str(entries[0]["imapid"]),
                                 '(flags)')
            mails_id = {}
            for entry in entries:
                mails_id[entry["imapid"]] = entry

            thrids_to_update = []
            for msg in data:
                mailid = int(msg.split()[2])
                old_seen = mails_id[mailid]["seen"]
                seen = "\\Seen" in imaplib.ParseFlags(msg)
                if old_seen is not int(seen):
                    self.db.execute("update mails set seen = " + str(int(seen)) + " where imapid = %s" % (mailid))
                    if not(mails_id[mailid]["thrid"] in thrids_to_update): thrids_to_update.append(mails_id[mailid]["thrid"])

            for thrid in thrids_to_update:
                cur = self.db.execute('select seen from mails'
                                     + self._get_where()
                                     + ' and thrid = ' + str(thrid))
                seen = True
                for entry in cur.fetchall():
                    if not entry[0]:
                        seen = False
                        break
                self.db.execute("update threads set seen = " + str(int(seen)) + " where imapid = %s" % (thrid))
            
            self.db.commit()
        else:
            app.logger.debug("No mail for this mailbox.")

    def load_thread(self, imapid):
        cur = self.db.execute('select imapid, fulltext, encoding, subject, sender, seen, date, mailbox from mails'
                             + self._get_where_no_mb()
                             + ' and thrid = ' + str(imapid)
                             + ' order by date')
        
        entries = cur.fetchall()
        messages = []
        subject = ""
        need_seen_updated = False
        for entry in entries:
            if subject is "":
                subject = entry[3]
            messages.append(self._format_message_from_db_row(entry))
            if entry[5] == 0:
                mb = self.mailbox
                self.load_mailbox(entry[7])
                self.imap_mail.uid("store", entry[0], "+FLAGS", "(\\Seen)")
                self.db.execute('update mails set seen = 1 ' + self._get_where() + ' and imapid = ' + str(entry[0]))
                need_seen_updated = True
                app.logger.debug("need up_")
                self.load_mailbox(mb)

        self.db.commit()
        if need_seen_updated:
            app.logger.debug("need up")
            count = self.db.execute('select count() from mails' + self._get_where_no_mb() + ' and thrid = ' + str(imapid) + ' and seen = 0').fetchall()[0][0]
            app.logger.debug(count)
            if count == 0: # then update the whole thread
                app.logger.debug("need modification")
                self.db.execute('update threads set seen = 1 ' + self._get_where_no_mb() + ' and imapid = ' + str(imapid))
        self.db.commit()
                
        return messages, subject

    def download_messages(self, start):
        typ, data = self.imap_mail.uid("fetch", str(start) + ":*",
                             '(body.peek[header.fields (subject message-id from to date)] x-gm-thrid flags)')
        app.logger.debug("Fetch from %s to *" % (start))
        i = 0
        final = "/" + str(len(data))
        threads_date = {}
        threads_seen = {}
        for msg in data:
            if msg is None or msg[0] == ")" or "UID" not in msg[0]:
                continue
            email = {}

            # Parse the email values:
            values_split = msg[0].replace("(", "").split()
            uid_index = values_split.index("UID")
            thrid_index = values_split.index("X-GM-THRID")
            message_id = values_split[uid_index+1]
            thrid = values_split[thrid_index+1]

            if int(message_id) < start:
                continue

            # Parse the flags
            seen = "\\Seen" in imaplib.ParseFlags(msg[0])
            email["seen"] = seen

            parser = HeaderParser()
            header = parser.parsestr(msg[1])

            decoded = decode_header(header["subject"])
            subject = ""
            for decod in decoded:
                if subject != "":
                    subject += " "
                subject += self._decode_full_proof(decod[0], decod[1])

            email["imapid"] = message_id
            email["subject"] = subject
            senders  = decode_header(header["from"])
            email["sender"] = ""
            for sender in senders:
                if email["sender"] != "":
                    email["sender"] += " "
                email["sender"] += self._decode_full_proof(sender[0], sender[1])
            decoded = decode_header(header["to"])[0]
            to = self._decode_full_proof(decoded[0], decoded[1])
            decoded = decode_header(header["date"])[0]
            date = date = self._decode_full_proof(decoded[0], decoded[1])
            date = time.strftime("%Y-%m-%d %H:%M:%S", email_utils.parsedate(date))

            self.db.execute('insert into mails (subject, account, imapid, seen, sender, thrid, receiver, date, mailbox)'
                          + ' values (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                             [email["subject"], self.get_ns (), email["imapid"], seen, email["sender"], thrid, to, date, self.mailbox])
            i += 1
            if i > 500:
                self.db.commit()
                app.logger.debug(str(message_id) + final)
                i = 0
            cur = self.db.execute('select seen, mailbox, sender from threads'
                                + self._get_where_no_mb()
                                + ' and imapid = ' + str(thrid)
                                + ' limit 1')
            thread_db = cur.fetchall()
            if len(thread_db) is 0:
                # We need to add a new thread
                self.db.execute('insert into threads (subject, imapid, account, seen, mailbox, date, sender)'
                              + ' values (?, ?, ?, ?, ?, ?, ?)',
                                [email["subject"], thrid, self.get_ns(), seen, self.mailbox, date, email["sender"]])
            else:
                old_seen = thread_db[0][0]
                index = str(thrid)
                senders = thread_db[0][2]
                if threads_date.has_key(index):
                    old_seen = threads_date[index][1]
                    senders = threads_date[index][4]
                new_mb = thread_db[0][1]
                if email["sender"] not in senders:
                    senders += ", " + email["sender"]
                if self.mailbox not in new_mb:
                    new_mb += "," + self.mailbox
                threads_date[index] = (date, min(old_seen, int(email["seen"])), new_mb, thrid, senders)
        self.db.commit()
        for th_date in threads_date.values():
            senders = th_date[4]
            self.db.execute('update threads set date = \'' + th_date[0] + "', seen = " + str(th_date[1])
                          + ', mailbox = \'' + th_date[2] +  '\', sender = ? '
                              + self._get_where_no_mb() + " and imapid = " + str(th_date[3]), (senders,))
        self.db.commit()
    
    def _get_where_no_mb(self):
        return ' where account = \'' + self.get_ns() + '\''


    def _get_where(self):
        return ' where account = \'' + self.get_ns() + '\'' + ' and mailbox like \'%' + self.mailbox + '%\''

    
    """
    Return a list with all message from start to end.
    0 is the last email
    100 is the 100th most recent email
    """
    def load_list(self, start, end):
        cur = self.db.execute('select imapid, subject, sender, seen from mails'
                             + self._get_where()
                             + ' order by imapid desc limit %s,%s' % (start, end))
        entries = [dict(imapid=row[0], subject=row[1], sender=row[2], seen=row[3]) for row in cur.fetchall()]
        return entries
    
    def init_date(self):
        self._today = time.strftime("%a, %d %b %Y")
        dt = datetime.timedelta(days=1)
        self._yesterday = time.strftime("%a, %d %b %Y", (datetime.datetime.today() - dt).timetuple())

    def format_date(self, row, full = False):
        th_time = time.strptime(row, "%Y-%m-%d %H:%M:%S")
        time_format = time.strftime("%a, %d %b %Y", th_time)
        if time_format == self._today:
            time_format = time.strftime("%H:%M", th_time)
        elif time_format == self._yesterday:
            time_format = time.strftime("hier" + ", %H:%M", th_time)
        elif full:
            time_format = time.strftime("%a, %d %b %Y %H:%M", th_time)
        return time_format
    
    def parse_emails(self, row):
        content = ""
        for mail in row.split(", "):
            name = email_utils.parseaddr(mail)
            if content != "":
                content += ", "
            if name[0] != "":
                content += name[0]
            else:
                content += name[1]
        return content
    """
    Return a list with all threads from start to end.
    """
    def load_threads(self, start, end):
        self.init_date()
        cur = self.db.execute('select imapid, subject, seen, sender, date from threads'
                             + self._get_where()
                             + self._get_order_by()
                             + ' limit %s,%s' % (start, end))
        entries = [dict(imapid=row[0], subject=row[1], seen=row[2], sender=self.parse_emails(row[3]), date=self.format_date(row[4]) ) for row in cur.fetchall()]
        return entries

    def get_content_from_message(self, message_instance):
        content = ""
        maintype = message_instance.get_content_type()
        encoding = message_instance.get_content_charset("utf-8")
        if maintype in ("multipart/mixed", "multipart/signed"):
            for part in message_instance.get_payload():
                content += self.get_content_from_message(part)[0]
        elif maintype == "multipart/alternative": #arg :(
            new_content = ""
            for part in message_instance.get_payload():
                new_content = self.get_content_from_message(part)
                if new_content[1] == "text/html":
                    break
            content += new_content[0]
        elif maintype == "text/plain":
            data = message_instance.get_payload(decode=True)
            content += pat1.sub(r'<a href="\1" target="_blank">\1</a>', self._decode_full_proof(data, encoding).replace("\n", "<br />"))
        elif maintype == "text/html":
            data = message_instance.get_payload(decode=True)
            content += data.decode(encoding)
        return content, maintype

    def _decode_full_proof(self, text, encoding):
        if encoding == None: encoding = "utf-8"
        try:
            text = text.decode(encoding)
        except UnicodeDecodeError:
            try:
                text = text.decode(chardet.detect(text)["encoding"])
            except UnicodeDecodeError:
                try:
                    text = text.decode("utf-8")
                except UnicodeDecodeError:
                    text = unicode(text, errors_ignore)
        return text

    def sync_all(self):
        for mb in self.mailboxes_synced:
            self.load_mailbox(mb)
            self.load_messages()
            self.update_flags(500)


def connect_db():
    return sqlite3.connect(app.config['DATABASE'])

def init_db():
    with closing(connect_db()) as db:
        with app.open_resource('main.sql') as f:
            db.cursor().executescript(f.read())
        db.commit()
    
    with closing(sqlite3.connect("db/email.db")) as db:
        with app.open_resource('schema.sql') as f:
            db.cursor().executescript(f.read())
        db.commit()

@app.route("/ajax/thread/<int:account>/<mailbox>/<imapid>")
def view_full_thread(account, mailbox, imapid):
    mail = get_mail_instance(account)
    mail.open_db()
    mail.load_mailbox(mailbox)
    messages = mail.load_thread(imapid)
    mail.close_db()
    hide_first_mails = len(messages[0]) > 4
    return jsonify(message=render_template("email/email-thread.html", thread=messages[0], subject=messages[1], hide_first_mails=hide_first_mails))

@app.route("/settings/account/<int:account>/")
def settings_account(account):
    mail = get_mail_instance(account)
    all_mb = mail.get_all_mailboxes()
    unselected_mb = mail.get_unselected_mailboxes()
    content = render_template("email/email-ajax-settings.html", account=account, name=mail.name, host=mail.host, all_mailboxes=all_mb, unselected_mailboxes=unselected_mb)
    return jsonify(content=content, title="Settings of %s (%s)" % (mail.name, mail.host))

@app.route("/mails/<int:account>/<mailbox>/<int:imapid>")
def view_mail(account, imapid):
    return jsonify(message=view_mail_raw(account, imapid, mailbox))

def remove_empty_elements(array):
    next_array = []
    for a in array:
        if a != "":
            next_array.append(a)
    return next_array

def get_mail_instance(account):
    if not email_accounts.has_key(account):
        # Get the password, etc...
        db = sqlite3.connect(app.config["DATABASE"])
        cur = db.execute("select  email, password, host, mailboxes_synced from imapaccounts where id = " + str(account))
        data = cur.fetchall()
        email_accounts[account] = EmailAccount(data[0][2], data[0][0], data[0][1], "db/email.db", remove_empty_elements(data[0][3].split(";")))
        db.close()

    mail = email_accounts[account]
    return mail

def view_mail_raw(account, imapid, mailbox = "INBOX"):
    mail = get_mail_instance(account)
    mail.open_db()
    mail.load_mailbox(mailbox)
    message = mail.load_message(imapid)
    mail.close_db()
    return render_template("email/email-message.html", message=message, even=False)


IMAP_ACCOUNTS = []
def update_imap_accounts_list(db):
    global IMAP_ACCOUNTS
    cur = db.execute("select id, email, host from imapaccounts")
    IMAP_ACCOUNTS = [dict(id=row[0], name=row[1], host=row[2]) for row in cur.fetchall()]


@app.route("/", methods=["GET", "POST"])
def start():
    db = sqlite3.connect(app.config["DATABASE"])
    if request.form.has_key("email"):
        db.execute("insert into imapaccounts (email, password, host, mailboxes_synced) values (?, ?, ?, ';INBOX;')",
                [request.form["email"], request.form["password"], request.form["host"]])
        db.commit()
        update_imap_accounts_list(db)
    db.close()
    return render_template("email/email-home.html", accounts=IMAP_ACCOUNTS, page_class="email-home")

@app.route("/ajax/threadslist/<int:account>/<mailbox>/<int:page>")
def view_thread_list(account, mailbox, page):
    # Several case:
    #   - not logged but he sent the authentification things
    #   - the user is not logged
    #   - logged


    app.logger.debug(mailbox)
    
    mail = get_mail_instance(account)
    mail.open_db()
    mail.load_mailbox(mailbox)
    
    mails_id = mail.load_threads(page*100, 100)
    mail.close_db()
    
    return jsonify(thread_list=render_template('email/email-ajax-threads-list.html',
                                    emails=mails_id,
                                    mailbox=mailbox,
                                    mailboxes=mail.get_mailboxes())
                  )

@app.route("/ajax/settings/<int:account>/<key>/<value>")
def set_settings(account, key, value):
    keys = key.split(";")
    db = sqlite3.connect(app.config["DATABASE"])
    mail = get_mail_instance(account)
    if keys[0] == "mailbox":
        mailbox = keys[1].replace("%", "/")
        if mailbox is not "" and (value == "1" or value == "0"):
            # Get the current synced mailboxes
            cur = db.execute("select  mailboxes_synced from imapaccounts where id = " + str(account))
            data = cur.fetchall()
            mailboxes_synced = data[0][0]
            if value == "1":
                mailboxes_synced = mailboxes_synced + mailbox + ";"
            else:
                mailboxes_synced = mailboxes_synced.replace(mailbox + ";", "")
            mail.mailboxes_synced = remove_empty_elements(mailboxes_synced.split(";"))
            mail.list_mailboxes()
            db.execute("update imapaccounts set mailboxes_synced = '" + mailboxes_synced + "' where id = " + str(account))
    db.commit()
    db.close()
    return ""

@app.route("/threads/<int:account>/<mailbox>/<int:page>")
def view_thread(account, mailbox, page):
    # Several case:
    #   - not logged but he sent the authentification things
    #   - the user is not logged
    #   - logged


    mail = get_mail_instance(account)
    mail.open_db()
    mail.load_mailbox(mailbox)
    
    mails_id = mail.load_threads(page*100, 100)
    mail.close_db()
    
    return render_template('email/email.html',
            account=account,
            accountname=mail.name,
            page_next="/threads/" + mailbox + "/" + str(int(page) + 1),
            page_back="/threads/" + mailbox + "/" + str(int(page) - 1),
            page=page,
            emails=mails_id,
            mailbox=mailbox,
            accounts=IMAP_ACCOUNTS,
            page_class="email",
            mailboxes=mail.mailboxes_synced)

@app.route("/sync/<int:account>/")
def sync_full(account):
    mail = get_mail_instance(account)
    mail.open_db()
    mail.sync_all()
    mail.close_db()
    return jsonify(success=True)

@app.route("/widgets")
def widgets():
    return render_template("email/widgets.html")
@app.route("/sync/<int:account>/<mailbox>")
def sync(account, mailbox):
    mail = get_mail_instance(account)
    mail.open_db()
    mail.load_mailbox(mailbox)
    mail.load_messages()
    mail.update_flags(100)
    mail.close_db()
    return jsonify(success=True)

@app.route("/box/<int:account>/<mailbox>/<int:page>", methods=["GET", "POST"])
def root(account, mailbox, page):
    # Several case:
    #   - not logged but he sent the authentification things
    #   - the user is not logged
    #   - logged

    mail = get_mail_instance(account)
    mail.open_db()
    mail.load_mailbox(mailbox)
    mails_id = mail.load_list(page * 100, (page + 1) * 100)
    mail.close_db()
    emails_list = sorted(mails_id, lambda x, y: cmp(int(y["imapid"]), int(x["imapid"])))
    return render_template('email/email-list.html', page=0, emails=emails_list, mailbox=mailbox)

email_accounts = {}

if __name__ == "__main__":
    app.debug = True
    db = sqlite3.connect(app.config["DATABASE"])
    update_imap_accounts_list(db)
    db.close()
    app.run()
