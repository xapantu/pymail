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


app = Flask(__name__)


DATABASE = "email.db"
DEBUG=True
SECRET_KEY="ah ah"
OFFLINE=False

app.config.from_object(__name__)

imap_accounts = {}

def connect_db():
    return sqlite3.connect(app.config['DATABASE'])

def init_db():
    with closing(connect_db()) as db:
        with app.open_resource('schema.sql') as f:
            db.cursor().executescript(f.read())
        db.commit()
            

def load_imap_account(host, name, password):
    mail = imaplib.IMAP4_SSL(host)
    mail.login(name, password)
    mail.list()
    app.logger.debug("load imap")
    imap_accounts[name] = mail

def close_imap_account():
    mail.close()
    app.logger.debug("close imap")
    #mail.logout()

def load_message(mail, mails_id, start, end, database):
    if start > end:
        return
    typ, data = mail.uid("fetch", str(start) + ":" + str(end),
                         '(body.peek[header.fields (subject message-id)] flags)')
    app.logger.debug("start: %s, end: %s" % (start, end))
    for msg in data:
        if msg[0] == ")":
            continue
        email = {}
        message_id = msg[0].split()[2]
        if mails_id.has_key(message_id):
            continue
        app.logger.debug(message_id)
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
        database.execute('insert into mails (subject, account, imapid, seen) values (?, ?, ?, ?)',
                         [email["subject"], session["email"], email["imapid"], seen])
        mails_id[message_id] = email

def load_message_with_cache(mail, database, page_size, page):
    if not app.config["OFFLINE"]:
        typ, data = mail.uid("search", None, 'ALL')

        # How many messages available?
        server_imap_ids = data[0].split()
        server_mail_count = len(server_imap_ids) - 1
        start_wanted = int(server_imap_ids[max(server_mail_count - (page + 1) * page_size + 1, 0)]) # 100 messages per page
        end_wanted = int(server_imap_ids[max(server_mail_count - page * page_size, 0)])

        cur = database.execute('select imapid, subject, seen from mails where account = \'' + session["email"] + '\' and imapid >= ' + str(start_wanted) + ' and imapid <= ' +  str(end_wanted) + ' ORDER by imapid')
    else:
        cur = database.execute('select imapid, subject, seen from mails where account = \'' + session["email"] + '\' ORDER by imapid desc limit ' + str(page_size))
    mails_id = {}

    entries = [dict(imapid=row[0], subject=row[1], seen=row[2]) for row in cur.fetchall()]


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
        email = {}
        email["seen"] = entry["seen"]
        email["subject"] = entry["subject"]
        mails_id[str(entry["imapid"])] = entry
    
    return mails_id

def clean_text(text):
    return text.replace("\r\n", "").replace("\n", "<br />")
def get_content_from_message(message_instance):
    content = ""
    maintype = message_instance.get_content_type()
    app.logger.debug(maintype)
    encoding = message_instance.get_content_charset("utf-8")
    if maintype in ("multipart/mixed", "multipart/alternative"): #arg :(
        for part in message_instance.get_payload():
            content += get_content_from_message(part)
    elif maintype == "text/plain":
        data = message_instance.get_payload(decode=True)
        content += data.decode(encoding).replace("\n", "<br />")
    elif maintype == "text/html":
        data = message_instance.get_payload(decode=True)
        content += data.decode(encoding)
    return content

@app.route("/mails/<int:imapid>")
def view_mail(imapid):
    if not session.has_key("email"):
        return redirect("/")
    else:
        if not app.config["OFFLINE"]:
            if not imap_accounts.has_key(session["email"]):
                load_imap_account(session["host"], session["email"], session["password"])
            mail = imap_accounts[session["email"]]
            mail.select("inbox") # connect to inbox.
        # First - is it in the DB?
        database = connect_db()
        cur = database.execute('select imapid, subject, seen, encoding, fulltext from mails'
                               + ' where account = \'' + session["email"] + '\' and imapid = ' + str(imapid))
        entries = [dict(imapid=row[0], subject=row[1], seen=row[2], fulltext=row[3], encoding=row[4]) for row in cur.fetchall()]
        import chardet
        if len(entries) > 0: # yay, we have it in the db
            message = entries[0]
            encoding = "utf-8"
            if message["fulltext"] is not None: # yay, we even have the content!!
                encoding = message["encoding"]
                pass
            else:
                typ, data = mail.uid("fetch", imapid, '(body.peek[])')
                app.logger.debug(data[0][1])
                msg = data[0][1].decode(chardet.detect(data[0][1])["encoding"])
                app.logger.debug(chardet.detect(data[0][1]))
                database.executemany("update mails set fulltext = ? where imapid = %s" % (imapid), [(msg,)])
                database.commit()
                database.close()
                message["fulltext"] = msg
                encoding = chardet.detect(data[0][1])["encoding"]
            email_message = email.message_from_string(message["fulltext"].encode(encoding))
            content = get_content_from_message(email_message)
            #message["fulltext"] = content
            return jsonify(message=render_template("message.html", message=content))
        else:
            mails_id = {} # not used here, just a simple dict to send to load_message, useless in our case
            load_message(mail, mails_id, imapid, imapid, database)
            database.commit()
            database.close()
            return view_mail(imapid)


@app.route("/", methods=["GET", "POST"])
def start():
    return root(0)

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
        mail = None
        if not app.config["OFFLINE"]:
            if not imap_accounts.has_key(session["email"]):
                load_imap_account(session["host"], session["email"], session["password"])
            mail = imap_accounts[session["email"]]
            # Out: list of "folders" aka labels in gmail.
            mail.select("inbox") # connect to inbox.
        database = connect_db()

        mails_id = load_message_with_cache(mail, database, 500, page)
        
        database.commit()
        database.close()
        return render_template('email-list.html', page=page, emails=sorted(mails_id.values(), lambda x, y: cmp(int(y["imapid"]), int(x["imapid"]))))

if __name__ == "__main__":
    #load_imap_account()
    app.debug = True
    app.run()
    #close_imap_account()
