"""Flag cross-file duplicate transactions in corpus.db (is_dup=1).

The same payment can appear in several fetched resources: monthly CSVs plus
quarterly or annual roll-ups of the same period, or the same file attached to
two datasets. Key: (publisher, date, supplier_raw, amount, txn) — with txn
treated as '' when absent. Rows sharing a key across MORE THAN ONE source
file keep the copies in the first file seen (lowest rowid) and flag every
copy in other files. Duplicates within a single file are NOT flagged: the
Cabinet Office template splits one invoice into line items that can legally
repeat (same supplier, date, and amount, different line numbers).

Run after parse_corpus.py. Idempotent.
"""
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    con = sqlite3.connect(HERE / "corpus.db")
    con.execute("UPDATE transactions SET is_dup=0")
    con.execute("DROP TABLE IF EXISTS _dupkeys")
    # keys that span more than one source file; the first row seen (lowest
    # rowid) donates its file as the keeper
    con.execute("""
        CREATE TEMP TABLE _dupkeys AS
        SELECT t1.publisher, IFNULL(t1.date,'') AS d, t1.supplier_raw,
               t1.amount, IFNULL(t1.txn,'') AS t,
               t1.source_file AS keep_file
        FROM transactions t1 JOIN (
          SELECT MIN(rowid) AS r0 FROM transactions
          GROUP BY publisher, IFNULL(date,''), supplier_raw, amount,
                   IFNULL(txn,'')
          HAVING COUNT(DISTINCT source_file) > 1
        ) g ON t1.rowid = g.r0
    """)
    con.execute("CREATE INDEX _dk ON _dupkeys(publisher, d, supplier_raw, amount, t)")
    n = con.execute("""
        UPDATE transactions SET is_dup=1
        WHERE EXISTS (
          SELECT 1 FROM _dupkeys k
          WHERE k.publisher=transactions.publisher
            AND k.d=IFNULL(transactions.date,'')
            AND k.supplier_raw=transactions.supplier_raw
            AND k.amount=transactions.amount
            AND k.t=IFNULL(transactions.txn,'')
            AND k.keep_file<>transactions.source_file)
    """).rowcount
    con.commit()
    tot = con.execute("SELECT COUNT(*), ROUND(SUM(amount)/1e9,3) FROM transactions "
                      "WHERE is_dup=1").fetchone()
    print(f"flagged {n} cross-file duplicate rows = {tot[0]} rows, "
          f"£{tot[1]}bn")


if __name__ == "__main__":
    main()
