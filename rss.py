#! /usr/bin/env python2
# -*- coding: utf-8 -*-

from flask import Flask, render_template, session, request, redirect, url_for, jsonify, g
from contextlib import closing
import sqlite3
import xml.etree.ElementTree
import email.utils
import time
import date_formater

app = Flask(__name__)
DATABASE = "rss/rss.sqlite"
DEBUG=True
SECRET_KEY="ah ah"
OFFLINE=False
app.config.from_object(__name__)

@app.before_request
def before_request():
    g.db = sqlite3.connect(app.config['DATABASE'])
    date_formater.init_date()

@app.teardown_request
def teardown_request(exception):
    g.db.close()

def download_file(uri):
    import urllib
    page = urllib.urlopen(uri)
    return page.read()

def parse_item(item):
    title = None
    link = None
    description = None
    pubDate = None
    guid = None

    for node in item:
        if node.tag == "title":
            title = node.text
        elif node.tag == "link":
            link = node.text
        elif node.tag == "description":
            description = node.text
        elif node.tag == "pubDate":
            pubDate = time.strftime("%Y-%m-%d %H:%M:%S", email.utils.parsedate(node.text))
        elif node.tag == "guid":
            guid = node.text
        else:
            print("%s element not handled" % node.tag)

    return dict(title=title, link=link, description=description, pubDate=pubDate, guid=guid)

def parse_channel(channel):
    title = None
    language = None
    description = None
    link = None
    articles = []

    for node in channel:
        if node.tag == "title":
            title = node.text
        elif node.tag == "link":
            link = node.text
        elif node.tag == "language":
            language = node.text
        elif node.tag == "description":
            description = node.text
        elif node.tag == "item":
            articles.append(parse_item(node))
        else:
            print("%s element not handled" % node.tag)

    return dict(articles=articles, title=title, language=language, description=description, link=link)

def parse_xml(feed_uri):
    data = download_file(feed_uri)

    root_element = xml.etree.ElementTree.fromstring(data)
    contents = []
    if root_element.tag != "rss":
        raise NameError("The root element is not rss, it may be a html file")
    for channel in root_element:
        if channel.tag != "channel": # another node?? not valid, let's skip it
            print("Root element contains a node of type %s" % channel.tag)
        else:
            contents.append(parse_channel(channel))
    return contents
    

def add_feed(feed_name):
    if "://" not in feed_name:
        feed_name = "http://" + feed_name
    g.db.execute("insert into feeds (url, name) values (?, ?)", (feed_name,feed_name))
    g.db.commit()

def sync_feed(feedid):
    cur = g.db.execute("select name, url from feeds where id = " + str(feedid))
    row = cur.fetchall()[0]
    try:
        content = parse_xml(row[1])[0]
    except:
        # Hum, maybe it is not a feed :)
        try:
            from BeautifulSoup import BeautifulSoup
            import urllib2
            page = urllib2.urlopen(row[1])
            soup = BeautifulSoup(page)
            url = soup.find("link", {"type": "application/rss+xml"}).attrMap["href"]
            if "://" not in url:
                url = "/".join(row[1].split("/")[0:-1]) + "/" + url
            app.logger.debug("Switch to %s for %s" % (url, row[1]))
            g.db.execute("update feeds set url = (?) where id = " + str(feedid), (url,))
            g.db.commit()
            content = parse_xml(url)[0]
        except ImportError:
            g.db.execute("update feeds set name = (?) where id = " + str(feedid), ("Feed not valid, install beautifoul soup for autodetection",))
            g.db.commit()
            return
        except:
            g.db.execute("update feeds set name = (?) where id = " + str(feedid), ("Feed not valid, couldn't autodetect it :(",))
            g.db.commit()
            raise
            return
    app.logger.debug(content["title"])
    if content["title"] != row[0]:
        g.db.execute("update feeds set name = (?) where id = " + str(feedid), (content["title"],))
        g.db.commit()

    # We check wether each article is in the db
    for article in content["articles"]:
        # How many article with this id?
        cur = g.db.execute("select count(id) from articles where guid = (?) and feed = (?)", (article["guid"], feedid))
        count = cur.fetchall()[0][0]
        if count == 0:
            g.db.execute("insert into articles (name, url, guid, content, feed, pubDate, seen) values (?, ?, ?, ?, ?, ?, 0)", (article["title"], article["link"], article["guid"], article["description"], feedid, article["pubDate"]))
    g.db.commit()

@app.route("/ajax/feed/<int:feedid>/")
def ajax_feed(feedid):
    cur = g.db.execute("select name, id, pubDate, seen from articles where feed = " + str(feedid) + " order by articles.pubDate desc")
    subitems = [dict(subject=row[0], id=row[1], date=date_formater.format_date(row[2]), seen=row[3]) for row in cur.fetchall()]
    return jsonify(content=render_template("rss/rss-ajax-subitems.html", subitems=subitems, subitems_target="/ajax/article/"))

@app.route("/ajax/seen/<int:article>/<int:seen>")
def ajax_mark_seen(article, seen):
    #FIXME: investigate wether the int: is enough to avoid a sql injection, not sure right now
    g.db.execute("update articles set seen = " + str(seen) + " where id = " + str(article))
    g.db.commit()
    return jsonify(done=1)


@app.route("/ajax/feed/-1")
def ajax_unread():
    cur = g.db.execute("select articles.name, articles.id, articles.pubDate, articles.seen, feeds.name from articles, feeds where feeds.id = articles.feed and seen = 0 order by articles.pubDate desc")
    subitems = [dict(subject=row[0], id=row[1], date=date_formater.format_date(row[2]), seen=row[3], sender=row[4]) for row in cur.fetchall()]
    return jsonify(content=render_template("rss/rss-ajax-subitems.html", subitems=subitems, subitems_target="/ajax/article/"))

@app.route("/ajax/article/<int:article>/")
def ajax_article(article):
    cur = g.db.execute("select content, name, seen from articles where id = " + str(article))
    data = cur.fetchall()[0]
    if data[2] == 0:
        g.db.execute("update articles set seen = 1 where id = " + str(article))
        g.db.commit()
    return jsonify(content=data[0])

@app.route("/ajax/fullview/-1")
def ajax_full_view_unread():
    date_formater.init_date()
    cur = g.db.execute("select feeds.url, articles.name, articles.id, articles.content, articles.seen, feeds.name, articles.pubDate, articles.url, articles.feed from articles, feeds where feeds.id = articles.feed and seen = 0 order by articles.pubDate desc")
    feeds = [dict(sender=(row[1], row[5], row[7]), imapid=row[2], seen=row[4], body=row[3] + "<div class=\"clearer\"></div>", date=date_formater.format_date(row[6]), feedid=row[8]) for row in cur.fetchall()]
    return jsonify(content=render_template("rss/rss-ajax-thread.html", thread=feeds))

@app.route("/ajax/fullview/<int:article>/")
def ajax_full_view(article):
    date_formater.init_date()
    cur = g.db.execute("select feeds.url, articles.name, articles.id, articles.content, articles.seen, feeds.name, articles.pubDate, articles.url, articles.feed from articles, feeds where feeds.id = articles.feed and feeds.id = " + str(article) + " order by articles.pubDate desc")
    feeds = [dict(sender=(row[1], row[5], row[7]), imapid=row[2], seen=row[4], body=row[3] + "<div class=\"clearer\"></div>", date=date_formater.format_date(row[6]), feedid=row[8]) for row in cur.fetchall()]
    return jsonify(content=render_template("rss/rss-ajax-thread.html", thread=feeds))

@app.route("/sync/<int:feedid>/")
def sync(feedid):
    sync_feed(feedid)
    return "done"

def get_feed_list():
    cur = g.db.execute("select url, name, id from feeds")
    feeds = [dict(url=row[0], name=row[1], id=row[2]) for row in cur.fetchall()]
    for feed in feeds:
        cur = g.db.execute("select count(id) from articles where feed = " + str(feed["id"]) + " and seen = 0")
        feed["unread"] = cur.fetchall()[0][0]
    return feeds

@app.route("/sync")
def sync_all():
    cur = g.db.execute("select id from feeds")
    for row in cur.fetchall():
        sync_feed(row[0])
    # Get the feeds
    feeds = get_feed_list()
    return jsonify(done=1, content=render_template("rss/rss-ajax-firstpane.html", feeds=feeds))

@app.route("/", methods=["POST", "GET"])
def root():
    if request.form.has_key("new_feed"):
        add_feed(request.form["new_feed"])

    # Get the feeds
    feeds = get_feed_list()
    return render_template("rss/rss.html", feeds=feeds, sync_button="sync_all_rss()")

def init_db():
    with closing(sqlite3.connect(DATABASE)) as db:
        with app.open_resource('rss.sql') as f:
            db.cursor().executescript(f.read())
        db.commit()

if __name__ == "__main__":
    app.debug = True
    app.run(port=5001)
