import sqlite3
con = sqlite3.connect(r"C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db")
con.row_factory = sqlite3.Row

print("--- Blaby ENFORCEMENT SERVICES rows ---")
for r in con.execute("""select date, year_month, amount, expense_type, expense_area, source_file
                        from transactions where publisher='Blaby District Council'
                        and supplier_raw='ENFORCEMENT SERVICES' order by date"""):
    print(dict(r))

print("--- Bristol expense_type='Council Tax' all suppliers ---")
for r in con.execute("""select supplier_raw, count(*) t, round(sum(amount),2) g
                        from transactions where publisher='Bristol City Council'
                        and expense_type='Council Tax' group by supplier_raw order by g desc limit 15"""):
    print(dict(r))

print("--- JTR COLLECTIONS rows sign check ---")
for r in con.execute("""select publisher, substr(year_month,1,4) yr, expense_type, count(*) t,
                        round(sum(amount),2) g, sum(amount<0) nneg
                        from transactions where supplier_raw='JTR COLLECTIONS'
                        group by publisher, yr, expense_type"""):
    print(dict(r))

print("--- Civil Enforcement Agents / Quality Bailiffs / Able sign check ---")
for r in con.execute("""select supplier_raw, publisher, substr(year_month,1,4) yr, count(*) t,
                        round(sum(amount),2) g, sum(amount<0) nneg
                        from transactions where supplier_raw in
                        ('CIVIL ENFORCEMENT AGENTS LTD','Enforcement Bailiffs Ltd t/a Quality Bailiffs',
                         'Enforcement Bailiffs Ltd','Able Investigations and Enforcement Solutions Limited',
                         'CCS ENFORCEMENT SERVICES LTD','BAIL ENFORCEMENT AGENCY LTD','CAPITAL RESOLVE LTD')
                        group by supplier_raw, publisher, yr"""):
    print(dict(r))

print("--- Whyte & Co blank-expense years: which dataset/source ---")
for r in con.execute("""select expense_type, count(*) t, round(sum(amount),2) g, sum(amount<0) nneg
                        from transactions where publisher='Royal Borough of Greenwich'
                        and supplier_raw='WHYTE & CO' group by expense_type"""):
    print(dict(r))

print("--- Bristol Marston/B&S 2024 biggest contra pair check: same-day? ---")
for r in con.execute("""select date, amount, expense_type from transactions
                        where publisher='Bristol City Council' and supplier_raw='Bristow & Sutor'
                        and abs(amount)>14000 order by date limit 10"""):
    print(dict(r))
