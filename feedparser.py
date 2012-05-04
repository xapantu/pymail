#import xml.etree.ElementTree as ET
import urllib
import time
import email.utils
import BeautifulSoup
from lxml import etree as ET

def download_file(uri):
    page = urllib.urlopen(uri)
    return page.read()

def read_file(uri):
    page = open(uri, "r")
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
            pubDate = email.utils.parsedate(node.text)
        elif node.tag == "guid":
            guid = node.text
        else:
            print("%s element not handled" % node.tag)

    return dict(title=title, link=link, description=description, updated_parsed=pubDate, id=guid)

def parse_channel(channel):
    title = None
    language = None
    description = None
    link = None
    articles = []
    parsed = {}
    parsed["feed"] = {}
    parsed["entries"] = []

    for node in channel:
        if node.tag == "title":
            parsed["feed"]["title"] = node.text
        elif node.tag == "link":
            parsed["feed"]["link"] = node.text
        elif node.tag == "language":
            parsed["feed"]["language"] = node.text
        elif node.tag == "description":
            parsed["feed"]["description"] = node.text
        elif node.tag == "item":
            parsed["entries"].append(parse_item(node))
        else:
            print("%s element not handled" % node.tag)

    return parsed

def parse_xml(feed_uri):
    data = download_file(feed_uri)

    #parser = ET.HTMLParser()

    root_element = ET.fromstring(data)
    if root_element.tag != "rss":
        return
        raise NameError("The root element is not rss, it may be a html file")
    for channel in root_element:
        if channel.tag != "channel": # another node?? not valid, let's skip it
            
            print("Root element contains a node of type %s" % channel.tag)
        else:
            return parse_channel(channel)
    return None

parse = parse_xml
