import numpy as np
import pandas as pd
import pytest
from travel.data import prepare
from travel.metrics import cross_sell, cohort_retention, summary, wilson


def row(client, key, product='AIR', created='2024-01-01', status='SUC', price='100,0', start='2024-01-01'):
    return dict(client_rk=client,order_rk=key,order_type_cd=product,created_dttm=created,
                order_status_cd=status,nominal_price_rub_amt=price,book_start_dttm=start)


def prepared(rows):
    return prepare(pd.DataFrame(rows))[0]


def test_non_order_sentinel_does_not_pollute_denominator():
    orders,q=prepare(pd.DataFrame([row('a','x'),row('b','sentinel',None,None),row('c','sentinel',None,None)]))
    assert q['source_rows']==3 and q['non_order_rows']==2
    assert summary(orders).iloc[0].orders==1
    assert summary(orders).iloc[0].success_share_all==1


def test_duplicate_order_fails_instead_of_arbitrary_deduplication():
    with pytest.raises(ValueError,match='order_rk'):
        prepared([row('a','x'),row('a','x',status='ERR')])


def test_unknown_status_separate_and_money_success_only():
    o=prepared([row('a','1',price='1 200,50'),row('b','2',status=None,price='500,0'),row('c','3',status='ERR',price='900,0')])
    s=summary(o).iloc[0]
    assert s.missing_status==1
    assert s.success_share_all==pytest.approx(1/3)
    assert s.success_share_known==.5
    assert s.successful_booking_value_rub==1200.5


def test_calendar_lead_keeps_same_day_booking_at_zero():
    o=prepared([row('a','1','HOT','2024-01-01 20:00:00',start='2024-01-01 00:00:00')])
    assert o.lead_days.iloc[0]==0


def test_cross_sell_prior_same_time_repeated_air_and_censoring():
    o=prepared([
        row('a','1',created='2024-01-01'),row('a','2',created='2024-01-05'),
        row('a','3','HOT','2024-01-31'), # exactly 30 days: included once
        row('b','4',created='2024-01-01'),row('b','5','HOT','2024-02-01'), # 31 days
        row('c','6','HOT','2024-01-01'),row('c','7',created='2024-01-02'), # prior HOT
        row('d','8',created='2024-02-20'),row('d','9','HOT','2024-02-21'), # censored, even with event
        row('e','10',created='2024-01-01'),row('e','11','HOT','2024-01-01')]) # simultaneous
    r=cross_sell(o,windows=(30,),as_of='2024-03-01').iloc[0]
    assert r.air_clients==5
    assert r.excluded_prior_or_same_time_hot==2
    assert r.excluded_short_followup==1
    assert r.eligible_clients==2 and r.hotel_clients==1
    assert r.cross_sell_share==.5


def test_cohort_future_cells_missing_and_observed_zeros_zero():
    o=prepared([row('a','1',created='2024-01-02'),row('a','2',created='2024-03-05'),
                row('b','3',created='2024-02-01'),row('c','4',created='2024-04-03')])
    r,s=cohort_retention(o)
    assert r.loc['2024-01',0]==1 and r.loc['2024-01',1]==0 and r.loc['2024-01',2]==1
    assert np.isnan(r.loc['2024-02',2])
    assert '2024-04' not in r.index


def test_invalid_date_rejected():
    with pytest.raises(ValueError,match='датой'):
        prepared([row('a','1',created='bad-date')])


def test_empty_eligible_window_unavailable_not_zero():
    o=prepared([row('a','1',created='2024-01-01')])
    r=cross_sell(o,windows=(30,)).iloc[0]
    assert r.eligible_clients==0 and np.isnan(r.cross_sell_share)
    assert np.isnan(wilson(0,0)[0])


def test_negative_amount_excluded_without_dropping_order():
    o=prepared([row('a','1',price='-100'),row('b','2',price='200')])
    r=summary(o).iloc[0]
    assert r.orders==2 and r.successful_orders==2
    assert r.priced_successful_orders==1 and r.successful_booking_value_rub==200


def test_all_failed_money_is_unavailable():
    r=summary(prepared([row('a','1',status='ERR')])).iloc[0]
    assert pd.isna(r.successful_booking_value_rub)


def test_infinite_amount_excluded_without_dropping_order():
    o, q = prepare(pd.DataFrame([row('a','1',price='inf'),row('b','2',price='200')]))
    assert q['invalid_amount_orders'] == 1
    assert summary(o).iloc[0].successful_booking_value_rub == 200


def test_unknown_order_type_rejected_instead_of_counted_as_client_only():
    with pytest.raises(ValueError, match='тип'):
        prepared([row('a','1'),row('b','2',product='RAIL')])
