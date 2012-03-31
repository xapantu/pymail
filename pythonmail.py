#! /usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Flask, render_template, session, request, redirect, url_for, jsonify
from email.parser import HeaderParser
from email.header import decode_header
import email
from time import strftime
import sqlite3
import imaplib
from contextlib import closing
import chardet


app = Flask(__name__)


DATABASE = "email.db"
DEBUG=True
SECRET_KEY="ah ah"
OFFLINE=False

app.config.from_object(__name__)

imap_accounts = {}

class EmailAccount(object):

    def __init__(self, host, name, password, database_name):
        self.host = host
        self.name = name
        self.password = password
        self.database_name = database_name
        self.load_imap_account()
    
    def load_imap_account(self):
        mail = imaplib.IMAP4_SSL(self.host)
        mail.login(self.name, self.password)
        mail.list()
        app.logger.debug("load imap accounts")
        self.imap_mail = mail

    def open_db(self):
        self.db = sqlite3.connect(self.database_name)

    def close_db(self):
        self.db.close()
    
    def close_imap_account(self):
        mail.close()
        app.logger.debug("close imap")
        mail.logout()

    def load_mailbox(self, mailbox):
        self.mailbox = mailbox
        try:
            self.imap_mail.select(mailbox) # connect to inbox.
        except imaplib.abort: # maybe a timeout?
            self.load_imap_account()
            self.imap_mail.select(mailbox) # connect to inbox.

    def get_ns(self):
        return self.name + ":" + self.host

    """
    Open the DB, check what is the oldest message we have there, and download all the new ones.
    """
    def load_messages(self):
        cur = self.db.execute('select imapid from mails'
                             + ' where account = \'' + self.get_ns() + '\''
                             + self._get_where()
                             + ' and mailbox = \'' + self.malibox + '\''
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
        msg = data[0][1].decode(chardet.detect(data[0][1])["encoding"])
        self.db.executemany("update mails set fulltext = ? where imapid = %s" % (imapid), [(msg,)])
        self.db.commit()
        return msg

    def _format_message_from_db_row(self, entry):
        message = {}
        message["imapid"] = entry[0]
        message["fulltext"] = entry[1]
        message["encoding"] = entry[2]
        message["subject"] = entry[3]
        message["sender"] = entry[4]
        message["seen"] = entry[5]
        message["date"] = entry[6]

        encoding = "utf-8" # is this encoding stuff *really* necessary?
        if message["fulltext"] is not None: # yay, we even have the content!!
            if message["encoding"] is not None:
                encoding = message["encoding"]
        else:
            message["fulltext"] = self._load_message_body(message["imapid"])
            encoding = chardet.detect(message["fulltext"])["encoding"]
        email_message = email.message_from_string(message["fulltext"].encode(encoding))
        content = self.get_content_from_message(email_message)[0]
        message["body"] = content
        return message

    """
    Return a dict with the message values (e.g. subject, sender, body...)
    """
    def load_message(self, imapid):
        cur = self.db.execute('select imapid, fulltext, encoding, subject, sender, seen, date from mails'
                             + ' where account = \'' + self.get_ns() + '\''
                             + self._get_where()
                             + ' and mailbox = \'' + self.malibox + '\''
                             + ' and imapid = ' + str(imapid))
        
        entry = cur.fetchall()
        if len(entry) is 0:
            self.download_messages(imapid)
            cur = self.db.execute('select imapid, fulltext, encoding, subject, sender, seen, date from mails'
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

    def load_thread(self, imapid):
        cur = self.db.execute('select imapid, fulltext, encoding, subject, sender, seen, date from mails'
                             + self._get_where()
                             + ' and thrid = ' + str(imapid))
        
        entries = cur.fetchall()
        messages = []
        subject = ""
        for entry in entries:
            if subject is "":
                subject = entry[3]
            messages.append(self._format_message_from_db_row(entry))
        return messages, subject

    def download_messages(self, start):
        typ, data = self.imap_mail.uid("fetch", str(start) + ":*",
                             '(body.peek[header.fields (subject message-id from to date)] x-gm-thrid flags)')
        app.logger.debug("Fetch from %s to *" % (start))
        i = 0
        final = "/" + str(len(data))
        for msg in data:
            if msg[0] == ")":
                continue
            email = {}

            # Parse the email values:
            values_split = msg[0].replace("(", "").split()
            uid_index = values_split.index("UID")
            thrid_index = values_split.index("X-GM-THRID")
            message_id = values_split[uid_index+1]
            thrid = values_split[thrid_index+1]
            app.logger.debug(str(message_id) + final)

            if int(message_id) < start:
                continue

            # Parse the flags
            seen = "\\Seen" in imaplib.ParseFlags(msg[0])
            email["seen"] = seen

            parser = HeaderParser()
            header = parser.parsestr(msg[1])

            decoded = decode_header(header["subject"])[0]
            subject = self._decode_full_proof(decoded[0], decoded[1])

            email["imapid"] = message_id
            email["subject"] = subject
            email["sender"] = decode_header(header["from"])[0]
            email["sender"] = self._decode_full_proof(email["sender"][0], email["sender"][1])
            decoded = decode_header(header["to"])[0]
            to = self._decode_full_proof(decoded[0], decoded[1])
            decoded = decode_header(header["date"])[0]
            date = self._decode_full_proof(decoded[0], decoded[1])
            self.db.execute('insert into mails (subject, account, imapid, seen, sender, thrid, receiver, date)'
                          + ' values (?, ?, ?, ?, ?, ?, ?, ?)',
                             [email["subject"], self.get_ns (), email["imapid"], seen, email["sender"], thrid, to, date])
            i += 1
            if i > 500:
                self.db.commit()
                i = 0
            cur = self.db.execute('select imapid from threads'
                                + self._get_where()
                                + ' limit 1')
            if len(cur.fetchall()) is 0:
                # We need to add a new thread
                self.db.execute('insert into threads (subject, imapid, account, seen)'
                              + ' values (?, ?, ?, ?)',
                                [email["subject"], thrid, self.get_ns(), seen])
        self.db.commit()

    def _get_where(self):
        return ' where account = \'' + self.get_ns() + '\'' + ' and mailbox = \'' + self.mailbox + '\''

    
    """
    Return a list with all message from start to end.
    0 is the last email
    100 is the 100th most recent email
    """
    def load_list(self, start, end):
        cur = self.db.execute('select imapid, subject, sender, seen from mails'
                             + self._get_where()
                             + ' order by imapid desc limit ' + str(end))
        entries = [dict(imapid=row[0], subject=row[1], sender=row[2], seen=row[3]) for row in cur.fetchall()]
        return entries
    
    """
    Return a list with all threads from start to end.
    """
    def load_threads(self, start, end):
        cur = self.db.execute('select imapid, subject, seen from threads'
                             + self._get_where()
                             + ' order by imapid desc limit ' + str(end))
        entries = [dict(imapid=row[0], subject=row[1], seen=row[2]) for row in cur.fetchall()]
        return entries

    def get_content_from_message(self, message_instance):
        content = ""
        maintype = message_instance.get_content_type()
        encoding = message_instance.get_content_charset("utf-8")
        if maintype == "multipart/mixed":
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
            content += self._decode_full_proof(data, encoding).replace("\n", "<br />")
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


def connect_db():
    return sqlite3.connect(app.config['DATABASE'])

def init_db():
    with closing(connect_db()) as db:
        with app.open_resource('schema.sql') as f:
            db.cursor().executescript(f.read())
        db.commit()

@app.route("/mails_thread/<imapid>")
def view_full_thread(imapid):
    if not session.has_key("email"):
        return redirect("/")
    else:
        if not email_accounts.has_key(session["email"]):
            email_accounts[session["email"]] = EmailAccount(session["host"], session["email"], session["password"], "email.db")

        mail = email_accounts[session["email"]]
        mail.open_db()
        mail.load_mailbox("inbox")
        messages = mail.load_thread(imapid)
        mail.close_db()
        return jsonify(message=render_template("thread.html", thread=messages[0], subject=messages[1]))

@app.route("/mails/<int:imapid>")
def view_mail(imapid):
    return jsonify(message=view_mail_raw(imapid))

def view_mail_raw(imapid):
    if not session.has_key("email"):
        return redirect("/")
    else:
        if not email_accounts.has_key(session["email"]):
            email_accounts[session["email"]] = EmailAccount(session["host"], session["email"], session["password"], "email.db")

        mail = email_accounts[session["email"]]
        mail.open_db()
        mail.load_mailbox("inbox")
        message = mail.load_message(imapid)
        mail.close_db()
        return render_template("message.html", message=message, even=False)


@app.route("/", methods=["GET", "POST"])
def start():
    return root(0)

@app.route("/threads/<int:page>")
def view_thread(page):
    # Several case:
    #   - not logged but he sent the authentification things
    #   - the user is not logged
    #   - logged

    if not session.has_key("email"):
        return render_template("login.html")
    else:
        if not email_accounts.has_key(session["email"]):
            email_accounts[session["email"]] = EmailAccount(session["host"], session["email"], session["password"], "email.db")

        mail = email_accounts[session["email"]]
        mail.open_db()
        mail.load_mailbox("inbox")
        
        mails_id = mail.load_threads(0, 100)
        mail.close_db()
        
        emails_list = sorted(mails_id, lambda x, y: cmp(int(y["imapid"]), int(x["imapid"])))
        return render_template('email-thread.html', page=page, emails=emails_list)

@app.route("/sync/<mailbox>")
def sync(mailbox):
    if not email_accounts.has_key(session["email"]):
        email_accounts[session["email"]] = EmailAccount(session["host"], session["email"], session["password"], "email.db")

    mail = email_accounts[session["email"]]
    mail.open_db()
    mail.load_mailbox(mailbox)
    mail.load_messages()
    mail.update_flags(100)
    mail.close_db()
    return jsonify(success=True)

@app.route("/<int:page>", methods=["GET", "POST"])
def root(page):
    # Several case:
    #   - not logged but he sent the authentification things
    #   - the user is not logged
    #   - logged

    if not session.has_key("email") and request.form.has_key("email"):
        session["email"] = request.form["email"]
        session["host"] = request.form["host"]
        session["password"] = request.form["password"]
        return redirect("/")
    elif not session.has_key("email"):
        return render_template("login.html")
    else:
        if not email_accounts.has_key(session["email"]):
            email_accounts[session["email"]] = EmailAccount(session["host"], session["email"], session["password"], "email.db")

        mail = email_accounts[session["email"]]
        mail.open_db()
        mail.load_mailbox("inbox")
        mails_id = mail.load_list(0, 100)
        mail.close_db()
        emails_list = sorted(mails_id, lambda x, y: cmp(int(y["imapid"]), int(x["imapid"])))
        return render_template('email-list.html', page=0, emails=emails_list)

email_accounts = {}

if __name__ == "__main__":
    app.debug = True
    app.run()
