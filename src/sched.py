import streamlit as st 
import pandas as pd
import numpy as np 
import datetime

from schedutils import schedutils as sc
import config

def load_data():
    s_ical = sc.download_ical(config.CALENDAR_URL)
    sched = sc.ical_to_df(s_ical, 
        start=config.SCHED_ICAL_START_DATE, 
        end=config.SCHED_ICAL_END_DATE,
        tz=config.TZ)

    residents = sc.resident_df(config.RESIDENTS_CSV)

    blocks = sc.blocks_df(config.BLOCKS_CSV)

    return sched, residents, blocks

@st.experimental_memo
def load_and_preprocess_data():
    sched, res, blocks = load_data()
    sched = sc.get_final_sched(sched, blocks, res)
    return sched, res, blocks 

def display():
    '''Main entrypoint for sched page'''
    sched, res, blocks = load_and_preprocess_data()

    blurb = '''**Figure out when your coresidents will be off.** 

Choose the residents, a date range, and a time window when you want to plan your event.
This tool will automatically pull
the ShiftAdmin schedule and block schedule and calculate the best dates/times. 

*It\'s like a Doodle poll that fills itself out.*'''
    st.markdown(blurb)

    with st.expander('Options:', expanded=True):
        res_choices_holder = st.empty()
        default_resident_choices = []

        pgy_cols = st.columns(4)
        pgy_selected = [pgy_col.checkbox(f'PGY{i+1}s') for i, pgy_col in enumerate(pgy_cols)]
        for i, pgy in enumerate(pgy_selected):
            if pgy:
                default_resident_choices += res[res['year'] == (i+1)]['resident'].tolist()
        
        resident_choices = res_choices_holder.multiselect("Choose residents", res['resident'].tolist(), default=default_resident_choices)

        date_cols = st.columns(2)
        st_date = date_cols[0].date_input('Search between', key='st_date', 
            min_value=sched['start'].min(), max_value=sched['end'].max(),
            value=datetime.date.today())
        en_date_min_value = st_date
        en_date_min_value = sched['end'].min()
        en_date = date_cols[1].date_input('and ', key='en_date',
            min_value=st_date, max_value=sched['end'].max(),
            value=sched['end'].max())

        time_cols = st.columns(2)
        st_time = time_cols[0].time_input('for each day, show results only between the hours of', value=datetime.time(17,00))
        en_time = time_cols[1].time_input('and', key='en_time', value=datetime.time(22,00))
        
    # Make sure residents were selected
    if not len(resident_choices):
        st.info('Please select at least one resident above.')
        st.stop()

    # Clean UI inputs
    # Make the inputs timezone-aware
    start_dt = pd.Timestamp(st_date)
    start_dt = start_dt.tz_localize(config.TZ)
    end_dt = pd.Timestamp(en_date) + pd.Timedelta(86399, 's')
    end_dt = end_dt.tz_localize(config.TZ)

    # Filter the schedule
    fs = sc.filter_sched_dates(sched, start_dt, end_dt)
    fs = sc.filter_sched_residents(fs, resident_choices)
    # st.write(fs) # TODO remove

    # get the hourly shift info
    hdf = sc.hourly_shift_info(fs)

    # Calculate the free resident hours
    free_res_hrs = sc.free_resident_hours(sc.hourly_shifts_being_worked(hdf, st_time, en_time, start_dt, end_dt), len(resident_choices))

    # figure out the best dates
    best_dates = sc.best_dates(free_res_hrs)

    # display the best dates and who's off/on during them
    cols = st.columns(3)
    for i, bd in enumerate(best_dates):
        with cols[i]:
            met_str = 'Best Date' if not i else 'Next Best'
            st.metric(met_str, bd[0].strftime('%m/%d'), delta=f'Avg {bd[1]:.2f} residents free')

            working, partial, free, off = sc.working_free_for_date_time(sched, resident_choices, bd[0], st_time, en_time, config.TZ)
            ofpw = (off, free, partial, working)
            headers = ('Off', 'Free', 'Partially free', 'Working')
            for reslist, header in zip(ofpw, headers):
                st.markdown(f'**{header}**: ' + ', '.join([f'{res} ({shift})' for res, shift in reslist]))

    # display the free resident hours
    st.dataframe(free_res_hrs)
