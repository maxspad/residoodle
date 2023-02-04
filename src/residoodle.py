import streamlit as st 

import datetime
import pandas as pd
import plotly.express as px
import plotly.io as pio

from typing import Tuple

import helpers as h
import config as cf
import schedexp as sched

pio.templates.default = 'seaborn'

@st.experimental_memo
def load_schedule(start_date : datetime.date, end_date : datetime.date, 
    bd : pd.DataFrame, res : pd.DataFrame, exclude_nonem: bool):

    se = sched.ScheduleExplorer(start_date, end_date, bd, res, 
        exclude_nonem=exclude_nonem)
    return se

@st.experimental_memo
def get_helper_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    '''Load helper dataframes'''
    bd = sched.load_block_dates(cf.BLOCK_DATES_FN).set_index('Block')
    res = sched.load_residents(cf.RESIDENTS_FN)
    return bd, res


# Load helper data
bd, res = get_helper_data()
bd.index = [f'Block {b}' for b in bd.index]

DATE_FMT = "%m/%d/%y"

# # Configure sidebar
# with st.sidebar:
#     bd_list = {f'Year to Date: {datetime.date(2022, 7, 1).strftime(DATE_FMT)} to {datetime.date.today().strftime(DATE_FMT)}': 'YTD', 'Custom Date Range': 'Custom'}
#     for b, r in bd.iterrows():
#         bd_list[f'{b}: {r["Start Date"].strftime(DATE_FMT)} to {r["End Date"].strftime(DATE_FMT)}'] = b

#     sel = st.selectbox('Choose a block or date range:', bd_list.keys())
#     sel_block = bd_list[sel]
#     if sel_block == 'YTD':
#         start_date = datetime.date(2022, 7, 1)
#         end_date = datetime.date.today()
#     elif sel_block == 'Custom':
#         start_date = st.date_input('Custom start date:', value=datetime.date(2022, 7, 1))
#         end_date = st.date_input('Custom end date:', value=datetime.date.today())
#     else:
#         start_date = bd.loc[sel_block,'Start Date']
#         end_date = bd.loc[sel_block,'End Date']
#     exclude_nonem = True # st.checkbox('Exclude off-service residents', value=True)

# # Download the shiftadmin data
# try:
#     se = load_schedule(start_date, end_date, bd, res, exclude_nonem)
#     print(se)
# except sched.ScheduleError:
#     st.error('End Date must come after Start Date')
#     st.stop()

# st.dataframe(se.shift_counts_by_res_and_block())
# res
with st.expander('Settings', expanded=True):
    cols = st.columns(2)
    with cols[0]:
        start_date = st.date_input('Start Date', value=datetime.date.today(),
            min_value=datetime.date.today(), max_value=datetime.date(2023,6,30))
        start_time = st.time_input('Start Time', value=datetime.time(17,0,0))
    with cols[1]:
        end_date = st.date_input('End Date', value=datetime.date.today() + datetime.timedelta(days=7),
            min_value=start_date, max_value=datetime.date(2023,6,30))
        end_time = st.time_input('End Time', value=datetime.time(22, 0, 0))

    if end_time < start_time:
        st.error('End time must be after start time.')
        st.stop()

    se = load_schedule(start_date, end_date, bd, res, True)
    msplc = st.empty()
    sel_res = msplc.multiselect('Choose residents:', res['Resident'].tolist())
    cg = h.CheckGroup([1,2,3,4], ['PGY1','PGY2','PGY3','PGY4'])
    sel_pgy = cg.get_selected()
    if len(sel_pgy):
        sel_res = msplc.multiselect('Choose residents', res['Resident'].tolist(),
            default=res[res['pgy'].isin(sel_pgy)]['Resident'].tolist())
    if not len(sel_res):
        st.info('Choose at least one resident.')
        st.stop()

st.write(se)
se.filter_residents(sel_res)
st.write(se)
blah = se.shift_counts_by_res_and_block()
blah

s = se.get_sched().sort_values('Start')
s
# s = se._s
# s.shape
# s = s[s['Resident'].isin(sel_res)]
# s.shape
# s
# blah = sched.bd_to_half_blocks(bd)
# blah = (blah - pd.to_datetime(start_date))['Start Date'].dt.total_seconds()
# blah = blah[blah <= 0]
# st.write(blah.idxmax())
# st.markdown(blah.reset_index().to_html(), unsafe_allow_html=True)
# # st.markdown(se._get_closest_block(start_date).reset_index().to_html(), unsafe_allow_html=True)