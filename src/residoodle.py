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
    res : pd.DataFrame, exclude_nonem: bool):

    s = sched.load_sched_api(start_date, end_date)
    s = sched.add_res_to_sched(s, res)
    if exclude_nonem:
        s = s.dropna(subset=['PGY'])
    return s

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

# Configure sidebar
with st.sidebar:
    bd_list = {f'Year to Date: {datetime.date(2022, 7, 1).strftime(DATE_FMT)} to {datetime.date.today().strftime(DATE_FMT)}': 'YTD', 'Custom Date Range': 'Custom'}
    for b, r in bd.iterrows():
        bd_list[f'{b}: {r["Start Date"].strftime(DATE_FMT)} to {r["End Date"].strftime(DATE_FMT)}'] = b

    sel = st.selectbox('Choose a block or date range:', bd_list.keys())
    sel_block = bd_list[sel]
    if sel_block == 'YTD':
        start_date = datetime.date(2022, 7, 1)
        end_date = datetime.date.today()
    elif sel_block == 'Custom':
        start_date = st.date_input('Custom start date:', value=datetime.date(2022, 7, 1))
        end_date = st.date_input('Custom end date:', value=datetime.date.today())
    else:
        start_date = bd.loc[sel_block,'Start Date']
        end_date = bd.loc[sel_block,'End Date']
    exclude_nonem = True # st.checkbox('Exclude off-service residents', value=True)

# Download the shiftadmin data
try:
    s = load_schedule(start_date, end_date, res, exclude_nonem)
except sched.ScheduleError:
    st.error('End Date must come after Start Date')
    st.stop()

st.dataframe(bd)
bd.index = [i+1.0 for i in range(len(bd))]
mids = bd[['Mid-Block Transition Date']]
mids.index = [b+0.5 for b in bd.index]
mids['Start Date'] = mids['Mid-Block Transition Date']
bd = pd.concat([bd[['Start Date']], mids[['Start Date']]], axis=0).sort_index()
bd.index.name = 'Block'

s = s.set_index('Start').sort_index()
s['Block'] = -1
for blk, r in bd.iloc[:-1, :].iterrows():
    print(blk, blk + 0.5, r)
    s.loc[(s.index >= r['Start Date']) & (s.index < bd.loc[blk+0.5, 'Start Date']), 'Block'] = blk

blah = s.groupby(['Resident','Block'])['Shift'].count().reset_index()
blah = blah.pivot(index='Block', columns='Resident', values='Shift').fillna(0.0)
blah
# bd2 = bd.copy()
# bd['End Date'] = bd['Mid-Block Transition Date']
# bd.drop('Mid-Block Transition Date', inplace=True, axis=1)
# bd.index = [i + 1.0 for i in range(len(bd.index))]
# bd2['Start Date'] = bd2['Mid-Block Transition Date']
# bd2.drop('Mid-Block Transition Date', inplace=True, axis=1)
# bd2.index = [i + 1.5 for i in range(len(bd2.index))]
# bd = pd.concat([bd,bd2]).sort_index()
# st.dataframe(bd)
# # st.dataframe(bd2)
# st.dataframe(s)

# # bd.iloc[::2, :]
# s = s.set_index('Start').sort_index()
# st.dataframe(s)
# s['Block'] = ''
# for blk, r in bd.iterrows():
#     s.loc[(s.index >= r['Start Date']) & (s.index < (r['End Date'])), 'Block'] = blk

# st.dataframe(s)

# st.dataframe(s.groupby(['Block','Resident'])['Shift'].count())
