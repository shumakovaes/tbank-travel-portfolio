from pathlib import Path
import argparse
import json
import sqlite3
import numpy as np
import pandas as pd
from .data import load_orders, SOURCE_COMMIT
from . import metrics
from .plots import make_figures
from .report import write_reports, experiment_sizes

ROOT=Path(__file__).resolve().parents[1]


def verify_sql(orders, tables):
    cols=['order_type_cd','created_dttm','nominal_price_rub_amt','is_success','valid_amount']
    with sqlite3.connect(':memory:') as con:
        orders[cols].to_sql('orders',con,index=False)
        sql=pd.read_sql_query((ROOT/'sql/product_summary.sql').read_text(encoding='utf-8'),con)
        ref=tables['product_summary'].set_index('product').loc[sql['product']]
        for col in ['orders','successful_orders','successful_booking_value_rub']:
            actual = pd.to_numeric(sql[col]).to_numpy(dtype=float, na_value=np.nan)
            expected = ref[col].to_numpy(dtype=float, na_value=np.nan)
            np.testing.assert_allclose(actual,expected,rtol=0,atol=.01,equal_nan=True)
        sql_month=pd.read_sql_query((ROOT/'sql/monthly_orders.sql').read_text(encoding='utf-8'),con)
        ref_month=tables['monthly_orders'][sql_month.columns].reset_index(drop=True)
        pd.testing.assert_frame_equal(sql_month,ref_month,check_dtype=False)
    return {'product_summary_sql_matches_pandas':True,'monthly_sql_matches_pandas':True}


def run(data_path, out_dir=None):
    out=Path(out_dir) if out_dir else ROOT/'reports'
    out.mkdir(parents=True,exist_ok=True)
    (out/'tables').mkdir(exist_ok=True)
    orders,quality=load_orders(data_path)
    retention,sizes=metrics.cohort_retention(orders)
    tables={'product_summary':metrics.summary(orders),'monthly_orders':metrics.monthly(orders),
            'hotel_lead':metrics.hotel_lead(orders),'cohort_retention':retention,
            'cohort_sizes':sizes.to_frame(),'cross_sell':metrics.cross_sell(orders),
            'destinations':metrics.destinations(orders),'promo_coverage':metrics.promo_coverage(orders)}
    baseline=tables['cross_sell'].set_index('window_days').loc[30,'cross_sell_share']
    tables['experiment_plan']=experiment_sizes(baseline)
    checks=verify_sql(orders,tables)
    checks['row_accounting']=quality['source_rows']==quality['orders']+quality['non_order_rows']
    if not checks['row_accounting']:
        raise AssertionError('Нарушен баланс строк')
    for name,frame in tables.items():
        frame.to_csv(out/'tables'/f'{name}.csv',index=name in ['cohort_retention','cohort_sizes'],encoding='utf-8-sig')
    (out/'quality.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest={'upstream_commit':SOURCE_COMMIT,'data':quality,'verification':checks,
              'versions':{'pandas':pd.__version__,'numpy':np.__version__}}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    figures=make_figures(tables,out/'figures')
    write_reports(tables,quality,figures,out)
    return tables,quality


def main():
    parser=argparse.ArgumentParser(description='Анализ бронирований Т-Банка на публичной учебной выборке')
    parser.add_argument('--data',type=Path,default=ROOT/'data/raw/dataset_travel.csv')
    parser.add_argument('--out',type=Path,default=ROOT/'reports')
    args=parser.parse_args()
    if not args.data.is_file():
        parser.error(f'Нет CSV: {args.data}. Выполните python scripts/download_data.py')
    _,q=run(args.data,args.out)
    print(f"Готово: {q['orders']} заказов. Отчёт: {args.out / 'report.html'}")


if __name__=='__main__':
    main()
