import streamlit as st
from streamlit.components.v1 import iframe
import config as cf

def run():
    iframe(cf.GOOGLE_FORM_URL, height=550, scrolling=True)