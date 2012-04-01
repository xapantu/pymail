#! /usr/bin/env python
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
        app.logger.debug("LOAD IMAP")
        mail = imaplib.IMAP4_SSL(self.host)
        mail.login(self.name, self.password)
        status, mailboxes = mail.list()
        self._mailboxes = []
        app.logger.debug(str(mail.namespace()))

        for mailbox in mailboxes:
            mb = mailbox.split(" \"")[2].replace("\"", "")
            self._mailboxes.append((mb.replace("/", "%"), mb))

        app.logger.debug("load imap accounts")
        self.imap_mail = mail

    def get_mailboxes(self):
        return self._mailboxes

    def open_db(self):
        app.logger.debug("OPEN DB")
        self.db = sqlite3.connect(self.database_name)
        app.logger.debug("OPEN DB")

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
        except imaplib.abort: # maybe a timeout?
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
        message = {}
        message["imapid"] = entry[0]
        message["fulltext"] = entry[1]
        message["encoding"] = entry[2]
        message["subject"] = entry[3]
        message["sender"] = entry[4]
        message["seen"] = entry[5]
        message["date"] = entry[6]
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
                             + " where account = '" + self.get_ns() + "'"
                             + ' and thrid = ' + str(imapid)
                             + ' order by date')
        
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
        threads_date = {}
        threads_seen = {}
        for msg in data:
            if msg is None or msg[0] == ")":
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
                subject += self._decode_full_proof(decod[0], decod[1])

            email["imapid"] = message_id
            email["subject"] = subject
            email["sender"] = decode_header(header["from"])[0]
            email["sender"] = self._decode_full_proof(email["sender"][0], email["sender"][1])
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
            cur = self.db.execute('select seen from threads'
                                + self._get_where_no_mb()
                                + ' and imapid = ' + str(thrid)
                                + ' limit 1')
            thread_db = cur.fetchall()
            if len(thread_db) is 0:
                # We need to add a new thread
                self.db.execute('insert into threads (subject, imapid, account, seen, mailbox, date)'
                              + ' values (?, ?, ?, ?, ?, ?)',
                                [email["subject"], thrid, self.get_ns(), seen, self.mailbox, date])
            else:
                if thread_db[0][0] == True and email["seen"] == False:
                    threads_seen[str(thrid)] = (email["seen"], thrid)
                threads_date[str(thrid)] = (date, thrid)
        self.db.commit()
        for th_date in threads_date.values():
            self.db.execute('update threads set date = \'' + th_date[0] + "'"
                              + self._get_where_no_mb() + " and imapid = " + str(th_date[1]))
        for th_date in threads_seen.values():
            self.db.execute('update threads set seen = ' + str(int(th_date[0]))
                              + self._get_where_no_mb() + " and imapid = " + str(th_date[1]))
        self.db.commit()
    
    def _get_where_no_mb(self):
        return ' where account = \'' + self.get_ns() + '\''


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
                             + ' order by imapid desc limit %s,%s' % (start, end))
        entries = [dict(imapid=row[0], subject=row[1], sender=row[2], seen=row[3]) for row in cur.fetchall()]
        return entries
    
    """
    Return a list with all threads from start to end.
    """
    def load_threads(self, start, end):
        cur = self.db.execute('select imapid, subject, seen from threads'
                             + self._get_where()
                             + self._get_order_by()
                             + ' limit %s,%s' % (start, end))
        entries = [dict(imapid=row[0], subject=row[1], seen=row[2]) for row in cur.fetchall()]
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

@app.route("/mails_thread/<mailbox>/<imapid>")
def view_full_thread(mailbox, imapid):
    if not session.has_key("email"):
        return redirect("/")
    else:
        if not email_accounts.has_key(session["email"]):
            email_accounts[session["email"]] = EmailAccount(session["host"], session["email"], session["password"], "email.db")

        mail = email_accounts[session["email"]]
        mail.open_db()
        mail.load_mailbox(mailbox)
        messages = mail.load_thread(imapid)
        mail.close_db()
        return jsonify(message=render_template("thread.html", thread=messages[0], subject=messages[1]))

@app.route("/mails/<mailbox>/<int:imapid>")
def view_mail(imapid):
    return jsonify(message=view_mail_raw(imapid, mailbox))

def view_mail_raw(imapid, mailbox = "INBOX"):
    if not session.has_key("email"):
        return redirect("/")
    else:
        if not email_accounts.has_key(session["email"]):
            email_accounts[session["email"]] = EmailAccount(session["host"], session["email"], session["password"], "email.db")

        mail = email_accounts[session["email"]]
        mail.open_db()
        mail.load_mailbox(mailbox)
        message = mail.load_message(imapid)
        mail.close_db()
        return render_template("message.html", message=message, even=False)


@app.route("/", methods=["GET", "POST"])
def start():
    return view_thread("INBOX", 0)

@app.route("/ajax/threadslist/<mailbox>/<int:page>")
def view_thread_list(mailbox, page):
    # Several case:
    #   - not logged but he sent the authentification things
    #   - the user is not logged
    #   - logged


    app.logger.debug(mailbox)
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
        mail.load_mailbox(mailbox)
        
        mails_id = mail.load_threads(page*100, (page + 1)*100)
        mail.close_db()
        
        return jsonify(thread_list=render_template('ajax-threads-list.html', emails=mails_id, mailbox=mailbox, mailboxes=mail.get_mailboxes()))

@app.route("/threads/<mailbox>/<int:page>")
def view_thread(mailbox, page):
    # Several case:
    #   - not logged but he sent the authentification things
    #   - the user is not logged
    #   - logged


    app.logger.debug(mailbox)
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
        mail.load_mailbox(mailbox)
        
        mails_id = mail.load_threads(page*100, (page + 1)*100)
        mail.close_db()
        
        return render_template('email-thread.html', page_next="/threads/" + mailbox + "/" + str(int(page) + 1), page_back="/threads/" + mailbox + "/" + str(int(page) - 1), page=page, emails=mails_id, mailbox=mailbox, mailboxes=mail.get_mailboxes())

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

@app.route("/box/<mailbox>/<int:page>", methods=["GET", "POST"])
def root(mailbox, page):
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
        mail.load_mailbox(mailbox)
        mails_id = mail.load_list(page * 100, (page + 1) * 100)
        mail.close_db()
        emails_list = sorted(mails_id, lambda x, y: cmp(int(y["imapid"]), int(x["imapid"])))
        return render_template('email-list.html', page=0, emails=emails_list, mailbox=mailbox)

email_accounts = {}

if __name__ == "__main__":
    app.debug = True
    app.run()
