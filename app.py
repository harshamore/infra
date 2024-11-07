import streamlit as st
import boto3
from openai import OpenAI
import os
from typing import Dict, List

class AWSDeployer:
    def __init__(self, credentials: Dict[str, str]):
        self.credentials = credentials
        self.openai_client = OpenAI(api_key=st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY")))
    
    def get_aws_client(self, service: str):
        return boto3.client(
            service,
            aws_access_key_id=self.credentials['access_key'],
            aws_secret_access_key=self.credentials['secret_key'],
            region_name=self.credentials['region']
        )
    
    def process_user_request(self, user_request: str) -> Dict:
        # Prompt for GPT to convert natural language to AWS commands
        system_prompt = """You are an AWS expert. Convert the user's request into specific AWS commands.
        If any additional information is needed from the user, list it under "Required Information".
        Format your response as JSON with these keys:
        - explanation: Brief explanation of what needs to be done
        - required_info: List of additional information needed from user (if any)
        - aws_commands: List of AWS commands with service, action, and parameters
        
        Example output format:
        {
            "explanation": "To create a website, we need to...",
            "required_info": ["VPC CIDR block", "Website name"],
            "aws_commands": [
                {
                    "service": "ec2",
                    "action": "create_vpc",
                    "parameters": {"CidrBlock": "NEEDED_FROM_USER"}
                }
            ]
        }"""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_request}
                ],
                temperature=0.7
            )
            
            # Parse the response
            response_content = response.choices[0].message.content
            import json
            return json.loads(response_content)
            
        except Exception as e:
            st.error(f"Error processing request: {str(e)}")
            return None
    
    def execute_command(self, command: Dict) -> Dict:
        try:
            client = self.get_aws_client(command["service"])
            response = getattr(client, command["action"])(**command["parameters"])
            return {"success": True, "response": response}
        except Exception as e:
            return {"success": False, "error": str(e)}

def main():
    st.set_page_config(page_title="AWS Deployment Assistant")
    
    # Sidebar for AWS credentials
    with st.sidebar:
        st.title("AWS Credentials")
        with st.form("aws_credentials"):
            access_key = st.text_input("Access Key ID", type="password")
            secret_key = st.text_input("Secret Access Key", type="password")
            region = st.text_input("Region", value="us-east-1")
            submitted = st.form_submit_button("Connect to AWS")
            
            if submitted and access_key and secret_key:
                st.session_state.credentials = {
                    "access_key": access_key,
                    "secret_key": secret_key,
                    "region": region
                }
                st.success("Connected to AWS!")

    # Main interface
    st.title("AWS Deployment Assistant")
    
    if "credentials" not in st.session_state:
        st.warning("Please connect to AWS first using the sidebar.")
        return
    
    if "deployer" not in st.session_state and "credentials" in st.session_state:
        st.session_state.deployer = AWSDeployer(st.session_state.credentials)
    
    if "required_info" not in st.session_state:
        st.session_state.required_info = {}
    
    # User input
    user_request = st.text_input("What would you like to deploy? (e.g., 'I want to bring up a website')")
    
    if user_request:
        # Process the request
        result = st.session_state.deployer.process_user_request(user_request)
        
        if result:
            st.write("### Plan")
            st.write(result["explanation"])
            
            # Check if additional information is needed
            if result.get("required_info"):
                st.write("### Required Information")
                for info in result["required_info"]:
                    if info not in st.session_state.required_info:
                        st.session_state.required_info[info] = st.text_input(f"Please provide {info}:")
                
                # Check if all required info is provided
                if all(st.session_state.required_info.values()):
                    st.write("### AWS Commands")
                    st.json(result["aws_commands"])
                    
                    if st.button("Execute Deployment"):
                        for command in result["aws_commands"]:
                            # Replace placeholder values with user input
                            for key, value in command["parameters"].items():
                                if value == "NEEDED_FROM_USER":
                                    # Find matching required info
                                    for info_key, info_value in st.session_state.required_info.items():
                                        if info_key.lower().replace(" ", "_") in key.lower():
                                            command["parameters"][key] = info_value
                            
                            # Execute the command
                            execution_result = st.session_state.deployer.execute_command(command)
                            if execution_result["success"]:
                                st.success(f"Successfully executed: {command['action']}")
                            else:
                                st.error(f"Failed to execute {command['action']}: {execution_result['error']}")

if __name__ == "__main__":
    main()
