drop table if exists accounts;
create table accounts (
    id integer primary key autoincrement,
    name string not null
);

drop table if exists imapaccounts;
create table imapaccounts (
    id integer primary key autoincrement,
    accountid integer,
    email string not null,
    password string not null,
    host string not null
);
