drop table if exists mails;
create table mails (
    id integer primary key autoincrement,
    subject string not null,
    account string not null,
    imapid id not null,
    fulltext string,
    seen integer not null
);
