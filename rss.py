#! /usr/bin/env python2
# -*- coding: utf-8 -*-

from flask import Flask, render_template, session, request, redirect, url_for, jsonify, g
from contextlib import closing
import sqlite3
import xml.etree.ElementTree

app = Flask(__name__)
DATABASE = "rss/rss.sqlite"
DEBUG=True
SECRET_KEY="ah ah"
OFFLINE=False
app.config.from_object(__name__)

@app.before_request
def before_request():
    g.db = sqlite3.connect(app.config['DATABASE'])

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
            pubDate = node.text
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
    for channel in root_element:
        if channel.tag != "channel": # another node?? not valid, let's skip it
            print("Root element contains a node of type %s" % channel.tag)
        else:
            contents.append(parse_channel(channel))
    return contents
    

def add_feed(feed_name):
    g.db.execute("insert into feeds (url) values (?)", (feed_name,))
    g.db.commit()

def sync_feed(feedid):
    cur = g.db.execute("select name, url from feeds where id = " + str(feedid))
    row = cur.fetchall()[0]
    content = parse_xml(row[1])[0]
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
            g.db.execute("insert into articles (name, url, guid, content, feed) values (?, ?, ?, ?, ?)", (article["title"], article["link"], article["guid"], article["description"], feedid))
    g.db.commit()

@app.route("/ajax/feed/<int:feedid>/")
def ajax_feed(feedid):
    cur = g.db.execute("select content, name from articles where feed = " + str(feedid))
    content = ""
    for row in cur.fetchall():
        content += row[1] + "<br />" + row[0] + "<hr />"
    return content

@app.route("/sync/<int:feedid>/")
def sync(feedid):
    sync_feed(feedid)
    return "done"

@app.route("/", methods=["POST", "GET"])
def root():
    if request.form.has_key("new_feed"):
        add_feed(request.form["new_feed"])

    # Get the feeds
    cur = g.db.execute("select url, name from feeds")
    feeds = [dict(url=row[0], name=row[1]) for row in cur.fetchall()]
    return render_template("rss.html", feeds=feeds)

def init_db():
    with closing(sqlite3.connect(DATABASE)) as db:
        with app.open_resource('rss.sql') as f:
            db.cursor().executescript(f.read())
        db.commit()

if __name__ == "__main__":
    app.debug = True
    app.run()
