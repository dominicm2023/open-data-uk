# 00_build_agg.py — one scan of the 11.8M-row corpus into a small per-(supplier_raw, publisher) aggregate.
# Everything downstream (variants, cross-body presence, flows) queries agg.db, never corpus.db again.
# Clean-set definition inherited from ../spending/compute_findings.py: is_dup=0 AND supplier_raw<>''.
import sqlite3, os, time

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "spending", "corpus.db")
AGG = os.path.join(HERE, "agg.db")

def main():
    if os.path.exists(AGG):
        os.remove(AGG)
    t0 = time.time()
    con = sqlite3.connect(AGG)
    con.execute("ATTACH DATABASE ? AS corpus", (CORPUS,))
    con.execute("""
        CREATE TABLE sp AS
        SELECT supplier_raw,
               publisher,
               COUNT(*)    AS txns,
               SUM(amount) AS gbp,
               MIN(year_month) AS first_ym,
               MAX(year_month) AS last_ym
        FROM corpus.transactions
        WHERE is_dup=0 AND supplier_raw<>''
        GROUP BY supplier_raw, publisher
    """)
    con.execute("CREATE INDEX ix_sp_raw ON sp(supplier_raw)")
    # Per-supplier rollup (across publishers)
    con.execute("""
        CREATE TABLE s AS
        SELECT supplier_raw,
               COUNT(*)  AS publishers,
               SUM(txns) AS txns,
               SUM(gbp)  AS gbp
        FROM sp GROUP BY supplier_raw
    """)
    con.execute("CREATE INDEX ix_s_raw ON s(supplier_raw)")
    con.commit()
    n_sp = con.execute("SELECT COUNT(*) FROM sp").fetchone()[0]
    n_s  = con.execute("SELECT COUNT(*) FROM s").fetchone()[0]
    tot  = con.execute("SELECT SUM(txns), SUM(gbp) FROM s").fetchone()
    print(f"sp rows (supplier x publisher): {n_sp:,}")
    print(f"distinct supplier_raw strings : {n_s:,}")
    print(f"clean txns {tot[0]:,}  gbp {tot[1]:,.2f}")
    print(f"built in {time.time()-t0:.1f}s -> {AGG}")
    con.close()

if __name__ == "__main__":
    main()
