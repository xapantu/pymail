drop table if exists mails;
create table mails (
    id integer primary key autoincrement,
    subject string not null,
    account string not null,
    imapid id not null,
    thrid id not null,
    fulltext blob,
    encoding string,
    sender string,
    seen integer not null
);

drop table if exists threads;
create table threads (
    id integer primary key autoincrement,
    subject string not null,
    imapid id not null,
    account string not null,
    seen integer
);
