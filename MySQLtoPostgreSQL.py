import streamlit as st
import os
import re
from openai import AzureOpenAI
import base64
from streamlit_javascript import st_javascript
import json  # Added for proper text escaping
import pyperclip
import pickle
from langchain_community.vectorstores.faiss import FAISS
from langchain_openai import AzureOpenAIEmbeddings
import sys

# Set page configuration
st.set_page_config(page_title="MySQL to PostgreSQL Converter", layout="wide")

from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Access the API key
api_key = st.secrets["API_KEY"]


@st.cache_resource
def load_vector_index(api_key):
    import pickle
    from faiss import read_index
    from langchain_community.docstore.in_memory import InMemoryDocstore
    from langchain_community.vectorstores.faiss import FAISS
    from langchain_openai import AzureOpenAIEmbeddings

    embeddings = AzureOpenAIEmbeddings(
        azure_deployment="text-embedding-ada-002",
        azure_endpoint="https://mysqltopostgresql.openai.azure.com/",
        openai_api_key=api_key,
        openai_api_version="2024-08-01-preview"
    )

    #index = read_index("sp_vector_index/index.faiss")
    #with open("sp_vector_index/index.pkl", "rb") as f:
    #    docs, index_to_docstore_id = pickle.load(f)


    base_path = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
    index_path = os.path.join(base_path, "sp_vector_index", "index.faiss")
    pkl_path = os.path.join(base_path, "sp_vector_index", "index.pkl")

    index = read_index(index_path)
    with open(pkl_path, "rb") as f:
        docs, index_to_docstore_id = pickle.load(f)
    

    docstore = InMemoryDocstore({str(i): doc for i, doc in enumerate(docs)})

    return FAISS(
        index=index,
        docstore=docstore,
        index_to_docstore_id=index_to_docstore_id,
        embedding_function=embeddings
    )



# Function to initialize OpenAI client
def initialize_openai_client(api_key):
    return AzureOpenAI(
        api_key=api_key,
        api_version="2024-08-01-preview",
        azure_endpoint="https://mysqltopostgresql.openai.azure.com/"
    )

# Function to check if input is a MySQL query
def is_mysql_query(input_str):
    query_patterns = [r'\bSELECT\b', r'\bINSERT\b', r'\bUPDATE\b', r'\bDELETE\b',
                      r'\bCREATE\b', r'\bALTER\b', r'\bDROP\b', r'\bTRUNCATE\b', r'\bCALL\b']
    return any(re.search(pattern, input_str, re.IGNORECASE) for pattern in query_patterns)


def find_similar_examples(query_text, api_key, top_k=2, threshold=0.75):
    vector_db = load_vector_index(api_key)
    results = vector_db.similarity_search_with_score(query_text, k=top_k)

    filtered = []
    for doc, score in results:
        similarity = 1 - score  # FAISS returns distance, lower = closer
        if similarity >= threshold:
            filtered.append(doc)
    return filtered



# Function to call OpenAI API
def call_api(client, prompt_text, wholespprompt, systemprompt):
    try:

        example_block = ""
        similar_docs = find_similar_examples(prompt_text, api_key)

        if similar_docs:
            for doc in similar_docs:
                example_block += (
                    f"-- MySQL Example:\n{doc.page_content}\n\n"
                    f"-- PostgreSQL Conversion:\n{doc.metadata['postgres']}\n\n"
                    f"---\n"
                )
        full_prompt = example_block + wholespprompt + "\n\n" + prompt_text

        ModelName = "gpt-4o"
        response = client.chat.completions.create(
            model=ModelName,
            messages=[{"role": "system", "content": systemprompt},
                      {"role": "user", "content": full_prompt}],
            max_tokens=12000,          
            temperature=0,          
        )
        return response.choices[0].message.content
    except Exception as e:
        return str(e)

# Initialize session state variables
if 'mysql_query' not in st.session_state:
    st.session_state.mysql_query = ""
if 'converted_query' not in st.session_state:
    st.session_state.converted_query = ""

# Sidebar for tool instructions
st.sidebar.title("ℹ️ Tool Info")

st.sidebar.markdown("""
- 🆕 Use only for **new** MySQL stored procedures  

- 🚫 Not for minor edits on existing SPs  

- 📄 **SPs only** — not for tables  

- 🧠 No DB connection → manual fixes like casting may be needed  

- ⚡ More accurate than general ChatGPT replies
""")




st.title("🛠️ MySQL to PostgreSQL AI Converter")
st.write("Paste your **MySQL Stored Procedure** or upload a **.sql file** to convert.")

# File Upload Handling
upload_file = st.file_uploader("Upload SQL File (optional)", type=["sql"])
if upload_file is not None:
    st.session_state.mysql_query = upload_file.getvalue().decode("utf-8")
else:
    st.session_state.mysql_query = ""

# User Input Text Area
mysql_query = st.text_area("Paste your MySQL Stored Procedure:", height=250, value=st.session_state.mysql_query, key="mysql_query_text")

# OpenAI Prompt and System Prompt
wholespprompt = """
Convert the following MySQL stored procedure to PostgreSQL **meticulously**, ensuring that:
- Every **line is converted** correctly.
- The **functionality remains identical** to MySQL.
- PostgreSQL best practices **are strictly followed**.

**STRICT OUTPUT FORMAT:** 
- **No additional text, explanations, or summaries.** 
- **Return only the converted PostgreSQL query.** 
- **Use "RETURNS TABLE" instead of "RETURNS VOID" when applicable.** 
- **Always use RETURN QUERY instead of PERFORM for returning result sets.**

**Conversion Rules:**
1. **Variable Declarations**: Convert MySQL `SET @varname = ''` to PostgreSQL `DECLARE var_varname TYPE; var_varname := '';`
2. **Function Naming**: Always use `CREATE OR REPLACE FUNCTION` instead of `CREATE PROCEDURE`.
3. **Data Types**:
   - Use `VARCHAR(n)` instead of `TEXT`.
   - If a column is `INT` or `INTEGER`, do **not** specify length.
4. **String Functions**:
   - Replace **IFNULL** with **COALESCE**.
   - Replace **UTC_TIMESTAMP** with **NOW()**.
   - Use **CONCAT_WS()** instead of `STRING_AGG()`, unless aggregation is explicitly required.
5. **Temporary Tables**:
   - PostgreSQL does not require `INDEX my_index_name`, remove it.
   - Do **not** include `PRIMARY KEY` when creating temporary tables—use `ALTER TABLE` after creation.
6. **Exception Handling**:
   - Always include an **exception block** at the end of the function for error logging.
   - Example:
     ```
     EXCEPTION
        WHEN OTHERS THEN
        DECLARE df_code TEXT;
        DECLARE df_msg TEXT;
        BEGIN
            GET STACKED DIAGNOSTICS df_code = RETURNED_SQLSTATE, df_msg = MESSAGE_TEXT;
            RAISE NOTICE 'Error in function ---> %', df_msg;
            INSERT INTO error_log (error_msg, sp_name, metadata, logutc)
            VALUES (df_msg, '{sp or function name}', {one parameter of sp or func}, NOW());
        END;
     ```
7. **Code Optimization**:
   - Remove redundant MySQL-specific commands (e.g., `DELIMITER ;;`).
   - Optimize `GROUP_CONCAT()` conversions where applicable.

---

### **Why This Works**
✅ **Enforces strict formatting & structure**  
✅ **Reduces unnecessary errors & inconsistencies**  
✅ **Ensures output is always PostgreSQL-compliant**  
✅ **Avoids common mistakes caused by randomness in API responses**  

---

"""

systemprompt = """You are a SQL conversion specialist. Your role is to convert MySQL queries into functionally equivalent PostgreSQL queries **with 100% accuracy**. 

Your response **must**:
- Ensure **syntactical correctness** in PostgreSQL.
- Maintain the **exact functionality** of the MySQL query.
- Strictly **follow PostgreSQL best practices** without unnecessary modifications.

**Rules to follow:**
1. **Do not modify logic unless necessary** for PostgreSQL compatibility.
2. **Do not add explanations, summaries, or formatting instructions**—return only the converted PostgreSQL query.
3. **Use correct PostgreSQL syntax and conventions** for data types, variables, and error handling.
4. **Ensure function consistency**—if a MySQL stored procedure contains a `SELECT` statement (not assigning to a variable), convert it to a PostgreSQL function returning a `TABLE`.

Output **must** be a valid **PostgreSQL function or procedure** without unnecessary comments."""


# Conversion Button
convert_clicked = st.button("🚀 Convert to PostgreSQL", use_container_width=True)

if convert_clicked:
    if not mysql_query.strip():
        st.warning("⚠️ Please enter a Proper MySQL query to convert.")
    elif not api_key.strip():
        st.warning("⚠️ Please enter your API key.")
    else:
        client = initialize_openai_client(api_key)
        with st.spinner("Converting your query..."):
            if is_mysql_query(mysql_query):
                # 🔍 Show message about vector search before conversion
                similar_docs = find_similar_examples(mysql_query, api_key)
                if similar_docs:
                    st.info(f"🧠 Injecting {len(similar_docs)} example(s) from your SP library to boost accuracy.")
                else:
                    st.warning("⚠️ No similar SPs found. GPT will run without example guidance.")

                # 🚀 Call GPT
                converted_query = call_api(client, mysql_query, wholespprompt, systemprompt)
                st.session_state.converted_query = converted_query
                st.success("✅ Conversion Completed!")
            else:
                st.warning("⚠️ The input doesn't seem like a valid MySQL query.")


# Function to copy text to clipboard
# ... [Keep all previous code unchanged until the copy_to_clipboard function] ...

# Modified copy_to_clipboard function
# ... [Keep all previous code unchanged until the copy_to_clipboard function] ...

# Modified copy function with better error handling
def copy_to_clipboard(text):
    try:
        # Copy text to clipboard using pyperclip
        pyperclip.copy(text)
        # Show a success toast message
        st.toast("Copied to clipboard!", icon="✅")
    except Exception as e:
        # Show an error toast message
        st.toast(f"Failed to copy text: {str(e)}", icon="❌")

# ... [Rest of the code remains unchanged] ...

# Display the converted query and copy button if available
if 'converted_query' in st.session_state and st.session_state.converted_query:
    st.text_area("Converted PostgreSQL Query:", st.session_state.converted_query, height=250, key="converted_query_text")
    if st.button("📋 Copy Converted Query"):
        copy_to_clipboard(st.session_state.converted_query)
