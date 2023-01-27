import json
import pandas as pd
from dataclasses import dataclass
import typing
import datetime 
import requests
# @dataclass
# class Group:
#     groupID: int
#     groupShortName: str

# @dataclass
# class User:
#     userID: int
#     employeeID: str
#     nPI: str
#     firstName: str 
#     lastName: str

# @dataclass 

API_URL = 'https://www.shiftadmin.com/api_getscheduledshifts_json.php'
API_VALIDATION_KEY = 'UMICH_jrmacyu77w'
API_GID = 1
API_STRFTIME = '%Y-%m-%d'

def _json_to_df(data : dict) -> pd.DataFrame:
    df = pd.json_normalize(data['data']['scheduledShifts'])
    df['shiftStart'] = pd.to_datetime(df['shiftStart'])
    df['shiftEnd'] = pd.to_datetime(df['shiftEnd'])
    return df

def load_df_json_file(fn : str) -> pd.DataFrame: 
    with open(fn) as data_file:
        data = json.load(data_file)
    return _json_to_df(data)

class ShiftAdminException(Exception):
    pass

def load_df_api(start_date : datetime.date, end_date : datetime.date) -> pd.DataFrame:
    params = {'validationKey': API_VALIDATION_KEY, 'gid': API_GID, 
        'sd': start_date.strftime(API_STRFTIME), 'ed': end_date.strftime(API_STRFTIME)}
    r = requests.get(API_URL, params=params)
    data = r.json()
    # sanity check
    if (data['status'] == 'success') and (len(data['data']['scheduledShifts']) >= 1):
        return _json_to_df(data)
    else:
        raise ShiftAdminException('Shiftadmin API failure')


def full_df_to_rel(df : pd.DataFrame) -> typing.Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    '''Converts a giant long DF into a set of separate tables'''
    # Group
    groups_df = df[['groupID','groupShortName']].drop_duplicates().set_index('groupID').sort_index()
    # Users
    users_df = df[['userID','employeeID','nPI','firstName','lastName']].drop_duplicates().set_index('userID').sort_index()
    # Facilities
    facs_df = df[['facilityID','facilityExtID','facilityAbbreviation']].drop_duplicates().set_index('facilityID').sort_index()
    # Shifts
    shifts_df = df[['shiftID','shiftShortName','facilityID','groupID']]
    shifts_df = shifts_df.drop_duplicates().set_index('shiftShortName').sort_index()
    
    return groups_df, users_df, facs_df, shifts_df

if __name__ == '__main__':
    start_date = datetime.date.today()
    end_date = datetime.date.today() + datetime.timedelta(days=7)
    load_df_api(start_date, end_date)

    load_df_api(start_date, start_date)