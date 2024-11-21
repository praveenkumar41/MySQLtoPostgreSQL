import streamlit as st
import os
import tiktoken
import re
from openai import AzureOpenAI

# Initialize AzureOpenAI client
def initialize_openai_client(api_key):
    return AzureOpenAI(
    api_key=api_key,  
    api_version="2023-05-15",
    azure_endpoint="https://mysqltopostgresql.openai.azure.com/"
)

def count_tokens(encoder,text):
    tokens = encoder.encode(text)
    token_count = len(tokens)
    return token_count    


def is_mysql_query(input_str):
    # Regular expressions to match common MySQL query patterns
    query_patterns = [
        r'\bSELECT\b',    # Select statement
        r'\bINSERT\b',    # Insert statement
        r'\bUPDATE\b',    # Update statement
        r'\bDELETE\b',    # Delete statement
        r'\bCREATE\b',    # Create statement
        r'\bALTER\b',     # Alter statement
        r'\bDROP\b',      # Drop statement
        r'\bTRUNCATE\b',  # Truncate statement
        r'\bCALL\b'       # Stored procedure call
    ]

    # Check if input matches any of the query patterns
    for pattern in query_patterns:
        if re.search(pattern, input_str, re.IGNORECASE):
            return True
    if 'DELIMITER' in input_str and 'BEGIN' in input_str:
        return True    
    return False



# Function to call the API and update the output text area
def call_api(prompt_text,systemprompt):
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        tokencount = count_tokens(encoding,prompt_text)
        print(tokencount)
        if tokencount <= 4000:
            ModelName = "mysql-to-postgresql-gpt35"
        if tokencount > 4000:
            ModelName = "mysql-to-postgresql-gpt-35-turbo-16k"      
        
        response = client.chat.completions.create(
            model=ModelName,
            messages=[
              {"role": "system", "content": systemprompt},
              {"role": "user", "content": prompt_text}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return str(e)

def option_dict(option):
    options = {"Stored Procedure": 1, "Optimizer": 2, "Single Query": 3}
    return options.get(option, 0)

# Streamlit UI
st.title('MySQL To PostgreSQL')

with st.sidebar:
    st.write("Select an option:")
    option = st.selectbox("", ["Stored Procedure", "Optimizer", "Single Query"], index=0)
    api_key = st.text_input("Enter your API key:",placeholder="Enter your API key",label_visibility='collapsed')
    

selected_option_number = option_dict(option)
optimizerquery = "Optimize the given PostgreSQL query for improved performance without altering its functionality."
singlequery = "Convert the provided MySQL query to PostgreSQL format while maintaining its functionality."
wholespprompt = """As a PostgreSQL expert, please meticulously convert each and every line of the following MySQL query to PostgreSQL. Consider the key syntax and function differences between the two databases, ensuring the PostgreSQL query accurately produces the same results and functionality as the original MySQL query.

Additionally, adhere to the following conventions:

For variables declared in MySQL using SET @variablename = '', declare the equivalent variable in PostgreSQL with a name starting with 'var_' and assign it a value, e.g., var_variablename = ''.
Declare variables in PostgreSQL with names starting either with 'var_'.
When specifying the language, use single quotes around the language name, e.g., LANGUAGE 'plpgsql'.
Give preference to using the same table alias names as in MySQL.
Match column data types and lengths same as specified in MySQL. But if it is INT or INTEGER don't mention length just mention INT in postgresql.
Convert MySQL stored procedures to PostgreSQL functions if there is a separate select statement without the 'INTO' keyword and not attached to temporary tables or INSERT statements. Otherwise, consider it as a procedure.
Specify the PostgreSQL language using LANGUAGE 'plpgsql'.
Ensure to include LANGUAGE 'plpgsql' in every function or procedure.
Replace IFNULL in MySQL with COALESCE in PostgreSQL.
Replace UTC_TIMESTAMP in MySQL with NOW() in PostgreSQL.
Create an index in PostgreSQL when encountering KEY(column1, column2...) in MySQL.
When creating temporary tables in PostgreSQL, remove the primary key and column, then continue with the creation. After creating the temporary table, add the primary key using ALTER TABLE, e.g., ALTER TABLE tablename ADD PRIMARY KEY(id).
Convert decimal or decimal(40,30) in PostgreSQL to double precision.
Maintain the same alias names for columns in both MySQL and PostgreSQL.
Convert MySQL stored procedures to PostgreSQL functions if there's a separate select statement without the 'INTO' keyword, excluding temporary tables or INSERT statements.
Place exception blocks at the end of the PostgreSQL query if present in the MySQL query.
Follow the provided example for the excpetion block structure, replacing '{sp or function name}' with the corresponding SP or function name, and '{one parameter of sp or func}' with the appropriate parameter name.

Here is the example for exception block:
EXCEPTION
        WHEN OTHERS THEN
        DECLARE df_code int;
        DECLARE df_msg VARCHAR;
    BEGIN
        GET STACKED DIAGNOSTICS  df_code = RETURNED_SQLSTATE, df_msg = MESSAGE_TEXT;
        Raise notice 'error ---> %', df_msg;
        INSERT INTO atp.error_log(error_msg, sp_name, metadata, logutc)
        SELECT df_msg, {sp or function name}, {one parameter of sp or func}, now();

    END;
-----
Other guidelines to ensure accuracy:

Pay meticulous attention to data types and conversions, ensuring compatibility between MySQL and PostgreSQL.
Use VARCHAR instead of TEXT when declaring variables in PostgreSQL.
Consider any differences in default behaviors, such as handling of NULL values, case sensitivity, or quoting identifiers.
Account for any variations in function names or syntax that may exist between MySQL and PostgreSQL.
Be mindful of any specific settings or configurations that might affect the execution of the query in a PostgreSQL environment.
Ensure that each and every line of the MySQL query is accurately converted to PostgreSQL.
Optimize each query as much as possible for better performance.
Retain any comment lines present in the MySQL query.
"""
promptforai = ""

if selected_option_number == 1:    
   prompt_input = st.text_area(f'Paste your MySQL SP here (Selected option: {option}):', height=200,label_visibility='collapsed')
   promptforai = wholespprompt
elif selected_option_number == 2:    
   prompt_input = st.text_area(f'Paste your MySQL Query here (Selected option: {option}):', height=200,label_visibility='collapsed')    
   promptforai = optimizerquery    
elif selected_option_number == 3:
   prompt_input = st.text_area(f'Paste your MySQL Query here (Selected option: {option}):', height=200,label_visibility='collapsed')
   promptforai = singlequery


systemprompt = 'You are a query conversion specialist. Your role is to provide precise and accurate conversions of MySQL queries to PostgreSQL. And also ensure that the entire MySQL query is converted seamlessly to PostgreSQL, maintaining functionality and correctness throughout the process. Ensure the translated queries are syntactically correct and functionally equivalent to their MySQL counterparts.'


if st.button('Convert'):
    if prompt_input.strip() and api_key.strip():
       client = initialize_openai_client(api_key)
       print(api_key)  
       with st.spinner('Converting...'):
            if is_mysql_query(promptforai+"\n"+prompt_input):
               output = call_api(promptforai+"\n"+prompt_input,systemprompt)      
               #output_text.text(output)
               st.text_area('Successfully Converted as PostgreSQL : Response:', value=output, height=400)
            else:
                st.warning("Input is not a MySQL query or stored procedure. Processing not allowed.")   
    else:
        st.warning("Both prompt and API Key are required.")
