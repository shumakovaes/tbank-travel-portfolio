from math import sqrt
import numpy as np
import pandas as pd

LABELS = {'AIR': 'Авиабилеты', 'HOT': 'Отели'}


def wilson(successes, total, z=1.959963984540054):
    """95% интервал Wilson для доли клиентов; это не оценка причинного эффекта."""
    if not total:
        return np.nan, np.nan
    p = successes / total
    den = 1 + z*z/total
    center = (p + z*z/(2*total)) / den
    half = z * sqrt(p*(1-p)/total + z*z/(4*total*total)) / den
    return max(0, center-half), min(1, center+half)


def summary(orders):
    records = []
    for kind, g in orders.groupby('order_type_cd', sort=True):
        money = g.loc[g.is_success & g.valid_amount, 'nominal_price_rub_amt']
        known = int(g.status_known.sum())
        successes = int(g.is_success.sum())
        records.append({'product': kind, 'orders': len(g), 'clients': g.client_rk.nunique(),
                        'successful_orders': successes, 'missing_status': len(g)-known,
                        'success_share_all': successes/len(g),
                        'success_share_known': successes/known if known else np.nan,
                        'priced_successful_orders': len(money),
                        'successful_booking_value_rub': money.sum(min_count=1),
                        'mean_successful_booking_rub': money.mean(),
                        'median_successful_booking_rub': money.median()})
    return pd.DataFrame(records)


def monthly(orders):
    rows = []
    last_month = orders.month.max()
    for (month, kind), g in orders.groupby(['month', 'order_type_cd'], sort=True):
        rows.append({'month': str(month), 'product': kind, 'orders': len(g),
                     'successful_orders': int(g.is_success.sum()),
                     'successful_booking_value_rub': g.loc[g.is_success & g.valid_amount, 'nominal_price_rub_amt'].sum(min_count=1),
                     'exclude_from_full_month_comparison': month == last_month})
    return pd.DataFrame(rows)


def hotel_lead(orders):
    g = orders.loc[orders.order_type_cd.eq('HOT') & orders.lead_days.ge(0)].copy()
    bins = [-1, 0, 3, 7, 14, 30, np.inf]
    labels = ['0', '1–3', '4–7', '8–14', '15–30', '31+']
    g['lead_bucket'] = pd.cut(g.lead_days, bins=bins, labels=labels)
    rows = []
    for bucket, s in g.groupby('lead_bucket', observed=True):
        money = s.loc[s.is_success & s.valid_amount, 'nominal_price_rub_amt']
        rows.append({'lead_days': str(bucket), 'orders': len(s), 'successful_orders': int(s.is_success.sum()),
                     'success_share_all': s.is_success.mean(), 'missing_status': int((~s.status_known).sum()),
                     'median_successful_booking_rub': money.median(),
                     'mean_successful_booking_rub': money.mean()})
    return pd.DataFrame(rows)


def cohort_retention(orders):
    """Месячные когорты первой НАБЛЮДАЕМОЙ SUC-покупки.

    Последний месяц не используется. Ещё не наступившие периоды остаются NaN.
    M0 включает первую покупку, повторные покупки измеряются начиная с M1.
    """
    last_month = orders.month.max()
    g = orders.loc[orders.is_success & (orders.month < last_month)].copy()
    if g.empty:
        return pd.DataFrame(), pd.Series(dtype='int64', name='clients')
    first = g.groupby('client_rk').month.min().rename('cohort')
    g = g.join(first, on='client_rk')
    g['age_month'] = g.month.astype('int64') - g.cohort.astype('int64')
    sizes = first.value_counts().sort_index().rename('clients')
    counts = g.groupby(['cohort','age_month']).client_rk.nunique().unstack()
    max_age = int((last_month-1).ordinal - sizes.index.min().ordinal)
    retention = counts.reindex(index=sizes.index, columns=range(max_age+1)).fillna(0).div(sizes, axis=0)
    for cohort in retention.index:
        for age in retention.columns:
            if cohort + int(age) >= last_month:
                retention.loc[cohort, age] = np.nan
    retention.index = retention.index.astype(str)
    sizes.index = sizes.index.astype(str)
    return retention, sizes


def cross_sell(orders, windows=(7, 30, 60), as_of=None):
    """Доля новых для HOT клиентов с HOT после первой наблюдаемой SUC AIR.

    На клиента один якорь. Исключены уже имевшие HOT, включая совпадающее время.
    Для каждого окна включены только клиенты с полностью наблюдаемым окном.
    Считаем даты создания заказов, чей статус в выгрузке SUC.
    """
    end = pd.Timestamp(as_of) if as_of is not None else orders.created_dttm.max()
    g = orders.loc[orders.is_success & orders.created_dttm.le(end)]
    air = g.loc[g.order_type_cd.eq('AIR')].groupby('client_rk').created_dttm.min().rename('air_time')
    hot = g.loc[g.order_type_cd.eq('HOT')].groupby('client_rk').created_dttm.min().rename('hotel_time')
    joined = pd.concat([air, hot], axis=1).dropna(subset=['air_time'])
    prior = joined.hotel_time.notna() & joined.hotel_time.le(joined.air_time)
    new_hot = joined.loc[~prior].copy()
    rows = []
    for days in windows:
        if days <= 0:
            raise ValueError('Окно должно быть положительным')
        eligible = new_hot.loc[new_hot.air_time.le(end - pd.Timedelta(days=days))]
        delta = eligible.hotel_time - eligible.air_time
        hit = int((delta.gt(pd.Timedelta(0)) & delta.le(pd.Timedelta(days=days))).sum())
        n = len(eligible)
        lower, upper = wilson(hit, n)
        rows.append({'window_days': days, 'air_clients': len(joined),
                     'excluded_prior_or_same_time_hot': int(prior.sum()),
                     'eligible_clients': n, 'excluded_short_followup': len(new_hot)-n,
                     'hotel_clients': hit, 'cross_sell_share': hit/n if n else np.nan,
                     'wilson_lower': lower, 'wilson_upper': upper})
    return pd.DataFrame(rows)


def destinations(orders):
    tables = []
    for kind, field in [('HOT','hotel_city'), ('AIR','avia_arr_city')]:
        g = orders.loc[orders.is_success & orders.order_type_cd.eq(kind) & orders[field].notna()]
        t = g.groupby(field).agg(successful_orders=('order_rk','size')).reset_index().rename(columns={field:'destination'})
        t['product'] = kind
        tables.append(t.sort_values(['successful_orders','destination'], ascending=[False,True]).head(10))
    return pd.concat(tables, ignore_index=True)


def promo_coverage(orders):
    rows = []
    for kind, g in orders.groupby('order_type_cd'):
        d = g.promo_code_discount_amt
        rows.append({'product':kind,'orders':len(g),'missing_discount':int(d.isna().sum()),
                     'zero_discount':int(d.eq(0).sum()),'positive_discount':int(d.gt(0).sum()),
                     'negative_discount':int(d.lt(0).sum())})
    return pd.DataFrame(rows)
