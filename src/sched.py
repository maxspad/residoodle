import streamlit as st 
import pandas as pd
import numpy as np 

from schedutils import schedutils as sc
import config

def load_data():
    s_ical = sc.download_ical(config.CALENDAR_URL)
    sched = sc.ical_to_df(s_ical, 
        start=config.SCHED_ICAL_START_DATE, 
        end=config.SCHED_ICAL_END_DATE,
        tz=config.TZ)

    residents = sc.resident_df(config.RESIDENTS_CSV)

    blocks = pd.read_csv('data/blocks.csv', parse_dates=[1,3])
    blocks.index.name = 'block_id'

    return sched, residents, blocks

def display():
    '''Main entrypoint for sched page'''
    sched, res, blocks = load_data()

    # filter schedule to only UM residents
    sched = sched.loc[np.isin(sched['resident'], res['resident']), :]
    
    scbb = sc.find_off_service(sched, blocks, res)
    st.write(scbb)
    st.write(sched)
    
    sched_entries = sc.get_final_sched(sched, blocks, res)
    st.write(sched_entries)
    # import datetime
    # print(scbb.loc[(datetime.date(2022,7,2), 'A Rimawi'), :])
    # for i, s in enumerate(scbb):
    #     st.header(blocks.loc[i, 'block'])
    #     st.write(s.sort_values('shift', ascending=True))