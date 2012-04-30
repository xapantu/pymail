
import xml.etree.ElementTree

def parse_xml(feed_uri):
    data = download_file(feed_uri)

    root_element = xml.etree.ElementTree.fromstring(data)
    contents = []
    if root_element.tag != "rss" and root_element.tag != "feed":
        raise NameError("The root element is not rss, it may be a html file")
    if root_element.tag == "rss":
        for channel in root_element:
            if channel.tag != "channel": # another node?? not valid, let's skip it
                print("Root element contains a node of type %s" % channel.tag)
            else:
                contents.append(parse_channel(channel))
    elif root_element.tag == "atom":
        contents.append(parse_root_atom(root_element))
    return contents
    
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

def parse_atom_item(item):
    title = None
    link = None
    description = None
    pubDate = None
    guid = None

    for node in item:
        if node.tag == "title":
            title = node.text
        elif node.tag == "link":
            link = node.get("href")
        elif node.tag == "content":
            description = node.text
        elif node.tag == "published":
            pubDate = time.strftime("%Y-%m-%d %H:%M:%S", email.utils.parsedate(node.text))
        elif node.tag == "id":
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

def parse_root_atom(channel):
    title = None
    language = None
    description = None
    link = None
    articles = []

    language = channel.get("xml:lang")
    for node in channel:
        if node.tag == "title":
            title = node.text
        elif node.tag == "link":
            link = node.get("href")
        elif node.tag == "description":
            description = node.text
        elif node.tag == "item":
            articles.append(parse_item(node))
        else:
            print("%s element not handled" % node.tag)

    return dict(articles=articles, title=title, language=language, description=description, link=link)
