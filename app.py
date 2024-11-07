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

# Define DeploymentManager class
class DeploymentManager:
    def __init__(self):
        self.actions_history: List[Dict] = []
        self.deployment_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.rollback_queue = queue.Queue()
    
    def add_action(self, action: Dict):
        self.actions_history.append(action)
    
    def get_rollback_actions(self) -> List[Dict]:
        return list(reversed(self.actions_history))

# Define CostEstimator class
class CostEstimator:
    def __init__(self):
        self.pricing_data = {
            "ec2": {
                "t3.micro": 0.0104,
                "t3.small": 0.0208,
                "t3.medium": 0.0416
            },
            "s3": {
                "storage": 0.023,
                "transfer": 0.09
            }
        }
    
    def estimate_cost(self, service: str, config: Dict) -> Dict:
        if service == "ec2":
            instance_type = config.get("InstanceType", "t3.micro")
            hours = config.get("Hours", 730)  # Default to full month
            cost = self.pricing_data["ec2"].get(instance_type, 0) * hours
            return {
                "monthly_cost": cost,
                "details": f"{instance_type} running {hours} hours"
            }
        elif service == "s3":
            storage_gb = config.get("StorageGB", 1)
            transfer_gb = config.get("TransferGB", 0)
            cost = (storage_gb * self.pricing_data["s3"]["storage"] +
                   transfer_gb * self.pricing_data["s3"]["transfer"])
            return {
                "monthly_cost": cost,
                "details": f"{storage_gb}GB storage, {transfer_gb}GB transfer"
            }
        return {"monthly_cost": 0, "details": "Unknown service"}

# Define main CloudAssistant class
class CloudAssistant:
    def __init__(self):
        # Initialize OpenAI client with API key
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
        system_prompt = """You are an expert AWS cloud architect. Analyze user requests and provide:
        1. Detailed AWS configuration with specific service requirements
        2. Resource specifications for accurate cost estimation
        3. Deployment steps with rollback procedures
        
        For each AWS service mentioned, provide the exact API calls needed."""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            config = json.loads(response.choices[0].message.content)
            
            # Add cost estimation
            total_cost = 0
            for command in config.get("aws_commands", []):
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

def render_sidebar():
    """Render the sidebar with cloud provider selection and credentials input"""
    with st.sidebar:
        st.title("Cloud Provider Setup")
        
        provider = st.selectbox(
            "Select Cloud Provider",
            ["Select a provider", "AWS", "GCP", "Azure"]
        )
        
        if provider == "AWS":
            with st.form("aws_credentials"):
                st.subheader("AWS Credentials")
                access_key = st.text_input("Access Key ID", type="password")
                secret_key = st.text_input("Secret Access Key", type="password")
                region = st.text_input("Region", value="us-east-1")
                
                if st.form_submit_button("Connect"):
                    if access_key and secret_key and region:
                        return {
                            "access_key": access_key,
                            "secret_key": secret_key,
                            "region": region
                        }
                    else:
                        st.error("Please fill in all fields")
        
        elif provider in ["GCP", "Azure"]:
            st.info(f"{provider} integration coming soon!")
    
    return None

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
                response = f"I'll help you with that. Estimated monthly cost: ${config['total_estimated_cost']:.2f}"
                st.write(response)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response,
                    "config": config
                })
                
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
