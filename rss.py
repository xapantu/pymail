#! /usr/bin/env python2
# -*- coding: utf-8 -*-

from geventwebsocket.handler import WebSocketHandler
import geventwebsocket
from gevent.pywsgi import WSGIServer

from flask import Flask, render_template, session, request, redirect, url_for, jsonify, g
from contextlib import closing
import sqlite3
import xml.etree.ElementTree
import email.utils
import time
import gevent
import date_formater
import threading
import feedparser
import urllib

app = Flask(__name__)
DATABASE = "rss/rss.sqlite"
DEBUG=True
SECRET_KEY="ah ah"
OFFLINE=False
app.config.from_object(__name__)

@app.before_request
def before_request():
    g.db = sqlite3.connect(app.config['DATABASE'])
    import rss_db
    g.al = rss_db.FeedsDatabase()
    date_formater.init_date()

@app.teardown_request
def teardown_request(exception):
    g.db.close()

def download_file(uri):
    page = urllib.urlopen(uri)
    return page.read()

def add_feed(feed_name):
    if "://" not in feed_name:
        feed_name = "http://" + feed_name
    g.db.execute("insert into feeds (url, name) values (?, ?)", (feed_name,feed_name))
    g.db.commit()

class NoFeedFound(Exception):
    pass

def sync_feed(feedid, db):
    print "start sync_feed"
    cur = db.execute("select name, url from feeds where id = " + str(feedid))
    row = cur.fetchall()[0]
    print "request done"
    data = feedparser.parse(row[1])
    print "feed parsed and retrieved"
    if data["feed"].has_key("html"):
        # Okay, it is a webpage, let's detect the feed
        for link in data["feed"]["links"]:
            if link["type"] == "application/atom+xml" or link["type"] == "aplication/rss+xml":
                url = link["url"]
                db.execute("update feeds set url = (?) where id = " + str(feedid), (url,))
                db.commit()
                data = feedparser.parse(url)
                app.logger.debug("Switch to URL %s for %s." % (url, row[1]))
                break
        print "parsed"
    if data["feed"].has_key("html") or not (data["feed"].has_key("title")):
        raise NoFeedFound("Couldn't use this URL %s : no rss found there." % url)
    app.logger.debug(data["feed"]["title"])
    if data["feed"]["title"] != row[0]:
        db.execute("update feeds set name = (?) where id = " + str(feedid), (data["feed"]["title"],))
        db.commit()
    if data["url"] != row[1]:
        db.execute("update feeds set url = (?) where id = " + str(feedid), (data["url"],))
        db.commit()

    print "checking finished"
    # We check wether each article is in the db
    for article in data["entries"]:
        # How many article with this id?
        cur = db.execute("select count(id) from articles where guid = (?) and feed = (?)", (article["id"], feedid))
        count = cur.fetchall()[0][0]
        if count == 0:
            db.execute("insert into articles (name, url, guid, content, feed, pubDate, seen) values (?, ?, ?, ?, ?, ?, 0)", (article["title"], article["link"], article["id"], article["description"], feedid, time.strftime("%Y-%m-%d %H:%M:%S", article["updated_parsed"])))
    db.commit()

@app.route("/ajax/seen/<int:article>/<int:seen>")
def ajax_mark_seen(article, seen):
    #FIXME: investigate wether the int: is enough to avoid a sql injection, not sure right now
    g.db.execute("update articles set seen = " + str(seen) + " where id = " + str(article))
    app.logger.debug("update articles set seen = " + str(seen) + " where id = " + str(article))
    g.db.commit()
    return jsonify(done=1)

@app.route("/ajax/seen/feed/<int:article>/<int:seen>")
def ajax_mark_seen_feed(article, seen):
    #FIXME: investigate wether the int: is enough to avoid a sql injection, not sure right now
    g.db.execute("update articles set seen = " + str(seen) + " where feed = " + str(article))
    g.db.commit()
    return jsonify(done=1)

@app.route("/ajax/seen/feed/-1/<int:seen>")
def ajax_mark_all_seen(seen):
    g.db.execute("update articles set seen = " + str(seen))
    g.db.commit()
    return jsonify(done=1)


def save_view_mode(mode):
    g.db.execute("update configuration set value = '" + str(mode) + "' where key = 'view-mode'")
    g.db.commit()

@app.route("/ajax/feed/-1")
def ajax_unread():
    save_view_mode(0)
    cur = g.db.execute("select articles.name, articles.id, articles.pubDate, articles.seen, feeds.name, feeds.id from articles, feeds where feeds.id = articles.feed and seen = 0 order by articles.pubDate desc")
    subitems = [dict(subject=row[0], id=row[1], date=date_formater.format_date(row[2]), seen=row[3], sender=row[4], feed=row[5]) for row in cur.fetchall()]
    return jsonify(content=render_template("rss/rss-ajax-subitems.html", subitems=subitems, subitems_target="/ajax/article/"))

@app.route("/ajax/feed/<int:feedid>/")
def ajax_feed(feedid):
    save_view_mode(0)
    cur = g.db.execute("select name, id, pubDate, seen, feed from articles where feed = " + str(feedid) + " order by articles.pubDate desc")
    subitems = [dict(subject=row[0], id=row[1], date=date_formater.format_date(row[2]), seen=row[3], feed=row[4]) for row in cur.fetchall()]
    return jsonify(content=render_template("rss/rss-ajax-subitems.html", subitems=subitems, subitems_target="/ajax/article/"))


@app.route("/ajax/article/<int:article>/")
def ajax_article(article):
    date_formater.init_date()
    cur = g.db.execute("select feeds.url, articles.name, articles.id, articles.content, articles.seen, feeds.name, articles.pubDate, articles.url, articles.feed from articles, feeds where feeds.id = articles.feed and articles.id = " + str(article) + " order by articles.pubDate desc")
    feeds = [dict(sender=(row[1], row[5], row[7]), imapid=row[2], seen=row[4], body=row[3] + "<div class=\"clearer\"></div>", date=date_formater.format_date(row[6]), feedid=row[8]) for row in cur.fetchall()]
    return jsonify(content=render_template("rss/rss-ajax-thread.html", thread=feeds))

@app.route("/ajax/fullview/-1")
def ajax_full_view_unread():
    save_view_mode(1)
    date_formater.init_date()
    cur = g.db.execute("select feeds.url, articles.name, articles.id, articles.content, articles.seen, feeds.name, articles.pubDate, articles.url, articles.feed from articles, feeds where feeds.id = articles.feed and seen = 0 order by articles.pubDate desc")
    feeds = [dict(sender=(row[1], row[5], row[7]), imapid=row[2], seen=row[4], body=row[3] + "<div class=\"clearer\"></div>", date=date_formater.format_date(row[6]), feedid=row[8]) for row in cur.fetchall()]
    return jsonify(content=render_template("rss/rss-ajax-thread.html", thread=feeds))

@app.route("/ajax/fullview/<int:article>/")
def ajax_full_view(article):
    save_view_mode(1)
    date_formater.init_date()
    cur = g.al.get_articles_for_feed(article)
    feeds = [dict(sender=(art.name, feed.url, art.url), imapid=art.id, seen=art.seen, body=art.content + "<div class=\"clearer\"></div>", date=date_formater.format_date(art.pubDate), feedid=art.feed) for art, feed in cur]
    return jsonify(content=render_template("rss/rss-ajax-thread.html", thread=feeds))

@app.route("/sync/<int:feedid>/")
def sync(feedid):
    success = True
    try:
        sync_feed(feedid)
    except NoFeedFound as e:
        app.logger.debug(e)
        success = False
    return jsonify(done=success)

def get_feed_list():
    feeds = g.al.get_all_feeds()
    return feeds

@app.route("/sync")
def sync_all():
    cur = g.db.execute("select id from feeds")
    success = True
    for row in cur.fetchall():
        try:
            sync_feed(row[0])
        except NoFeedFound as e:
            app.logger.debug(e)
            success = False
    # Get the feeds
    feeds = get_feed_list()
    return jsonify(done=success, content=render_template("rss/rss-ajax-firstpane.html", feeds=feeds))

@app.route("/", methods=["POST", "GET"])
def root():
    if request.form.has_key("new_feed"):
        add_feed(request.form["new_feed"])

    # Get the feeds
    feeds = get_feed_list()
    cur = g.al.get_conf("view-mode")
    fullview_default = int(cur) == 1
    return render_template("rss/rss.html", feeds=feeds, fullview_default=fullview_default, page_class="rss")

def init_db():
    with closing(sqlite3.connect(DATABASE)) as db:
        with app.open_resource('rss.sql') as f:
            db.cursor().executescript(f.read())
        db.commit()

def check_timed(ws, db, event):
    #ws, db = data
    i = 0
    while True:
        i += 1
        if event.is_set():
            print "break"
            break
        ws.send('{ "message" : "%s" }' % ("i: %s" % i))
        #cur = db.execute("select * from configuration")
        #print cur.fetchall()
        #print "a"
        time.sleep(1)

def api_sync_async(ws, db, al, event):
    db = sqlite3.connect("rss/rss.sqlite")
    success = True
    try:
        for row in al.get_all_feeds():
            ws.send('{ "message" : "%s"}' % row.name)
            try:
                sync_feed(row.id, db)
            except NoFeedFound as e:
                app.logger.debug(e)
                success = False
            if event.is_set():
                print "break"
                break
    except:
        raise
        app.logger.debug("ERROR")
    db.close()
    ws.send('{ "done" : "%s"}' % success)
    # Get the feeds
    #feeds = get_feed_list()
    #return jsonify(done=success, content=render_template("rss/rss-ajax-firstpane.html", feeds=feeds))

@app.route("/api/sync")
def api_sync():
    if request.environ.get('wsgi.websocket'):
        ws = request.environ['wsgi.websocket']
        event = threading.Event()
        th = threading.Thread(None, api_sync_async, None, (ws, g.db, g.al,event))
        th.start()
        try:
            message = ws.receive()
            ws.close()
            event.set()
        except geventwebsocket.WebSocketError:
            event.set()
    return ""

#if __name__ == "__main__":
#    app.debug = True
#    app.run(port=5001)

if __name__ == '__main__':
    app.debug = True
    http_server = WSGIServer(('',5001), app, handler_class=WebSocketHandler)
    http_server.serve_forever()
