from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter, FuncFormatter
import numpy as np
from .metrics import LABELS

BLUE, TEAL, GREY = '#3159B8', '#178579', '#AEB8C4'


def make_figures(tables, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,
                         'axes.spines.right':False,'axes.titleweight':'bold','axes.titlesize':15,
                         'figure.facecolor':'white','axes.facecolor':'white','savefig.dpi':150})
    files = []
    def save(fig, name):
        fig.tight_layout(pad=1.5)
        path = out / f'{name}.png'
        fig.savefig(path, bbox_inches='tight')
        plt.close(fig)
        files.append(path)

    t = tables['monthly_orders']
    fig, ax = plt.subplots(figsize=(10,4.8))
    months = sorted(t.month.unique())
    for kind,color in [('AIR',BLUE),('HOT',TEAL)]:
        s = t.loc[t['product'].eq(kind)].set_index('month').reindex(months)
        ax.plot(range(len(months)),s.orders,marker='o',color=color,label=LABELS[kind])
    ax.axvspan(len(months)-1.5,len(months)-0.5,color=GREY,alpha=.22)
    ax.set(xticks=range(len(months)),xticklabels=months,ylabel='Заказы',title='Динамика бронирований')
    ax.tick_params(axis='x',rotation=40)
    ax.legend(frameon=False)
    fig.text(.02,-.01,'Последний месяц неполный; снижение в нём не интерпретируется как падение спроса.',fontsize=10,color='#526273')
    save(fig,'01_monthly')

    t = tables['product_summary']
    fig, axes = plt.subplots(1,2,figsize=(10,4.5))
    x = np.arange(len(t))
    axes[0].bar(x,t.success_share_all,color=[BLUE,TEAL])
    axes[0].set(xticks=x,xticklabels=[LABELS[k] for k in t['product']],ylim=(0,1.1),title='Доля SUC среди всех заказов')
    axes[0].yaxis.set_major_formatter(PercentFormatter(1))
    axes[1].bar(x,t.median_successful_booking_rub,color=[BLUE,TEAL])
    axes[1].set(xticks=x,xticklabels=[LABELS[k] for k in t['product']],ylabel='₽',title='Медиана цены SUC-заказа')
    for i,row in enumerate(t.itertuples()):
        axes[0].text(i,row.success_share_all+.025,f'{row.success_share_all:.1%}',ha='center')
        axes[1].text(i,row.median_successful_booking_rub*1.02,f'{row.median_successful_booking_rub:,.0f}'.replace(',',' '),ha='center')
    axes[1].margins(y=.18)
    save(fig,'02_products')

    t = tables['hotel_lead']
    fig, ax = plt.subplots(figsize=(10,4.6))
    ax.bar(t.lead_days,t.median_successful_booking_rub,color=TEAL)
    ax.set(xlabel='Календарных дней до заезда',ylabel='₽ за бронирование',title='Отели: медианная цена по глубине бронирования')
    for i,row in enumerate(t.itertuples()):
        ax.text(i,row.median_successful_booking_rub+120,f'n={row.successful_orders:,}'.replace(',',' '),ha='center',fontsize=10)
    ax.margins(y=.18)
    fig.text(.02,-.01,'Срез наблюдательный: цена зависит также от длительности, направления и состава заказа.',fontsize=10,color='#526273')
    save(fig,'03_hotel_lead')

    t = tables['cohort_retention']
    if not t.empty:
        fig, ax = plt.subplots(figsize=(10,6))
        cmap = plt.get_cmap('YlGnBu').copy()
        cmap.set_bad('#EDF1F5')
        im = ax.imshow(t.values*100,aspect='auto',cmap=cmap,vmin=0,vmax=25)
        for i in range(len(t)):
            for j in range(len(t.columns)):
                v=t.iloc[i,j]
                if np.isfinite(v):
                    ax.text(j,i,f'{v:.0%}' if j==0 else f'{v:.1%}',ha='center',va='center',fontsize=8,color='white' if v>.15 else '#24354A')
        ax.set(xticks=range(len(t.columns)),xticklabels=[f'M{c}' for c in t.columns],
               yticks=range(len(t)),yticklabels=t.index,title='Повторные покупки по месячным когортам',ylabel='Первая наблюдаемая SUC-покупка')
        fig.colorbar(im,ax=ax,label='Доля клиентов, % (шкала до 25%)')
        fig.text(.02,-.01,'M0 = 100% по определению. Серые клетки ещё не наблюдались; последний месяц исключён.',fontsize=10,color='#526273')
        save(fig,'04_retention')

    t=tables['cross_sell']
    fig, ax=plt.subplots(figsize=(10,4.6))
    y=t.cross_sell_share.to_numpy(dtype=float)
    ax.errorbar(np.arange(len(t)),y,yerr=np.vstack([y-t.wilson_lower.to_numpy(),t.wilson_upper.to_numpy()-y]),
                fmt='o',capsize=6,color=BLUE,markersize=8)
    ax.set(xticks=range(len(t)),xticklabels=[f'{d} дней' for d in t.window_days],
           ylabel='Доля клиентов с HOT после AIR',title='Кросс-продажа отеля после авиабилета')
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.set_ylim(0,max(t.wilson_upper.max()*1.4,.01))
    for i,row in enumerate(t.itertuples()):
        ax.text(i,row.wilson_upper+.001,f'{row.cross_sell_share:.2%}\nn={row.eligible_clients:,}'.replace(',',' '),ha='center',fontsize=10)
    fig.text(.02,-.01,'95% интервалы Wilson. В каждом окне своя база клиентов с полным сроком наблюдения.',fontsize=10,color='#526273')
    save(fig,'05_cross_sell')
    return files
