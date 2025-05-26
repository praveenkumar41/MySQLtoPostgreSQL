import sys
import os

# This will trigger streamlit to run your app
if __name__ == "__main__":
    # Get path to current exe or script
    base_path = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__)
    os.chdir(base_path)

    # Run streamlit programmatically
    os.system(f'"{sys.executable}" -m streamlit run MySQLtoPostgreSQLfinalv1.py')
