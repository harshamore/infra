import streamlit as st
import boto3
import openai

# Access OpenAI API key from Streamlit secrets
openai.api_key = st.secrets["openai"]["api_key"]

# Sidebar for AWS credentials
st.sidebar.title("AWS Connection")
aws_access_key = st.sidebar.text_input("AWS Access Key")
aws_secret_key = st.sidebar.text_input("AWS Secret Key", type="password")
aws_region = st.sidebar.text_input("AWS Region")
connect_button = st.sidebar.button("Connect")

# AWS Connection
aws_session = None
if connect_button:
    try:
        aws_session = boto3.Session(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region
        )
        st.sidebar.success("Connected to AWS!")
    except Exception as e:
        st.sidebar.error(f"Connection failed: {e}")

# Chat Interface for AWS deployment requests
st.title("AWS Deployment Assistant")
user_input = st.text_input("Enter your AWS deployment request:")

if user_input:
    # Send input to OpenAI to interpret and respond with AWS commands
    try:
        # Adjusted for the new OpenAI API syntax
        response = openai.ChatCompletion.acreate(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": user_input}]
        )
        
        # Extract OpenAI response
        response_content = response.choices[0].message["content"]
        st.write("Assistant:", response_content)
        
        # Check if additional information is required
        if "please specify" in response_content.lower():
            additional_details = st.text_input("Additional Details Required:", key="additional")
            if additional_details:
                # Resend with additional details if provided
                follow_up_response = openai.ChatCompletion.acreate(
                    model="gpt-4-turbo",
                    messages=[
                        {"role": "user", "content": user_input},
                        {"role": "assistant", "content": response_content},
                        {"role": "user", "content": additional_details}
                    ]
                )
                follow_up_content = follow_up_response.choices[0].message["content"]
                st.write("Assistant:", follow_up_content)
                
        # AWS Command Execution if fully configured
        if aws_session and "Ready to deploy" in response_content:
            # Placeholder for deploying based on the response instructions.
            # Parse commands from response_content and use Boto3 to execute in AWS.
            st.success("Deployment initiated in AWS.")

    except Exception as e:
        st.error(f"Error with OpenAI API request: {e}")
