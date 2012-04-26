drop table if exists feeds;
drop table if exists articles;
drop table if exists configuration;

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
create table configuration (
    key string,
    value string
);
insert into configuration (key, value) values ("view-mode", "1");
