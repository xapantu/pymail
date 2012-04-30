import sqlalchemy

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Integer, String
Base = declarative_base()

class Feed(Base):
    __tablename__ = 'feeds'

    id = sqlalchemy.Column(Integer, primary_key=True)
    name = sqlalchemy.Column(String)
    url = sqlalchemy.Column(String)
    unread = 0

    def __init__(self, name, url):
        self.name = name
        self.url = url

    def __repr__(self):
        return "<Feed('%s', '%s', '%s')>" % (self.id, self.name, self.url)

class Keys(Base):
    __tablename__ = 'configuration'

    key = sqlalchemy.Column(String, primary_key=True)
    value = sqlalchemy.Column(String)

class Article(Base):
    __tablename__ = 'articles'
    id = sqlalchemy.Column(Integer, primary_key=True)
    name = sqlalchemy.Column(String)
    url = sqlalchemy.Column(String)
    guid = sqlalchemy.Column(String)
    pubDate = sqlalchemy.Column(String)
    feed = sqlalchemy.Column(Integer)
    seen = sqlalchemy.Column(Integer)
    content = sqlalchemy.Column(Integer)

class FeedsDatabase(object):
    def __init__(self):
        self.engine = sqlalchemy.create_engine("sqlite:///rss/rss.sqlite")
        self.Session = sqlalchemy.orm.sessionmaker(bind=self.engine)
        self.session = self.Session()

    def get_all_feeds(self):
        return self.session.query(Feed).all()

    def get_conf(self, value):
        return self.session.query(Keys).filter_by(key=value).first().value

    # Deprecated
    def get_articles_for_feed(self, feedid):
        return self.session.query(Article, Feed).filter(Article.feed==Feed.id).\
                filter_by(feed=feedid).order_by(sqlalchemy.sql.expression.desc(Article.pubDate)).all()
