drop table if exists mails;
create table mails (
    id integer primary key autoincrement,
    subject string not null,
    account string not null,
    imapid id not null,
    fulltext blob,
    encoding string,
    sender string,
    seen integer not null
);
