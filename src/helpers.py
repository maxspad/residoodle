import pandas as pd
from typing import Callable, Collection
import streamlit as st
import plotly.express as px

SITE_COLORS = ['#22577A','#754043','#B3BFB8']
SITE_COLORS_MAP = {s : c for s, c in zip(['UM','SJ','HMC'], SITE_COLORS)}
TOD_COLORS = ['#002629','#C5C9BB','#E6AF2E']
TOD_COLORS_MAP = {t : c for t, c in zip(['Night','Evening','Morning'], TOD_COLORS)}
PGY_COLORS = ['#C0C1D8','#7476AA','#474973','#161B33']
PGY_COLORS_MAP = {p : c for p, c in zip([1,2,3,4], PGY_COLORS)}

def two_by_two_plot(plot_func : Callable, df : pd.DataFrame, use_relative=False):
    cols = st.columns(2)
    for i, c in enumerate(cols):
        c.plotly_chart(plot_func(df, i+1, use_relative=use_relative), use_container_width=True)
    cols = st.columns(2)
    for i, c in enumerate(cols):
        c.plotly_chart(plot_func(df, i+3, use_relative=use_relative), use_container_width=True)

def res_type_cat_plot(df : pd.DataFrame, pgy : int, use_relative=False, max_shifts=None):
    max_shifts = df.groupby('Resident')['Start'].count().max()
    df_pgy = df[df['PGY'] == pgy].sort_values('Last Name', ascending=False)
    # rx = (0, max_shifts) if max_shifts is not None else None
    plt = px.histogram(df_pgy, y='Resident', color='Type', 
                orientation='h', category_orders={'Type': ['Night','Evening','Morning']},
                barnorm=('percent' if use_relative else None),
                title=f'Shifts by Time of Day: PGY {pgy}',
                color_discrete_sequence=['#002629','#C5C9BB','#E6AF2E'],
                range_x=(0, max_shifts))
    return plt

def res_site_cat_plot(df : pd.DataFrame, pgy : int, use_relative=False):
    df_pgy = df[df['PGY'] == pgy].sort_values('Last Name', ascending=False)
    plt = px.histogram(df_pgy, y='Resident', color='Site', 
                orientation='h', category_orders={'Site': ['UM','SJ','HMC']},
                barnorm=('percent' if use_relative else None),
                title=f'Shifts by Site: PGY {pgy}',
                color_discrete_sequence=['#22577A','#754043','#B3BFB8'])
    return plt

def res_shift_cat_plot(df : pd.DataFrame, pgy : int, use_relative=False):
    df_pgy = df[df['PGY'] == pgy].sort_values('Last Name', ascending=False)
    df_pgy = df_pgy[df['Site'] == 'UM']
    df_pgy['Area'] = df_pgy['Shift'].copy()
    df_pgy.loc[df_pgy['Area'].str.contains('EC3'), 'Area'] = 'EC3'
    df_pgy.loc[df_pgy['Area'].isin(['UT','UV','UW']), 'Area'] = 'STAR'
    df_pgy.loc[df_pgy['Area'].isin(['UR','UF']), 'Area'] = 'Float'
    df_pgy.loc[~df_pgy['Area'].isin(['EC3','STAR','Float']), 'Area'] = 'Main'
    plt = px.histogram(df_pgy, y='Resident', color='Area', 
                orientation='h', # category_orders={'Site': ['UM','SJ','HMC']},
                barnorm=('percent' if use_relative else None),
                title=f'Shift Allocations: PGY {pgy}')
                # color_discrete_sequence=['#22577A','#754043','#B3BFB8'])
    return plt

class CheckGroup:

    def __init__(self, values, labels : Collection[str], caption=None, horizontal=True):
        self._values = values
        self._labels = labels
        self._lab_to_val = {lab : val for lab, val in zip(labels, values)}
        if caption is not None:
            st.caption(caption)
        if horizontal:
            cols = st.columns(len(values))
        else:
            cols = [st]*len(values)
        self._check_res = {lab : c.checkbox(lab) for lab, c in zip(labels, cols)}

    def __getitem__(self, label): 
        return self._check_res[label]

    def get_selected(self):
        toRet = []
        for lab in self._check_res:
            if self._check_res[lab]:
                toRet.append(self._lab_to_val[lab])
        return toRet

