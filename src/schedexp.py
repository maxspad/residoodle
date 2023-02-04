'''Module containing helper functions for working with the ShiftAdmin schedule'''

import json
import pandas as pd
from dataclasses import dataclass
import typing as t
import datetime 
import requests
import logging as log


_API_URL = 'https://www.shiftadmin.com/api_getscheduledshifts_json.php'
_API_VALIDATION_KEY = 'UMICH_jrmacyu77w'
_API_UM_GID = 1
_API_HMC_GID = 9
_API_STRFTIME = '%Y-%m-%d'

class ScheduleError(ValueError):
    pass


def load_sched_api(start_date : datetime.date, end_date : datetime.date,
    remove_nonum_hurley=True) -> pd.DataFrame:
    # Sanity check the dates
    if end_date < start_date:
        raise ScheduleError('End Date must come after Start Date')

    log.info('ShiftAdmin request for UM...')
    params = {'validationKey': _API_VALIDATION_KEY, 'gid': _API_UM_GID, 
        'sd': start_date.strftime(_API_STRFTIME), 'ed': end_date.strftime(_API_STRFTIME)}
    log.debug(f'Parameters: {params}')
    r = requests.get(_API_URL, params=params)
    log.debug(f'URL: {r.url}')
    data = r.json()
    df_um = _json_to_df(data)
    log.info(f'Done. Got {len(df_um)} shifts.')

    log.info('ShiftAdmin request for HMC...')
    params['gid'] = _API_HMC_GID
    log.debug(f'Parameters: {params}')
    r = requests.get(_API_URL, params=params)
    log.debug(f'URL: {r.url}')
    data = r.json()
    df_hmc = _json_to_df(data)
    log.info(f'Done. Got {len(df_hmc)} shifts')

    if remove_nonum_hurley:
        log.info('Removing non UM shifts from HMC schedule...')
        df_hmc = df_hmc[df_hmc['shiftShortName'].str.contains(' M')]
        log.info(f'{len(df_hmc)} shifts remaining')

    df = pd.concat([df_um, df_hmc])

    # Clean and add extra columns
    df = _postproc_df(df)

    return df

def load_df_json_file(fn : str) -> pd.DataFrame: 
    with open(fn) as data_file:
        data = json.load(data_file)
    return _postproc_df(_json_to_df(data))

def _postproc_df(df : pd.DataFrame) -> pd.DataFrame:
    df['Start'] = pd.to_datetime(df['shiftStart'])
    df['Start Date'] = df['Start'].dt.date
    df['Start Hour'] = df['Start'].dt.hour
    
    df['End'] = pd.to_datetime(df['shiftEnd'])
    df['End Date'] = df['End'].dt.date
    df['End Hour'] = df['End'].dt.hour

    df['Type'] = df['Start'].dt.hour.map(lambda x: 'Night' if x >= 20 else ('Evening' if x >= 11 else 'Morning'))
    
    df['Resident'] = df['firstName'].str[0] + ' ' + df['lastName']

    df.rename({
        'firstName': 'First Name',
        'lastName': 'Last Name',
        'groupShortName': 'Group',
        'facilityAbbreviation': 'Site',
        'shiftShortName': 'Shift',
        'shiftHours': 'Length'
    }, axis=1, inplace=True)

    df.drop(['employeeID','nPI','facilityExtID','shiftStart','shiftEnd'], inplace=True, axis=1)

    return df[['Resident','Shift','Site',
        'Start','End', 'Type', 'Length',
        'Start Date','Start Hour',
        'End Date', 'End Hour',
        'First Name', 'Last Name', 'userID',
        'facilityID','groupID','Group']]

def _json_to_df(data : dict) -> pd.DataFrame:
    # Check response
    if (data['status'] == 'success') and (len(data['data']['scheduledShifts']) >= 1):
        df = pd.json_normalize(data['data']['scheduledShifts'])
    else:
        raise ScheduleError('Shiftadmin API failure')
    return df

def add_res_to_sched(sched : pd.DataFrame, res : pd.DataFrame) -> pd.DataFrame:
    return (sched.merge(res[['userID','pgy']], how='left', on='userID')
                 .rename({'pgy' : 'PGY'}, axis=1))

def load_block_dates(fn : str) -> pd.DataFrame:
    bd = pd.read_csv(fn, parse_dates=['Start Date', 'End Date', 'Mid-transition Start Date'])
    bd.rename({'Mid-transition Start Date': 'Mid-Block Transition Date'}, axis=1, inplace=True)
    return bd

def load_residents(fn : str) -> pd.DataFrame:
    res = pd.read_csv(fn).reset_index()
    res['Resident'] = res['firstName'].str[0] + ' ' + res['lastName']
    return res

def bd_to_half_blocks(bd : pd.DataFrame):
    bd = bd.copy()
    bd.index = [i+1.0 for i in range(len(bd))]
    mids = bd[['Mid-Block Transition Date']]
    mids.index = [b+0.5 for b in bd.index]
    mids['Start Date'] = mids['Mid-Block Transition Date']
    bd = pd.concat([bd[['Start Date']], 
                    mids[['Start Date']],
                    pd.DataFrame({'Start Date': [pd.to_datetime(datetime.date(2023,6,30))]},
                                index=[14.0])
                    ], axis=0).sort_index()
    bd.index.name = 'Block'

    return bd    

def add_bd_to_sched(s : pd.DataFrame, bd : pd.DataFrame):
    s = s.copy()
    bd = bd.copy()
    bd = bd_to_half_blocks(bd)

    s['Block'] = -1
    for blk, r in bd.iloc[:-2, :].iterrows():
        s.loc[(s['Start Date'] >= r['Start Date']) & (s['Start Date'] < bd.loc[blk+0.5, 'Start Date']), 'Block'] = blk

    return s

class ScheduleExplorer:

    def __init__(self, start_date : datetime.date, end_date : datetime.date,
        block_dates : pd.DataFrame, residents : pd.DataFrame,
        exclude_nonem=True):

        self._bd = block_dates
        self._res = residents 
        self._exclude_nonem = exclude_nonem

        self._half_bd = bd_to_half_blocks(self._bd)
        delta_to_start = (self._half_bd - pd.to_datetime(start_date))['Start Date'].dt.total_seconds()
        delta_to_start = delta_to_start[delta_to_start <= 0]
        start_block = delta_to_start.idxmax()
        start_block_date = self._half_bd.loc[start_block, 'Start Date']
        delta_to_end = (self._half_bd - pd.to_datetime(end_date))['Start Date'].dt.total_seconds()
        delta_to_end = delta_to_end[delta_to_end >= 0]
        end_block = delta_to_end.idxmin()

        end_block_date = self._half_bd.loc[end_block, 'Start Date'] - pd.Timedelta('1d')

        self._start_date = start_date
        self._end_date = end_date

        self._start_block = start_block
        self._end_block = end_block

        self._start_block_date = start_block_date
        self._end_block_date = end_block_date

        self._s = load_sched_api(start_block_date, end_block_date)
        self._s = add_res_to_sched(self._s, self._res)
        if self._exclude_nonem:
            self._s = self._s.dropna(subset=['PGY'])
        self._s = add_bd_to_sched(self._s, self._bd)

    def filter_residents(self, sel_res : t.Collection[str]):
        self._s = self._s[self._s['Resident'].isin(sel_res)]
        
    def shift_counts_by_res_and_block(self):
        return (self._s.groupby(['Resident','Block'])['Shift']
                       .count()
                       .reset_index()
                       .pivot(index='Block', columns='Resident', values='Shift')
                       .fillna(0.0))

    def get_sched(self, add_offservice=True):
        if not add_offservice:
            return self._s
                  
        scbrb = self.shift_counts_by_res_and_block().T
        to_concat = []
        for blk in scbrb:
            no_shifts = scbrb[scbrb[blk] == 0.0][blk]
            no_shifts_res = no_shifts.index.tolist()
            for res_name in no_shifts_res:
                blk_start = self._half_bd.loc[blk, 'Start Date']
                blk_end = self._half_bd.loc[blk+0.5, 'Start Date']
                to_concat.append({
                    'Resident': res_name,
                    'Start': blk_start,
                    'End': blk_end,
                    'Shift': 'OS',
                    'Block': blk
                })
        toRet = pd.concat([self._s, pd.DataFrame(to_concat)])

        return toRet



    def __repr__(self):
        return f'Schedule Block {self._start_block} to Block {self._end_block} ({self._start_block_date} to {self._end_block_date}) with {len(self._s)} shifts'