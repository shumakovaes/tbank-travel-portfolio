from pathlib import Path
from math import ceil, sqrt
from statistics import NormalDist
import base64
import html
import json
import pandas as pd


def experiment_sizes(baseline):
    rows = []
    for lift in (.1, .2, .3):
        p0, p1 = baseline, baseline*(1+lift)
        if not 0 < p0 < p1 < 1:
            continue
        mean = (p0+p1)/2
        za, zb = NormalDist().inv_cdf(.975), NormalDist().inv_cdf(.8)
        n = ceil((za*sqrt(2*mean*(1-mean)) + zb*sqrt(p0*(1-p0)+p1*(1-p1)))**2/(p1-p0)**2)
        rows.append({'relative_mde':lift,'baseline':p0,'target':p1,'clients_per_group':n,'total_clients':2*n})
    return pd.DataFrame(rows)


def num(x):
    return f'{x:,.0f}'.replace(',', ' ')


def write_reports(tables, quality, figures, out):
    out=Path(out)
    s=tables['product_summary'].set_index('product')
    cross=tables['cross_sell'].set_index('window_days').loc[30]
    m=tables['monthly_orders']
    full=m.loc[~m.exclude_from_full_month_comparison].groupby('month').orders.sum()
    peak=full.idxmax()
    p=tables['promo_coverage'].set_index('product').loc['HOT']
    start=quality['period_start'][:10]
    end=quality['period_end'][:10]
    bullets=[
        f"В выборке {num(quality['source_rows'])} строк и {num(quality['orders'])} заказов за {start} — {end}. {num(quality['non_order_rows'])} строк без типа заказа учитываются отдельно.",
        f"У {num(cross.hotel_clients)} из {num(cross.eligible_clients)} подходящих клиентов есть успешный заказ отеля в течение 30 дней после первой наблюдаемой успешной покупки авиабилета: {cross.cross_sell_share:.2%}. 95% интервал Wilson: {cross.wilson_lower:.2%}–{cross.wilson_upper:.2%}.",
        f"Для 30-дневного окна исключены {num(cross.excluded_short_followup)} клиентов с недостаточным сроком наблюдения и {num(cross.excluded_prior_or_same_time_hot)} клиентов с отелем до или одновременно с авиабилетом.",
        f"Доля SUC среди всех заказов: авиабилеты {s.loc['AIR','success_share_all']:.2%}, отели {s.loc['HOT','success_share_all']:.2%}. У {num(s.loc['HOT','missing_status'])} гостиничных заказов статус отсутствует. Среди известных статусов HOT доля SUC равна {s.loc['HOT','success_share_known']:.2%}; это другой знаменатель, а не улучшение конверсии.",
        f"Медианная цена успешного заказа: авиабилеты {num(s.loc['AIR','median_successful_booking_rub'])} ₽, отели {num(s.loc['HOT','median_successful_booking_rub'])} ₽. Точные значения без округления сохранены в CSV.",
        f"Максимум заказов среди полных наблюдаемых месяцев — {peak}: {num(full.max())}. Ноябрь неполный, декабрь отсутствует. Одного неполного года недостаточно для вывода об устойчивой сезонности.",
        f"У {num(p.missing_discount)} из {num(p.orders)} гостиничных заказов ({p.missing_discount/p.orders:.2%}) не заполнена скидка. Пропуск не означает отсутствие промокода; эффект скидок по этому срезу не оценивается.",
    ]
    method=[
        'Единица анализа — уникальный order_rk для строк AIR/HOT. Клиентские строки без типа заказа исключены из метрик бронирований. Повторяющиеся ID или некорректная дата создания останавливают расчёт.',
        'SUC используется как операционное определение успешного заказа, унаследованное из исходного проекта. Статусы отражают состояние в выгрузке; даты перехода в SUC отсутствуют. Полный справочник статусов не опубликован в проверенном описании.',
        'Сумма nominal_price_rub_amt для SUC — номинальная стоимость успешных бронирований. Это не комиссионная выручка, прибыль, ARPU или LTV банка. Финансовые возвраты и комиссия неизвестны.',
        'Для кросс-продажи выбран один якорь на клиента: дата первого наблюдаемого AIR со статусом SUC. HOT должен быть строго позже и не позднее конца окна. Ранее наблюдаемые HOT исключаются. Для каждого окна отдельно исключается неполное наблюдение; окна нельзя трактовать как одну кумулятивную кривую одной когорты.',
        'Конец наблюдения принят равным максимальной дате создания заказа в CSV. Это техническая граница выгрузки, не подтверждённая дата окончания сбора всех событий. Связь заказов с одной поездкой не установлена; история до января и покупки вне сервиса не наблюдаются.',
        'Когорты строятся по первой наблюдаемой SUC-покупке, а не по привлечению нового клиента. Retention M1 — доля клиентов когорты с SUC в следующем календарном месяце. M0 всегда 100%. Последний месяц исключён, будущие клетки остаются пустыми.',
        'Глубина бронирования отелей — разность календарных дат заезда и создания заказа. Время суток обнуляется, чтобы покупка в день заезда не становилась отрицательным lead time. Единого подтверждённого часового пояса нет; близкие к полуночи случаи требуют проверки источника.',
        'Для медианы и среднего используются только SUC с известной неотрицательной суммой. Выбросы не обрезаются. Интервалы Wilson относятся к клиентской доле кросс-продаж и не учитывают смещение отбора выборки.',
    ]
    experiment=[
        'Гипотеза: релевантный блок отелей после успешной покупки авиабилета увеличит долю клиентов, бронирующих отель в течение 30 дней.',
        'Единица рандомизации — клиент, распределение 50/50 с постоянным закреплением варианта. Включать один раз после первого подходящего AIR. Исключать уже бронировавших HOT по полной доступной истории; это более точное условие, чем доступное в учебной выборке.',
        'Контроль — текущий интерфейс, тест — блок отелей по месту назначения и датам, если они достоверно известны. Основная метрика: доля рандомизированных клиентов с успешной HOT-покупкой за 30 дней, анализ по назначенной группе (ITT).',
        'Порог решения фиксируется заранее: двусторонний α=0.05, мощность 80%, относительный MDE 20%. Окно наблюдения каждой группы — полные 30 дней. Не завершать тест досрочно по случайному достижению значимости.',
        'Защитные метрики: отмены и возвраты, обращения в поддержку, задержка страницы, отписки. Для бизнес-решения дополнительно нужны комиссия, маржа и стоимость стимула. Проверить SRM и корректность событий до оценки эффекта.',
        'Плановый размер выборки рассчитан приближением для двух независимых долей, без поправки на потери и последовательный просмотр. Исторический baseline служит ориентиром: период, eligibility и аудиторию будущего теста нужно сверить. Длительность набора зависит от реального подходящего трафика и здесь не заявляется.',
        'Это план эксперимента. A/B-тест на этих данных не проводился, рост конверсии и финансовый эффект не доказаны.',
    ]
    changes=[
        'Длинный Colab-скрипт заменён модулями загрузки, метрик, графиков и отчёта; запуск через CLI без ручного редактирования путей.',
        'Разделены строки клиентов и заказы; добавлены проверки ключей, дат, денежных значений и покрытия статусов.',
        'Уточнены финансовые определения; убраны выводы о выручке банка, LTV и декабрьском пике.',
        'Кросс-продажи пересчитаны с одним якорем на клиента, исключением ранних HOT и контролем полного окна.',
        'В когортной таблице различаются ноль повторных покупок и ещё не наблюдавшийся период.',
        'Добавлены SQL-запросы с автоматической сверкой против pandas, тесты граничных случаев, проверка SHA-256 и выполненный ноутбук.',
    ]
    sources=[
        ('Официальное описание набора DANO 2024–2025','https://dano.hse.ru/data2024'),
        ('Словарь полей Т-Банка','https://dano.hse.ru/mirror/pubs/share/987926897.pdf'),
        ('Исходный проект Дениса Морозова (Kor4yz)','https://github.com/Kor4yz/T-bank_analysis_hotels_and_air_travel'),
    ]
    title='Т-Банк: возможности кросс-продаж в путешествиях'
    sections=[('Что показали данные',bullets),('Определения и ограничения',method),('Следующий шаг: дизайн A/B-теста',experiment),('Что переработано',changes)]
    md=[f'# {title}', '', 'Учебный проект по публичной выборке. Переработка исходного анализа, без заявлений о работе в Т-Банке.', '']
    for heading,items in sections:
        md += [f'## {heading}', '']+[f'- {x}' for x in items]+['']
    md += ['## Источники','']+[f'- [{label}]({url})' for label,url in sources]
    md += ['',f"Версия исходных данных: `{quality['source_sha256']}`.", 'Расчёты и таблицы: `tables/`. Графики: `figures/`.']
    (out/'analysis.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    css='''body{margin:0;background:#f3f5f8;color:#203047;font:16px/1.65 system-ui,sans-serif}main{max-width:1080px;margin:auto;padding:42px 26px}h1{font-size:38px;line-height:1.2;max-width:850px}h2{margin-top:40px;font-size:25px}h3{font-size:18px}a{color:#3159b8}header{border-bottom:4px solid #178579;padding-bottom:24px}.eyebrow{letter-spacing:.12em;text-transform:uppercase;font-size:12px;color:#526273}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:28px 0}.card,figure{background:white;border:1px solid #dde3eb;border-radius:12px;padding:20px}.value{font-size:30px;font-weight:700}.muted,figcaption{color:#526273;font-size:14px}li{margin-bottom:12px}figure{margin:22px 0}figure img{width:100%;height:auto}.table{overflow:auto}table{border-collapse:collapse;width:100%;background:white;font-size:14px}th,td{text-align:right;padding:10px 12px;border-bottom:1px solid #e1e5ec}th:first-child,td:first-child{text-align:left}footer{margin-top:40px;border-top:1px solid #ccd5df;padding-top:20px;font-size:14px}@media(max-width:650px){main{padding:24px 16px}h1{font-size:29px}.cards{grid-template-columns:1fr}.card{padding:14px}}@media print{body{background:white}figure{break-inside:avoid}main{padding:0}h2{break-after:avoid}}'''
    body=f'<header><div class="eyebrow">Портфолио · продуктовая аналитика</div><h1>{title}</h1><p>Бронирования, повторные покупки и гипотеза «авиабилет → отель»</p><div class="muted">{start} — {end} · публичная учебная выборка · расчёты на Python и SQL</div></header>'
    body+='<div class="cards">'+''.join(f'<div class="card"><div class="muted">{label}</div><div class="value">{value}</div><div class="muted">{note}</div></div>' for label,value,note in [
        ('Заказов',num(quality['orders']),'AIR и HOT после проверки'),
        ('Кросс-продажа за 30 дней',f'{cross.cross_sell_share:.2%}',f'{num(cross.hotel_clients)} / {num(cross.eligible_clients)} клиентов'),
        ('Интервал Wilson, 95%',f'{cross.wilson_lower:.2%}–{cross.wilson_upper:.2%}','Статистическая неопределённость доли')])+'</div>'
    for heading,items in sections:
        body+=f'<section><h2>{heading}</h2><ul>'+''.join(f'<li>{html.escape(x)}</li>' for x in items)+'</ul></section>'
        if heading=='Что показали данные':
            captions=['Помесячные объёмы: неполный ноябрь выделен серым.','Статус SUC и стоимость успешного бронирования.','Глубина бронирования отелей и цена; n — число SUC-заказов.','Повторные покупки: пустые периоды не заменяются нулями.','В каждом окне используются только клиенты с полным сроком наблюдения.']
            for path,caption in zip(figures,captions):
                encoded=base64.b64encode(path.read_bytes()).decode('ascii')
                body+=f'<figure><img alt="{html.escape(caption)}" src="data:image/png;base64,{encoded}"><figcaption>{caption}</figcaption></figure>'
        if heading=='Следующий шаг: дизайн A/B-теста':
            t=tables['experiment_plan'].copy()
            for c in ['relative_mde','baseline','target']:
                t[c]=t[c].map(lambda v:f'{v:.2%}')
            t.columns=['Относительный MDE','Базовая доля','Целевая доля','Клиентов на группу','Всего клиентов']
            body+='<h3>Ориентир для размера выборки</h3><div class="table">'+t.to_html(index=False,border=0)+'</div>'
    body+='<footer><b>Источники</b><ul>'+''.join(f'<li><a href="{url}">{label}</a></li>' for label,url in sources)+'</ul><p>Переработка публичного учебного проекта. Коммерческий эффект и работа автора портфолио в Т-Банке не заявляются.</p></footer>'
    (out/'report.html').write_text(f'<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{css}</style><main>{body}</main></html>',encoding='utf-8')
    return bullets
