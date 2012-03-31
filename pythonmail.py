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
        try:
            self.imap_mail.select(mailbox) # connect to inbox.
        except imaplib.abort: # maybe a timeout?
            self.load_imap_account()
            self.imap_mail.select("inbox") # connect to inbox.

    def get_ns(self):
        return self.name + ":" + self.host

    """
    Open the DB, check what is the oldest message we have there, and download all the new ones.
    """
    def load_messages(self):
        cur = self.db.execute('select imapid from mails'
                             + ' where account = \'' + self.get_ns() + '\''
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
        message["seen"] = True

        encoding = "utf-8" # is this encoding stuff *really* necessary?
        if message["fulltext"] is not None: # yay, we even have the content!!
            if message["encoding"] is not None:
                encoding = message["encoding"]
        else:
            message["fulltext"] = self._load_message_body(message["imapid"])
            encoding = chardet.detect(message["fulltext"])["encoding"]
        email_message = email.message_from_string(message["fulltext"].encode(encoding))
        content = self.get_content_from_message(email_message)
        message["body"] = content
        return message

    """
    Return a dict with the message values (e.g. subject, sender, body...)
    """
    def load_message(self, imapid):
        cur = self.db.execute('select imapid, fulltext, encoding, subject, sender, seen from mails'
                             + ' where account = \'' + self.get_ns() + '\''
                             + ' and imapid = ' + str(imapid))
        
        entry = cur.fetchall()
        if len(entry) is 0:
            self.download_messages(imapid)
            cur = self.db.execute('select imapid from mails'
                                 + ' where account = \'' + self.get_ns() + '\''
                                 + ' and imapid = ' + str(imapid))
            
            entry = cur.fetchall()
            if len(entry) is 0:
                raise
        return self._format_message_from_db_row(entry[0])
    
    def load_thread(self, imapid):
        cur = self.db.execute('select imapid, fulltext, encoding, subject, sender, seen from mails'
                             + ' where account = \'' + self.get_ns() + '\''
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
        app.logger.debug("DONWLOAD")
        typ, data = self.imap_mail.uid("fetch", str(start) + ":*",
                             '(body.peek[header.fields (subject message-id from)] x-gm-thrid flags)')
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
            encodage = "utf-8"
            if decoded[1] is not None: encodage = decoded[1]
            try:
                subject = decoded[0].decode(encodage)
            except UnicodeDecodeError:
                subject = decoded[0].decode(chardet.detect(decoded[0])["encoding"])

            email["imapid"] = message_id
            email["subject"] = subject
            email["sender"] = decode_header(header["from"])[0]
            encodage = "utf-8"
            if email["sender"][1] is not None: encodage = email["sender"][1]
            try:
                email["sender"] = email["sender"][0].decode(encodage)
            except UnicodeDecodeError:
                email["sender"] = email["sender"][0].decode(chardet.detect(email["sender"][0])["encoding"])
            """
            fulltext = ""
            try:
                fulltext = msg[1].decode(chardet.detect(msg[1])["encoding"])
            except:
                try:
                    fulltext = msg[1].decode("utf-8") # sometimes, chardet is just false
                except:
                    fulltext = unicode(msg[1], errors="ignore") # ok, let's forgot odd chars
            """
            self.db.execute('insert into mails (subject, account, imapid, seen, sender, thrid)'
                          + ' values (?, ?, ?, ?, ?, ?)',
                             [email["subject"], self.get_ns (), email["imapid"], seen, email["sender"], thrid])
            i += 1
            if i > 500:
                self.db.commit()
                i = 0
            cur = self.db.execute('select imapid from threads'
                                + ' where imapid = \'' + str(thrid) + '\''
                                + ' and account = \'' + self.get_ns() + '\''
                                + ' limit 1')
            if len(cur.fetchall()) is 0:
                # We need to add a new thread
                self.db.execute('insert into threads (subject, imapid, account)'
                              + ' values (?, ?, ?)',
                                [email["subject"], thrid, self.get_ns()])
        self.db.commit()
    
    """
    Return a list with all message from start to end.
    0 is the last email
    100 is the 100th most recent email
    """
    def load_list(self, start, end):
        cur = self.db.execute('select imapid, subject, sender, seen from mails'
                             + ' where account = \'' + self.get_ns() + '\''
                             + ' order by imapid desc limit ' + str(end))
        entries = [dict(imapid=row[0], subject=row[1], sender=row[2], seen=row[3]) for row in cur.fetchall()]
        return entries
    
    """
    Return a list with all threads from start to end.
    """
    def load_threads(self, start, end):
        cur = self.db.execute('select imapid, subject, seen from threads'
                             + ' where account = \'' + self.get_ns() + '\''
                             + ' order by imapid desc limit ' + str(end))
        entries = [dict(imapid=row[0], subject=row[1], seen=row[2]) for row in cur.fetchall()]
        return entries

    def get_content_from_message(self, message_instance):
        content = ""
        maintype = message_instance.get_content_type()
        app.logger.debug(maintype)
        encoding = message_instance.get_content_charset("utf-8")
        if maintype in ("multipart/mixed", "multipart/alternative"): #arg :(
            for part in message_instance.get_payload():
                content += self.get_content_from_message(part)
        elif maintype == "text/plain":
            data = message_instance.get_payload(decode=True)
            content += self._decode_full_proof(data, encoding).replace("\n", "<br />")
        elif maintype == "text/html":
            data = message_instance.get_payload(decode=True)
            content += data.decode(encoding)
        return content

    def _decode_full_proof(self, text, encoding):
        try:
            text = text.decode(encoding)
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
            

#def load_imap_account(host, name, password):
#    mail = imaplib.IMAP4_SSL(host)
#    mail.login(name, password)
#    mail.list()
#    app.logger.debug("load imap")
#    imap_accounts[name] = mail

#def close_imap_account():
#    mail.close()
#    app.logger.debug("close imap")
#    #mail.logout()

def load_message(mail, mails_id, start, end, database):
    if start > end:
        return
    typ, data = mail.uid("fetch", str(start) + ":" + str(end),
                         '(body.peek[header.fields (subject message-id from)] x-gm-thrid flags)')
    app.logger.debug("start: %s, end: %s" % (start, end))
    for msg in data:
        if msg[0] == ")":
            continue
        email = {}
        values_split = msg[0].replace("(", "").split()
        uid_index = values_split.index("UID")
        thrid_index = values_split.index("X-GM-THRID")
        #thrid_index = values_split.index("X")
        message_id = values_split[uid_index+1]
        thrid = values_split[thrid_index+1]
        if mails_id.has_key(message_id):
            continue
        seen = "\\Seen" in imaplib.ParseFlags(msg[0])
        email["seen"] = seen

        parser = HeaderParser()
        header = parser.parsestr(msg[1])

        decoded = decode_header(header["subject"])[0]
        encodage = "utf-8"
        if decoded[1] is not None: encodage = decoded[1]
        subject = decoded[0].decode(encodage)

        email["imapid"] = message_id
        email["subject"] = subject
        email["sender"] = decode_header(header["from"])[0]
        encodage = "utf-8"
        if email["sender"][1] is not None: encodage = email["sender"][1]
        email["sender"] = email["sender"][0].decode(encodage)
        database.execute('insert into mails (subject, account, imapid, seen, sender, thrid)'
                       + ' values (?, ?, ?, ?, ?, ?)',
                         [email["subject"], session["email"], email["imapid"], seen, email["sender"], thrid])
        database.commit()
        mails_id[message_id] = email
        cur = database.execute('select imapid from threads'
                             + ' where imapid = \'' + str(thrid) + '\''
                             + ' and account = \'' + session["email"] + '\''
                             + ' limit 1')
        if len(cur.fetchall()) is 0:
            # We need to add a new thread
            database.execute('insert into threads (subject, imapid, account)'
                       + ' values (?, ?, ?)',
                         [email["subject"], thrid, session["email"]])

def load_message_with_cache(mail, database, page_size, page):
    if not app.config["OFFLINE"]:
        typ, data = mail.uid("search", None, 'ALL')

        # How many messages available?
        server_imap_ids = data[0].split()
        server_mail_count = len(server_imap_ids) - 1
        start_wanted = int(server_imap_ids[max(server_mail_count - (page + 1) * page_size + 1, 0)]) # 100 messages per page
        end_wanted = int(server_imap_ids[max(server_mail_count - page * page_size, 0)])

        cur = database.execute('select imapid, subject, seen, sender from mails'
                             + ' where account = \'' + session["email"] + '\''
                             + ' and imapid >= ' + str(start_wanted)
                             + ' and imapid <= ' +  str(end_wanted) + ' ORDER by imapid')
    else:
        cur = database.execute('select imapid, subject, seen, sender from mails'
                             + ' where account = \'' + session["email"] + '\''
                             + ' order by imapid desc limit ' + str(page_size))
    mails_id = {}

    entries = [dict(imapid=row[0], subject=row[1], seen=row[2], sender=row[3]) for row in cur.fetchall()]


    if not app.config["OFFLINE"]:
        # So, here, we can:
        # - have all messages
        # - have the first messages
        # - have the last messages
        # So, we need to do *two* fetchs
        
        first_db_id = end_wanted # means we have nothing
        end_db_id = end_wanted # means we have everything. If we don't have anything, we
                               # don't need this (only one fetch is required), otherwise,
                               # it will be set later
        if len(entries) > 0:
            first_db_id = entries[0]["imapid"] - 1
            end_db_id = entries[-1]["imapid"] + 1

        # First fetch from start_wanted to first_db_id (let's hope it is ==)
        load_message(mail, mails_id, start_wanted, first_db_id, database)

        # Then from end_db_id to end_wanted
        load_message(mail, mails_id, end_db_id, end_wanted, database)

    # load other mails
    for entry in entries:
        mails_id[str(entry["imapid"])] = entry
    
    if not app.config["OFFLINE"]:
        app.logger.debug(str(first_db_id))
        app.logger.debug(str(end_db_id))
        typ, data = mail.uid("fetch", str(first_db_id+1) + ":" + str(end_db_id),
                             '(flags)')
        for msg in data:
            mailid = msg.split()[2]
            old_seen = mails_id[mailid]["seen"]
            seen = "\\Seen" in imaplib.ParseFlags(msg)
            if old_seen is not int(seen):
                app.logger.debug("DIFFERENT for message " + str(mailid) + str(seen) + str(old_seen))
                database.execute("update mails set seen = " + str(int(seen)) + " where imapid = %s" % (mailid))
            mails_id[mailid]["seen"] = seen
    
    return mails_id

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
@app.route("/cache_all")
def cache_all():
    mail = None
    if not session.has_key("email"):
        return "not logged"
    if not imap_accounts.has_key(session["email"]):
        load_imap_account(session["host"], session["email"], session["password"])
    mail = imap_accounts[session["email"]]
    # Out: list of "folders" aka labels in gmail.
    try:
        mail.select("inbox") # connect to inbox.
    except imaplib.abort:
        load_imap_account(session["host"], session["email"], session["password"])
        mail = imap_accounts[session["email"]]
        mail.select("inbox") # connect to inbox.
    
    database = connect_db()
    typ, data = mail.uid("fetch", "1:*",
                         '(body.peek[] x-gm-thrid flags)')
    
    # load all the mails from the db
    cur = database.execute('select imapid from mails where account = \'' + session["email"] + '\'')
    entries = [row[0] for row in cur.fetchall()]
    app.logger.debug(str(entries))
    final = "/" + str(len(data))
    mails_id = {}
    import chardet


    i = 0
    for msg in data:
        if msg[0] == ")":
            continue
        email = {}
        values_split = msg[0].replace("(", "").split()
        uid_index = values_split.index("UID")
        thrid_index = values_split.index("X-GM-THRID")
        #thrid_index = values_split.index("X")
        message_id = values_split[uid_index+1]
        app.logger.debug(str(message_id ) + final)
        if int(message_id) in entries:
            continue
        thrid = values_split[thrid_index+1]
        if mails_id.has_key(message_id):
            continue
        seen = "\\Seen" in imaplib.ParseFlags(msg[0])
        email["seen"] = seen

        parser = HeaderParser()
        header = parser.parsestr(msg[1])

        decoded = decode_header(header["subject"])[0]
        encodage = "utf-8"
        if decoded[1] is not None: encodage = decoded[1]
        try:
            subject = decoded[0].decode(encodage)
        except UnicodeDecodeError:
            subject = decoded[0].decode(chardet.detect(decoded[0])["encoding"])

        email["imapid"] = message_id
        email["subject"] = subject
        email["sender"] = decode_header(header["from"])[0]
        encodage = "utf-8"
        if email["sender"][1] is not None: encodage = email["sender"][1]
        try:
            email["sender"] = email["sender"][0].decode(encodage)
        except UnicodeDecodeError:
            email["sender"] = email["sender"][0].decode(chardet.detect(email["sender"][0])["encoding"])
        fulltext = ""
        try:
            fulltext = msg[1].decode(chardet.detect(msg[1])["encoding"])
        except:
            try:
                fulltext = msg[1].decode("utf-8") # sometimes, chardet is just false
            except:
                fulltext = unicode(msg[1], errors="ignore") # ok, let's forgot old chars

        database.execute('insert into mails (subject, account, imapid, seen, sender, thrid, fulltext)'
                       + ' values (?, ?, ?, ?, ?, ?, ?)',
                         [email["subject"], session["email"], email["imapid"], seen, email["sender"], thrid, fulltext])
        i += 1
        if i > 500:
            database.commit()
            i = 0
        mails_id[message_id] = email
        cur = database.execute('select imapid from threads'
                             + ' where imapid = \'' + str(thrid) + '\''
                             + ' and account = \'' + session["email"] + '\''
                             + ' limit 1')
        if len(cur.fetchall()) is 0:
            # We need to add a new thread
            database.execute('insert into threads (subject, imapid, account)'
                       + ' values (?, ?, ?)',
                         [email["subject"], thrid, session["email"]])
    database.commit()
    database.close()
    return "Sucess"


if __name__ == "__main__":
    app.debug = True
    app.run()
