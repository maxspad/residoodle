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
    return sched, residents

def display():
    '''Main entrypoint for sched page'''
    sched, res = load_data()
    mystery_res = sched.loc[~np.isin(sched.resident, res.resident), :].resident.unique()
    st.write(mystery_res)