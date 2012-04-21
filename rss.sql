drop table if exists feeds;
drop table if exists articles;

create table feeds (
    id integer primary key autoincrement,
    url string,
    name string
);

create table articles (
    id integer primary key autoincrement,
    feed integer,
    url string,
    guid string,
    pubDate string,
    seen integer,
    name string,
    content string
);
