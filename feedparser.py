#import xml.etree.ElementTree as ET
from lxml import etree as ET
import urllib
import time
import email.utils
import rfc3339

def download_file(uri):
    print "Download file..."
    page = urllib.urlopen(uri)
    print "Connected, retrieving..."
    return page.read()

def read_file(uri):
    page = open(uri, "r")
    return page.read()

def parse_item(item, is_rss):
    title = None
    link = None
    description = None
    pubDate = None
    guid = None
    content_tag = "description" if is_rss else "content"
    id_tag = "guid" if is_rss else "id"

    for node in item:
        node.tag = node.tag.split("}")[-1] # dirty hack, FIXME (it avoids ns issues)
        if node.tag == "title":
            title = node.text
        elif node.tag == "link":
            if is_rss:
                link = node.text
            elif node.attrib.has_key("href"):
                link = node.attrib["href"]
        elif node.tag == content_tag:
            description = node.text
        elif is_rss and node.tag == "pubDate":
            pubDate = email.utils.parsedate(node.text)
        elif not is_rss and node.tag =="updated":
            pubDate = rfc3339.parse_datetime(node.text).timetuple()
        elif node.tag == id_tag:
            guid = node.text
        else:
            print("%s element not handled" % node.tag)

    return dict(title=title, link=link, description=description, updated_parsed=pubDate, id=guid)

def parse_channel_rss(channel, is_rss = True):
    title = None
    language = None
    description = None
    link = None
    articles = []
    parsed = {}
    parsed["feed"] = {}
    parsed["entries"] = []

    article_node_tag = "item" if is_rss else "entry"

    for node in channel:
        node.tag = node.tag.split("}")[-1] # dirty hack, FIXME (it avoids ns issues)
        if node.tag == "title":
            parsed["feed"]["title"] = node.text
        elif node.tag == "link":
            parsed["feed"]["link"] = node.text
        elif node.tag == "language":
            parsed["feed"]["language"] = node.text
        elif node.tag == "description":
            parsed["feed"]["description"] = node.text
        elif node.tag == article_node_tag:
            parsed["entries"].append(parse_item(node, is_rss))
        else:
            print("%s element not handled" % node.tag)

    return parsed

def extract_rss_atom_link(data):
    root = ET.HTML(data)
    head = root.find("head")
    if head is not None:
        links = head.findall("link")
        for link in links:
            if link.attrib["type"] == "application/atom+xml" or link.attrib["type"] == "application/rss+xml":
                return link.attrib["href"]

def parse_xml(feed_uri):
    data = download_file(feed_uri)
    url = feed_uri
    print "feed downloaded %s" % feed_uri

    #parser = ET.HTMLParser()

    try:
        root_element = ET.fromstring(data)
    except ET.XMLSyntaxError:
        # Maybe it is an html file.
        try:
            url = extract_rss_atom_link(data)
            if url is None:
                raise
            root_element = ET.fromstring(download_file(url))
        except ET.XMLSyntaxError:
            print("Couldn't use this url %s", feed_uri)
            raise

    tag_name = root_element.tag.split("}")[-1] # dirty hack, FIXME (it avoids ns issues)
    if tag_name == "rss":
        for channel in root_element:
            if channel.tag != "channel": # another node?? not valid, let's skip it
                
                print("Root element contains a node of type %s" % channel.tag)
            else:
                data = parse_channel_rss(channel)
                data["url"] = url
                return data
    elif tag_name == "feed":
        data = parse_channel_rss(root_element, False)
        data["url"] = url
        return data
    else:
        raise NameError("The root element is not rss (it is %s), it may be a html file" % root_element.tag)
    return None

parse = parse_xml
