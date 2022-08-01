import streamlit as st 

def display():
    html = '''
    <iframe src="https://forms.gle/vPYeavGhLnfpuX6QA" style="height: 85vh; width: 100%" />
    '''
    st.write(html, unsafe_allow_html=True)