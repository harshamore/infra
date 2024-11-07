import streamlit as st
import openai
from openai import OpenAI
import boto3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from decimal import Decimal
import queue
import threading

# [Previous DeploymentManager and CostEstimator classes remain the same]

class CloudAssistant:
    # [Previous CloudAssistant implementation remains the same]
    pass

def init_session_state():
    """Initialize session state variables"""
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'assistant' not in st.session_state:
        st.session_state.assistant = None
    if 'credentials' not in st.session_state:
        st.session_state.credentials = None

def render_sidebar() -> None:
    """Render the sidebar with cloud provider selection and credentials input"""
    with st.sidebar:
        st.title("Cloud Provider Setup")
        
        provider = st.selectbox(
            "Select Cloud Provider",
            ["Select a provider", "AWS", "GCP", "Azure"]
        )
        
        if provider == "AWS":
            with st.form(key="aws_credentials_form"):
                st.subheader("AWS Credentials")
                access_key = st.text_input("Access Key ID", type="password")
                secret_key = st.text_input("Secret Access Key", type="password")
                region = st.text_input("Region", value="us-east-1")
                
                submit_button = st.form_submit_button("Connect")
                
                if submit_button:
                    if access_key and secret_key and region:
                        st.session_state.credentials = {
                            "access_key": access_key,
                            "secret_key": secret_key,
                            "region": region
                        }
                        st.success("AWS credentials updated!")
                    else:
                        st.error("Please fill in all fields")
        
        elif provider in ["GCP", "Azure"]:
            st.info(f"{provider} integration coming soon!")

def main():
    st.set_page_config(page_title="Cloud Configuration Assistant", layout="wide")
    
    # Initialize session state
    init_session_state()
    
    # Render sidebar (this updates session state if credentials are submitted)
    render_sidebar()
    
    # Initialize or update assistant if credentials are available
    if st.session_state.credentials and st.session_state.assistant is None:
        try:
            st.session_state.assistant = CloudAssistant()
            st.session_state.assistant.set_aws_credentials(st.session_state.credentials)
            st.success("Cloud Assistant initialized successfully!")
        except Exception as e:
            st.error(f"Error initializing Cloud Assistant: {str(e)}")
            return

    # Main chat interface
    st.title("Cloud Configuration Assistant")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            if "config" in message:
                with st.expander("Configuration Details"):
                    st.json(message["config"])

    # Chat input
    prompt = st.chat_input("What would you like to configure?")
    if prompt:
        if st.session_state.assistant is None:
            st.error("Please connect your AWS credentials first")
            return

        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Get assistant response
        with st.chat_message("assistant"):
            config = st.session_state.assistant.process_user_query(prompt)
            if config:
                response = f"{config['explanation']}\n\nEstimated monthly cost: ${config['total_estimated_cost']:.2f}"
                st.write(response)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response,
                    "config": config
                })
                
                with st.expander("Review Configuration"):
                    st.json(config["aws_commands"])
                
                if st.button("Execute Configuration"):
                    results = []
                    for command in config["aws_commands"]:
                        result = st.session_state.assistant.execute_aws_command(command)
                        results.append(result)
                    
                    if all(r["success"] for r in results):
                        st.success("Configuration completed successfully!")
                    else:
                        st.error("Some operations failed. Check the details.")
                        st.json(results)

if __name__ == "__main__":
    main()
