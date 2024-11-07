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
    def __init__(self):
        self.openai_api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OpenAI API key not found in environment variables or Streamlit secrets")
        
        self.openai_client = OpenAI(api_key=self.openai_api_key)
        self.deployment_manager = DeploymentManager()
        self.cost_estimator = CostEstimator()
        self.aws_credentials = None

    def set_aws_credentials(self, credentials: Dict):
        self.aws_credentials = credentials

    def get_aws_client(self, service: str):
        if not self.aws_credentials:
            raise ValueError("AWS credentials not set")
        return boto3.client(
            service,
            aws_access_key_id=self.aws_credentials['access_key'],
            aws_secret_access_key=self.aws_credentials['secret_key'],
            region_name=self.aws_credentials['region']
        )

    def process_user_query(self, user_query: str) -> Dict:
        """Process user query with OpenAI to generate AWS configurations"""
        system_prompt = """You are an expert AWS cloud architect. When a user requests to create AWS resources:
        1. First, explain what you'll do in a brief paragraph.
        2. Then, list the exact AWS commands needed in this format:
        
        Commands:
        Service: [service name, e.g., ec2]
        Action: [API action, e.g., run_instances]
        Parameters:
        - ParameterName: value
        - ParameterName: value
        
        For example, for an EC2 instance:
        Commands:
        Service: ec2
        Action: run_instances
        Parameters:
        - ImageId: ami-0c55b159cbfafe1f0
        - InstanceType: t2.micro
        - MinCount: 1
        - MaxCount: 1
        """

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.7
            )
            
            # Get the response text
            response_text = response.choices[0].message.content
            
            # Parse the response into explanation and commands
            parts = response_text.split("Commands:")
            explanation = parts[0].strip()
            
            # Parse commands if they exist
            commands = []
            if len(parts) > 1:
                command_text = parts[1].strip()
                current_command = {}
                
                # Split into command blocks
                command_blocks = command_text.split("Service:")
                
                for block in command_blocks:
                    if not block.strip():
                        continue
                        
                    lines = block.strip().split('\n')
                    command = {"service": "", "action": "", "parameters": {}}
                    
                    for line in lines:
                        line = line.strip()
                        if line.startswith("Service:"):
                            command["service"] = line.split("Service:")[1].strip().lower()
                        elif line.startswith("Action:"):
                            command["action"] = line.split("Action:")[1].strip()
                        elif line.startswith("Parameters:"):
                            continue
                        elif line.startswith("-"):
                            param_line = line[1:].strip()
                            if ":" in param_line:
                                key, value = param_line.split(":", 1)
                                command["parameters"][key.strip()] = value.strip()
                    
                    if command["service"] and command["action"]:
                        commands.append(command)
            
            # Create config dictionary
            config = {
                "explanation": explanation,
                "aws_commands": commands,
                "total_estimated_cost": 0
            }
            
            # Add cost estimation
            total_cost = 0
            for command in config["aws_commands"]:
                service = command.get("service")
                if service:
                    cost_estimate = self.cost_estimator.estimate_cost(
                        service,
                        command.get("parameters", {})
                    )
                    command["estimated_cost"] = cost_estimate
                    total_cost += cost_estimate["monthly_cost"]
            
            config["total_estimated_cost"] = total_cost
            return config
            
        except Exception as e:
            st.error(f"Error processing query: {str(e)}")
            return None

    def execute_aws_command(self, command: Dict) -> Dict:
        """Execute AWS command and return results"""
        try:
            client = self.get_aws_client(command["service"])
            response = getattr(client, command["action"])(
                **command["parameters"]
            )
            return {"success": True, "response": response}
        except Exception as e:
            return {"success": False, "error": str(e)}

# [Previous render_sidebar function remains the same]

def main():
    st.set_page_config(page_title="Cloud Configuration Assistant", layout="wide")
    
    # Initialize session state
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'assistant' not in st.session_state:
        st.session_state.assistant = None

    # Process sidebar and credentials
    credentials = render_sidebar()
    if credentials:
        if st.session_state.assistant is None:
            st.session_state.assistant = CloudAssistant()
        st.session_state.assistant.set_aws_credentials(credentials)
        st.success("AWS credentials connected successfully!")

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
    if prompt := st.chat_input("What would you like to configure?"):
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
