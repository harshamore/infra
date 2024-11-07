import streamlit as st
import boto3
from botocore.exceptions import ClientError
import openai
from datetime import datetime
import json
import re
import os
from pricing import AWSPricing  # Custom module for AWS pricing calculations

class AWSExpert:
    def __init__(self):
        self.openai_client = None
        self.aws_session = None
        self.pricing_client = None

    def initialize_openai(self, api_key):
        openai.api_key = st.secrets.get("OPENAI_API_KEY")
        self.openai_client = openai

    def connect_aws(self, access_key, secret_key):
        try:
            self.aws_session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key
            )
            self.pricing_client = AWSPricing(self.aws_session)
            return True
        except Exception as e:
            st.error(f"Failed to connect to AWS: {str(e)}")
            return False

    def disconnect_aws(self):
        self.aws_session = None
        st.session_state.aws_connected = False

    def get_gpt_response(self, user_input):
        try:
            completion = self.openai_client.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": """You are an AWS expert, your role will be understand natural language 
                     and convert them to AWS commands. Then execute them to provision the infrastructure in the cloud. 
                     If any information is needed from user like name, cidr etc. you will ask the user for those details"""},
                    {"role": "user", "content": user_input}
                ]
            )
            return completion.choices[0].message.content
        except Exception as e:
            st.error(f"Failed to get GPT response: {str(e)}")
            return None

    def execute_aws_command(self, command):
        try:
            # Parse the command and execute corresponding AWS API calls
            # This is a simplified example - you would need to implement proper command parsing
            if "create" in command.lower() and "ec2" in command.lower():
                ec2_client = self.aws_session.client('ec2')
                # Execute EC2 creation command
                response = ec2_client.run_instances(
                    # Parse parameters from command
                    ImageId='ami-12345678',
                    InstanceType='t2.micro',
                    MinCount=1,
                    MaxCount=1
                )
                return response
            # Add more command handlers here
            return None
        except Exception as e:
            st.error(f"Failed to execute AWS command: {str(e)}")
            return None

    def estimate_costs(self, command):
        try:
            # Use pricing client to estimate costs
            # This is a simplified example
            return self.pricing_client.calculate_cost(command)
        except Exception as e:
            st.error(f"Failed to estimate costs: {str(e)}")
            return None

def main():
    st.title("AWS Expert Assistant")
    
    # Initialize session state
    if 'aws_expert' not in st.session_state:
        st.session_state.aws_expert = AWSExpert()
    if 'aws_connected' not in st.session_state:
        st.session_state.aws_connected = False
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []

    # Sidebar for AWS credentials
    with st.sidebar:
        st.header("Configuration")
        
        # AWS Credentials
        aws_access_key = st.text_input("AWS Access Key", type="password")
        aws_secret_key = st.text_input("AWS Secret Key", type="password")
        
        # OpenAI API Key
        openai_api_key = st.text_input("OpenAI API Key", type="password")
        
        if st.button("Connect"):
            if aws_access_key and aws_secret_key and openai_api_key:
                st.session_state.aws_expert.initialize_openai(openai_api_key)
                if st.session_state.aws_expert.connect_aws(aws_access_key, aws_secret_key):
                    st.session_state.aws_connected = True
                    st.success("Connected to AWS!")
            else:
                st.error("Please provide all required credentials")

        if st.session_state.aws_connected and st.button("Disconnect"):
            st.session_state.aws_expert.disconnect_aws()
            st.success("Disconnected from AWS")

    # Main chat interface
    if st.session_state.aws_connected:
        # Display chat history
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.write(message["content"])

        # Chat input
        user_input = st.chat_input("What would you like to do in AWS?")
        
        if user_input:
            # Display user message
            with st.chat_message("user"):
                st.write(user_input)
            st.session_state.chat_history.append({"role": "user", "content": user_input})

            # Get GPT response
            gpt_response = st.session_state.aws_expert.get_gpt_response(user_input)
            
            if gpt_response:
                # Display assistant response
                with st.chat_message("assistant"):
                    st.write(gpt_response)
                st.session_state.chat_history.append({"role": "assistant", "content": gpt_response})

                # Extract AWS commands from GPT response
                # This is a simplified example - you would need more sophisticated parsing
                aws_commands = re.findall(r'```(.*?)```', gpt_response, re.DOTALL)
                
                if aws_commands:
                    # Execute AWS commands
                    for command in aws_commands:
                        result = st.session_state.aws_expert.execute_aws_command(command)
                        estimated_cost = st.session_state.aws_expert.estimate_costs(command)
                        
                        if result:
                            st.success("Command executed successfully!")
                            if estimated_cost:
                                st.info(f"Estimated monthly cost: ${estimated_cost:.2f}")
                        else:
                            st.error("Failed to execute command")
    else:
        st.info("Please connect to AWS using the sidebar")

if __name__ == "__main__":
    main()
