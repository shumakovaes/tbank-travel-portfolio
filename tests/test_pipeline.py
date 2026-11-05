import pandas as pd
import pytest

from travel.pipeline import run


@pytest.mark.parametrize('case', ['no_hotels', 'no_flights', 'no_successes', 'one_month', 'missing_hotel_dates', 'zero_cross_sell'])
def test_report_handles_sparse_data_without_nan_text(tmp_path, case):
    rows = [
        dict(client_rk='a', order_rk='1', order_type_cd='AIR', order_status_cd='SUC',
             created_dttm='2024-01-01', book_start_dttm='2024-01-01', nominal_price_rub_amt='100'),
        dict(client_rk='b', order_rk='2', order_type_cd='HOT', order_status_cd='SUC',
             created_dttm='2024-03-01', book_start_dttm='2024-03-01', nominal_price_rub_amt='200'),
    ]
    if case == 'no_hotels':
        rows[1]['order_type_cd'] = 'AIR'
    elif case == 'no_flights':
        rows[0]['order_type_cd'] = 'HOT'
    elif case == 'no_successes':
        for row in rows:
            row['order_status_cd'] = 'ERR'
    elif case == 'one_month':
        rows[1]['created_dttm'] = '2024-01-10'
    elif case == 'missing_hotel_dates':
        rows[1]['book_start_dttm'] = None
    data = tmp_path / 'input.csv'
    pd.DataFrame(rows).to_csv(data, sep=';', index=False)
    out = tmp_path / 'reports'
    tables, quality = run(data, out)
    assert quality['orders'] == 2
    assert (out / 'report.html').is_file()
    html = (out / 'report.html').read_text(encoding='utf-8')
    assert html.count('<figure>') == 5
    assert 'nan%' not in html.lower()
    report = (out / 'analysis.md').read_text(encoding='utf-8')
    assert 'nan' not in report.lower()
    assert 'Ноябрь' not in report
    assert 'декабрь' not in report
    assert tables['experiment_plan'].empty
    assert list(tables['experiment_plan'].columns) == [
        'relative_mde', 'baseline', 'target', 'clients_per_group', 'total_clients']
