# Intro to databases — fictional course notes

A database index helps locate rows without scanning an entire table. A B-tree index maintains sorted keys and supports equality and range lookups. Indexes consume storage and add work to inserts, updates, and deletes.

Transactions group operations into a single unit. Atomicity means all operations commit together or none do. Isolation controls how concurrent transactions observe one another. Durability means committed changes survive a restart.

A primary key uniquely identifies each row. A foreign key references a key in another table and enforces referential integrity. A left join preserves every row from its left input, including those without a matching right-side row.
