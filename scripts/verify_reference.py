"""Независимая сверка отчётных таблиц с исходным CSV без pandas и travel.*.

Запускать после pipeline на фиксированной исходной выборке.
"""
import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]


def read(path, delimiter=','):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream, delimiter=delimiter))


def verify(data, reports):
    raw = read(data, ';')
    orders = [r for r in raw if r['order_type_cd'] in ('AIR', 'HOT')]
    for row in orders:
        row['time'] = datetime.fromisoformat(row['created_dttm'])
    counts = Counter(r['order_type_cd'] for r in orders)
    successes = [r for r in orders if r['order_status_cd'] == 'SUC']
    for result in read(reports / 'tables/product_summary.csv'):
        product = result['product']
        chosen = [r for r in successes if r['order_type_cd'] == product]
        amounts = [Decimal(r['nominal_price_rub_amt'].replace(',', '.')) for r in chosen]
        assert int(result['orders']) == counts[product]
        assert int(result['successful_orders']) == len(chosen)
        assert Decimal(result['successful_booking_value_rub']) == sum(amounts)
        assert Decimal(result['median_successful_booking_rub']) == median(amounts)

    first_air, first_hot = {}, {}
    for row in sorted(successes, key=lambda r: r['time']):
        first = first_air if row['order_type_cd'] == 'AIR' else first_hot
        first.setdefault(row['client_rk'], row['time'])
    end = max(r['time'] for r in orders)
    cross_checks = []
    for result in read(reports / 'tables/cross_sell.csv'):
        days = int(result['window_days'])
        window = timedelta(days=days)
        prior = {c for c, t in first_air.items() if c in first_hot and first_hot[c] <= t}
        eligible = {c for c, t in first_air.items() if c not in prior and t + window <= end}
        converted = {c for c in eligible if c in first_hot and
                     first_air[c] < first_hot[c] <= first_air[c] + window}
        assert int(result['eligible_clients']) == len(eligible)
        assert int(result['hotel_clients']) == len(converted)
        assert int(result['excluded_prior_or_same_time_hot']) == len(prior)
        cross_checks.append((days, len(converted), len(eligible)))

    def month_index(time):
        return time.year * 12 + time.month - 1

    last_month = month_index(end)
    activity = defaultdict(set)
    for row in successes:
        month = month_index(row['time'])
        if month < last_month:
            activity[row['client_rk']].add(month)
    cohorts = defaultdict(set)
    for client, months in activity.items():
        cohorts[min(months)].add(client)
    for result in read(reports / 'tables/cohort_retention.csv'):
        label = next(iter(result.values()))
        cohort = month_index(datetime.fromisoformat(label + '-01'))
        clients = cohorts[cohort]
        for age, value in list(result.items())[1:]:
            month = cohort + int(age)
            if month >= last_month:
                assert value == ''
            else:
                expected = sum(month in activity[c] for c in clients) / len(clients)
                assert abs(float(value) - expected) < 1e-12
    print(f'Сверка пройдена: {len(orders)} заказов; продукты, суммы, медианы, когорты и AIR → HOT {cross_checks}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=ROOT / 'data/raw/dataset_travel.csv')
    parser.add_argument('--reports', type=Path, default=ROOT / 'reports')
    args = parser.parse_args()
    verify(args.data, args.reports)
