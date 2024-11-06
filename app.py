import streamlit as st
import openai
import boto3
from google.cloud import compute_v1
from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient
import json
import yaml
from typing import Dict, Any
import os

# Cloud Provider Authentication Classes
class CloudAuth:
    @staticmethod
    def aws_auth(credentials: Dict[str, str]) -> boto3.Session:
        return boto3.Session(
            aws_access_key_id=credentials['access_key'],
            aws_secret_access_key=credentials['secret_key'],
            region_name=credentials['region']
        )
    
    @staticmethod
    def gcp_auth(credentials: Dict[str, str]) -> compute_v1.InstancesClient:
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials['credentials_path']
        return compute_v1.InstancesClient()
    
    @staticmethod
    def azure_auth(credentials: Dict[str, str]) -> ComputeManagementClient:
        credential = ClientSecretCredential(
            tenant_id=credentials['tenant_id'],
            client_id=credentials['client_id'],
            client_secret=credentials['client_secret']
        )
        return ComputeManagementClient(credential, credentials['subscription_id'])

class CloudProvisioner:
    def __init__(self):
        self.cloud_clients = {}
    
    def provision_resource(self, provider: str, config: Dict[str, Any]) -> Dict[str, Any]:
        if provider == "AWS":
            return self._provision_aws(config)
        elif provider == "GCP":
            return self._provision_gcp(config)
        elif provider == "AZURE":
            return self._provision_azure(config)
    
    def _provision_aws(self, config: Dict[str, Any]) -> Dict[str, Any]:
        ec2 = self.cloud_clients['aws'].client('ec2')
        response = ec2.run_instances(
            ImageId=config['image_id'],
            InstanceType=config['instance_type'],
            MinCount=1,
            MaxCount=1,
            NetworkInterfaces=[{'SubnetId': config['subnet_id']}]
        )
        return response
    
    # Add GCP and Azure provisioning methods similarly

class LLMInterface:
    def __init__(self, api_key: str):
        openai.api_key = st.secrets["OPENAI_API_KEY"]
    
    def process_query(self, query: str) -> Dict[str, Any]:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert in AWS, GCP, AZURE cloud configurations and deployments, with advanced experience working with cloud provider APIs."},
                {"role": "user", "content": query}
            ]
        )
        return self._parse_llm_response(response.choices[0].message.content)
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        try:
            # Attempt to parse YAML or JSON configuration from LLM response
            return yaml.safe_load(response)
        except:
            st.error("Failed to parse LLM response into valid configuration")
            return {}

def main():
    st.title("Cloud Resource Provisioner")
    
    # Cloud Provider Selection
    provider = st.selectbox(
        "Select Cloud Provider",
        ["AWS", "GCP", "AZURE"]
    )
    
    # Authentication Section
    with st.expander("Cloud Provider Authentication"):
        if provider == "AWS":
            aws_access_key = st.text_input("AWS Access Key", type="password")
            aws_secret_key = st.text_input("AWS Secret Key", type="password")
            aws_region = st.text_input("AWS Region")
            credentials = {
                "access_key": aws_access_key,
                "secret_key": aws_secret_key,
                "region": aws_region
            }
        elif provider == "GCP":
            gcp_creds_path = st.text_input("GCP Credentials File Path")
            credentials = {"credentials_path": gcp_creds_path}
        else:  # AZURE
            azure_tenant = st.text_input("Azure Tenant ID")
            azure_client = st.text_input("Azure Client ID")
            azure_secret = st.text_input("Azure Client Secret", type="password")
            azure_subscription = st.text_input("Azure Subscription ID")
            credentials = {
                "tenant_id": azure_tenant,
                "client_id": azure_client,
                "client_secret": azure_secret,
                "subscription_id": azure_subscription
            }
    
    # OpenAI API Configuration
    openai.api_key = st.secrets["OPENAI_API_KEY"]
    
    # Initialize Components
    if st.button("Initialize Connection"):
        try:
            cloud_auth = CloudAuth()
            provisioner = CloudProvisioner()
            
            if provider == "AWS":
                provisioner.cloud_clients['aws'] = cloud_auth.aws_auth(credentials)
            elif provider == "GCP":
                provisioner.cloud_clients['gcp'] = cloud_auth.gcp_auth(credentials)
            else:
                provisioner.cloud_clients['azure'] = cloud_auth.azure_auth(credentials)
            
            st.session_state['provisioner'] = provisioner
            st.session_state['llm'] = LLMInterface(openai_api_key)
            st.success("Connection established successfully!")
            
        except Exception as e:
            st.error(f"Failed to initialize connection: {str(e)}")
    
    # Chat Interface
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    if prompt := st.chat_input("Enter your infrastructure request"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        if 'llm' in st.session_state and 'provisioner' in st.session_state:
            # Process request through LLM
            config = st.session_state['llm'].process_query(prompt)
            
            if config:
                # Attempt to provision resources
                try:
                    result = st.session_state['provisioner'].provision_resource(provider, config)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"Successfully provisioned resources:\n```json\n{json.dumps(result, indent=2)}\n```"
                    })
                except Exception as e:
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"Failed to provision resources: {str(e)}"
                    })
        else:
            st.error("Please initialize the connection first!")

if __name__ == "__main__":
    main()
