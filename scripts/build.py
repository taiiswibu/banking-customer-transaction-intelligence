"""One command rebuilds data, SQL answers, native report and offline preview."""
import argparse,time
from pathlib import Path
import pipeline, run_sql, build_powerbi, report, validate

def main():
    p=argparse.ArgumentParser();p.add_argument('--data-folder',help='Override absolute Power BI processed-data path (forward slashes recommended)')
    a=p.parse_args();started=time.perf_counter()
    pipeline.main();run_sql.main();build_powerbi.main(a.data_folder);report.main();validate.main()
    print(f'BUILD PASS in {time.perf_counter()-started:.1f}s. Open powerbi/Banking.pbip and select Refresh.')

if __name__=='__main__':main()
