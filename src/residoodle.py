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
def load_schedule(start_date : datetime.date, end_date : datetime.date):

    s = sched.load_sched_api(start_date, end_date, remove_nonum_hurley=True)

    return s

@st.experimental_memo
def get_helper_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    '''Load helper dataframes'''
    bd = sched.load_block_dates(cf.BLOCK_DATES_FN).set_index('Block')
    half_bd = sched.bd_to_half_blocks(bd)
    res = sched.load_residents(cf.RESIDENTS_FN)
    return bd, half_bd, res


# Load helper data
bd, half_bd, res = get_helper_data()
bd.index = [f'Block {b}' for b in bd.index]

DATE_FMT = "%m/%d/%y"

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


st.write(f'Selected dates: {start_date} to {end_date}')

block_start, block_end = sched.get_flanking_block_dates(half_bd, start_date, end_date)
st.write(f'Block dates {block_start} to {block_end}')

# load the schedule for the block dates flanking the selected start date/time
s = load_schedule(block_start, block_end) 
# add residents and block dates
s = sched.add_res_to_sched(s, res)
s = sched.add_bd_to_sched(s, bd)
s = s.dropna(subset=['PGY']) # filter out unknown (non-em) residents
s = s[s['Resident'].isin(sel_res)] # filter to selected residents
# get shift counts grouped by half-block and resident
scbrb = (s.groupby(['Resident','Block'])['Shift']
          .count()
          .reset_index()
          .pivot(index='Block', columns='Resident', values='Shift')
          .fillna(0.0)).T

s
scbrb

# Add special "OS" (off-service) shifts to those who aren't scheduled for a full block
to_concat = []
for blk in scbrb:
    os = scbrb.loc[scbrb[blk] == 0.0, blk].index.tolist()
    block_days = pd.date_range(half_bd.loc[blk, 'Start Date'], half_bd.loc[blk+0.5, 'Start Date'], freq='D')
    for res in os:
        for d in block_days:
            start = d
            end = d + pd.Timedelta(hours=23, minutes=59, seconds=59)
            to_concat.append({
                'Resident': res,
                'Block': blk,
                'Start': start,
                'Start Date': start.date(),
                'Start Hour': start.hour,
                'End': end,
                'End Date': end.date(),
                'End Hour': end.hour,
                'Shift': 'OS'
            })
s = pd.concat([s, pd.DataFrame(to_concat)], axis=0)
s

days = pd.date_range(start_date, end_date, freq='D')
days

for d in days:
    st.markdown(f'### {d}')
    itv_start = d + pd.Timedelta(hours=start_time.hour, minutes=start_time.minute)
    itv_end = d + pd.Timedelta(hours=end_time.hour, minutes=end_time.minute)

    s_for_day = s[['Resident','Shift','Start','End']]
    s_for_day = s_for_day[(s_for_day['Start'] >= d) & (s_for_day['Start'] <= (d + pd.Timedelta(hours=23, minutes=59, seconds=59)))]
    s_for_day['Overlap'] = s_for_day.apply(lambda r: ((itv_start <= r['Start'] <= itv_end) or (r['Start'] <= itv_start <= r['End'])), axis=1)
    
    sel_res_set = set(sel_res)
    identif_res_set = set(s_for_day['Resident'].unique())
    off_res_set = sel_res_set - identif_res_set

    off_to_add = [
        {'Resident': r,
         'Shift': 'Off',
         'Start': d,
         'End': d + pd.Timedelta(hours=23, minutes=59, seconds=59),
         'Overlap': False}
         for r in off_res_set
    ]
    s_for_day = pd.concat([s_for_day, pd.DataFrame(off_to_add)])

    st.markdown(f'Interval: {itv_start} to {itv_end}')
    st.dataframe(s_for_day)
    st.write(off_res_set)