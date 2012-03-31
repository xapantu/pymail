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
    receiver string,
    date string,
    seen integer not null,
    mailbox string not null
);

drop table if exists threads;
create table threads (
    id integer primary key autoincrement,
    subject string not null,
    imapid id not null,
    account string not null,
    mailbox string not null,
    seen integer
);
