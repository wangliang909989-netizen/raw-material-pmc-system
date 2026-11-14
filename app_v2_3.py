import io
import math
from datetime import date, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(page_title='原材料物控分析系统 V2.3', page_icon='📦', layout='wide')
st.title('📦 原材料物控分析系统')
st.caption('V2.3｜净需求 · 分批到货 · 库容约束 · IQC放行 · 缺料预警')
st.info('用于原材料计划模拟。到货不等于可用；只有IQC放行的合格数量才能参与投料。')

with st.expander('① 基础参数', expanded=True):
    material = st.text_input('原材料名称', '电解液')
    c1, c2 = st.columns(2)
    with c1:
        stock = st.number_input('初始合格库存(kg)', min_value=0.0, value=200.0, step=10.0)
        pending = st.number_input('初始待检库存(kg)', min_value=0.0, value=0.0, step=10.0)
        frozen = st.number_input('冻结库存(kg，仅展示，不计入可用)', min_value=0.0, value=0.0, step=10.0)
        safety = st.number_input('安全库存(kg)', min_value=0.0, value=50.0, step=10.0)
        capacity = st.number_input('合格品库容上限(kg，0表示不限)', min_value=0.0, value=300.0, step=10.0)
    with c2:
        moq = st.number_input('最小订货量MOQ(kg)', min_value=1.0, value=50.0, step=10.0)
        multiple = st.number_input('订货倍量(kg)', min_value=1.0, value=50.0, step=10.0)
        lead = st.number_input('采购提前期(自然日)', min_value=0, value=3)
        iqc_days = st.number_input('IQC检验周期(自然日)', min_value=0, value=2)
        start = st.date_input('分析开始日期', value=date.today())
        days = st.number_input('分析天数', min_value=1, max_value=90, value=7)

st.subheader('② 每日订单需求')
def default_orders():
    return pd.DataFrame([
        {'订单':'A订单','需求日期':start,'需求kg':100.0,'优先级':1},
        {'订单':'B订单','需求日期':start+timedelta(days=1),'需求kg':150.0,'优先级':2},
        {'订单':'C订单','需求日期':start+timedelta(days=2),'需求kg':120.0,'优先级':3},
    ])
orders = st.data_editor(default_orders(), num_rows='dynamic', hide_index=True, use_container_width=True,
    column_config={'需求日期':st.column_config.DateColumn('需求日期',format='YYYY-MM-DD'),
                   '需求kg':st.column_config.NumberColumn('需求kg',min_value=0),
                   '优先级':st.column_config.NumberColumn('优先级(1最高)',min_value=1,step=1)})

st.subheader('③ 已确认采购批次与IQC放行')
st.caption('仅填写已有可靠交付承诺的批次。计划到货日仅作跟踪；合格数量在放行日计入库存。')
receipts = st.data_editor(pd.DataFrame([{'批次':'采购批次1','计划到货日':start+timedelta(days=1),
    'IQC放行日':start+timedelta(days=3),'合格数量kg':200.0}]), num_rows='dynamic', hide_index=True,
    use_container_width=True,
    column_config={'计划到货日':st.column_config.DateColumn('计划到货日',format='YYYY-MM-DD'),
                   'IQC放行日':st.column_config.DateColumn('IQC放行日',format='YYYY-MM-DD'),
                   '合格数量kg':st.column_config.NumberColumn('合格数量kg',min_value=0)})

st.subheader('④ 初始待检库存')
release_pending = st.checkbox('计划在分析期内放行初始待检库存（仅用于模拟）')
pending_release_date = st.date_input('初始待检预计放行日', value=start) if release_pending else None
pending_qualified = st.number_input('初始待检预计合格量kg',min_value=0.0,max_value=float(pending),value=float(pending)) if release_pending else 0.0
carry_backlog = st.checkbox('未满足订单需求结转至后续日期',value=True)


def as_date(value):
    if pd.isna(value):
        return None
    return pd.Timestamp(value).date()


def round_order(qty, min_order, pack):
    if qty <= 1e-8:
        return 0.0
    return float(math.ceil((max(qty,min_order)-1e-8)/pack)*pack)


def run_analysis():
    horizon = [start+timedelta(days=i) for i in range(int(days))]
    clean_orders = []
    for i,r in orders.iterrows():
        d=as_date(r.get('需求日期'))
        q=r.get('需求kg')
        if d is None or pd.isna(q) or float(q)<0:
            raise ValueError(f'订单第{i+1}行的日期或需求量无效')
        p=r.get('优先级')
        if pd.isna(p) or float(p)<1:
            raise ValueError(f'订单第{i+1}行的优先级必须≥1')
        clean_orders.append({'订单':str(r.get('订单') or f'订单{i+1}'),'日期':d,'需求':float(q),'优先级':int(p),'序号':i})
    releases={d:0.0 for d in horizon}
    for i,r in receipts.iterrows():
        arrival=as_date(r.get('计划到货日'))
        release=as_date(r.get('IQC放行日'))
        qty=r.get('合格数量kg')
        if arrival is None or release is None or pd.isna(qty) or float(qty)<0:
            raise ValueError(f'采购批次第{i+1}行数据无效')
        if release<arrival:
            raise ValueError(f'采购批次第{i+1}行：IQC放行日不能早于到货日')
        if release in releases:
            releases[release]+=float(qty)
    if release_pending and pending_release_date in releases:
        releases[pending_release_date]+=pending_qualified
    backlog=[]
    balance=float(stock)
    rows=[]
    allocations=[]
    first_short=None
    first_safety=None
    for d in horizon:
        opening=balance
        incoming=releases[d]
        balance+=incoming
        todays=[o.copy() for o in clean_orders if o['日期']==d and o['需求']>0]
        queue=backlog+todays if carry_backlog else todays
        queue.sort(key=lambda o:(o['优先级'],o['日期'],o['序号']))
        total_due=sum(o['需求'] for o in queue)
        unmet=[]
        satisfied=0.0
        for o in queue:
            allocated=min(balance,o['需求'])
            balance-=allocated
            satisfied+=allocated
            left=o['需求']-allocated
            allocations.append({'日期':d,'订单':o['订单'],'原需求日期':o['日期'],
                '优先级':o['优先级'],'待分配需求kg':o['需求'],'分配kg':allocated,'未满足kg':left})
            if left>1e-8:
                o['需求']=left
                unmet.append(o)
        backlog=unmet if carry_backlog else []
        shortage=sum(o['需求'] for o in unmet)
        if shortage>1e-8 and first_short is None:
            first_short=(d,shortage)
        if balance<safety-1e-8 and first_safety is None:
            first_safety=d
        risk='缺料' if shortage>1e-8 else ('低于安全库存' if balance<safety-1e-8 else ('安全库存临界' if abs(balance-safety)<1e-8 else '正常'))
        rows.append({'日期':d,'期初合格kg':opening,'当日IQC放行kg':incoming,
                     '当日新增需求kg':sum(o['需求'] for o in todays),'参与分配需求kg':total_due,
                     '实际分配kg':satisfied,'当日未满足kg':shortage,'期末合格kg':balance,
                     '风险':risk,'库容超限kg':max(0.0,opening+incoming-capacity) if capacity>0 else 0.0})
    # A separate forward-planning simulation, starting from the same real confirmed supply.
    # New procurement must be released on/before demand date and cannot retroactively repair late demand.
    planned=[]
    planned_balance=float(stock)
    backlog_plan=[]
    first_infeasible=None
    for d in horizon:
        confirmed=releases[d]
        planned_balance+=confirmed
        due=[o.copy() for o in clean_orders if o['日期']==d and o['需求']>0]
        due=backlog_plan+due if carry_backlog else due
        need=sum(o['需求'] for o in due)
        earliest_release=start+timedelta(days=int(lead)+int(iqc_days))
        desired=max(0.0,need+safety-planned_balance)
        proposal=round_order(desired,moq,multiple)
        allowed=capacity-planned_balance if capacity>0 else float('inf')
        feasible=(d>=earliest_release)
        if proposal>0 and (not feasible or proposal>allowed+1e-8):
            if first_infeasible is None:
                first_infeasible=d
            status='不可按常规采购满足' if not feasible else 'MOQ/库容冲突'
            new_qty=0.0
        else:
            status='可安排' if proposal>0 else '无需新增'
            new_qty=proposal
        if new_qty>0:
            planned.append({'建议IQC放行日':d,'建议到货日':d-timedelta(days=int(iqc_days)),
                '最迟下单日':d-timedelta(days=int(iqc_days)+int(lead)),
                '建议订货kg':new_qty,'说明':'计划模拟，尚未确认供应商交付'})
            planned_balance+=new_qty
        due.sort(key=lambda o:(o['优先级'],o['日期'],o['序号']))
        outstanding=[]
        for o in due:
            served=min(planned_balance,o['需求'])
            planned_balance-=served
            if o['需求']-served>1e-8:
                o['需求']-=served
                outstanding.append(o)
        backlog_plan=outstanding if carry_backlog else []
        if status not in ('无需新增','可安排'):
            planned.append({'建议IQC放行日':d,'建议到货日':pd.NaT,'最迟下单日':pd.NaT,
                '建议订货kg':0.0,'说明':f'{status}：当日需求+安全库存缺口{desired:.2f}kg，需加急/调整批次/替代/改计划'})
    return pd.DataFrame(rows),pd.DataFrame(allocations),pd.DataFrame(planned),first_short,first_safety,first_infeasible

if st.button('开始物控分析',type='primary'):
    try:
        result,detail,plan,first_short,first_safety,first_infeasible=run_analysis()
        st.subheader('⑤ 每日滚动库存与风险')
        st.dataframe(result,use_container_width=True,hide_index=True)
        st.subheader('⑥ 订单优先级分配')
        st.dataframe(detail,use_container_width=True,hide_index=True)
        if first_short:
            st.error(f'首次缺料：{first_short[0]}，当日未满足需求 {first_short[1]:.2f} kg')
        else:
            st.success('在当前已确认供应和所选结转规则下，分析期内无缺料。')
        if first_safety:
            st.warning(f'首次低于安全库存：{first_safety}')
        if capacity>0 and (result['库容超限kg']>1e-8).any():
            st.error('已有放行批次可能造成库容超限；需调整放行/入库安排。')
        st.subheader('⑦ 新增采购分批建议（模拟）')
        st.caption('按当日需求+安全库存逐日试算，先扣除已确认放行批次；无法同时满足MOQ、库容及提前期时标注冲突，不虚构可行采购。')
        if not plan.empty:
            st.dataframe(plan,use_container_width=True,hide_index=True)
        else:
            st.success('无需新增采购。')
        if first_infeasible:
            st.warning(f'最早出现常规采购不可行或库容冲突的日期：{first_infeasible}。请协调采购、IQC、仓库和PC。')
        st.caption('假设：自然日提前期；当天放行可在当天投料前使用；仓库容量按合格品库存计算；尚未建模供应商产能、批量上限、日内时点和多物料共享库容。')
        output=io.BytesIO()
        with pd.ExcelWriter(output,engine='openpyxl') as writer:
            result.to_excel(writer,sheet_name='每日滚动库存',index=False)
            detail.to_excel(writer,sheet_name='订单分配',index=False)
            plan.to_excel(writer,sheet_name='采购分批建议',index=False)
            pd.DataFrame([{'原材料':material,'初始合格kg':stock,'初始待检kg':pending,'冻结kg':frozen,
                '安全库存kg':safety,'库容kg':capacity,'MOQkg':moq,'订货倍量kg':multiple,
                '采购提前期天':lead,'IQC天':iqc_days}]).to_excel(writer,sheet_name='参数',index=False)
        st.download_button('📥 下载Excel分析结果',data=output.getvalue(),
            file_name='原材料物控分析_V2.3.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except (ValueError,TypeError) as exc:
        st.error(f'输入数据需要检查：{exc}')