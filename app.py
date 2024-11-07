import streamlit as st
from boto3 import Session
from botocore.exceptions import ClientError
import openai
from datetime import datetime
import json
import re
import os

# Initialize session states
if 'aws_connected' not in st.session_state:
    st.session_state.aws_connected = False
if 'aws_expert' not in st.session_state:
    st.session_state.aws_expert = None
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'current_region' not in st.session_state:
    st.session_state.current_region = None

# Load OpenAI API key from secrets
openai.api_key = st.secrets["OPENAI_API_KEY"]

class AWSCommandExecutor:
    def __init__(self, session, region):
        self.session = session
        self.region = region
        
    def create_vpc(self, cidr_block, name='MyVPC'):
        ec2 = self.session.client('ec2')
        try:
            vpc = ec2.create_vpc(CidrBlock=cidr_block)
            vpc_id = vpc['Vpc']['VpcId']
            
            # Add name tag to VPC
            ec2.create_tags(
                Resources=[vpc_id],
                Tags=[{'Key': 'Name', 'Value': name}]
            )
            
            return f"VPC created successfully. VPC ID: {vpc_id}"
        except Exception as e:
            return f"Failed to create VPC: {str(e)}"
    
    def create_ec2_instance(self, instance_type='t2.micro', name='MyInstance'):
        ec2 = self.session.client('ec2')
        try:
            # Get latest Amazon Linux 2 AMI
            response = ec2.describe_images(
                Filters=[
                    {'Name': 'name', 'Values': ['amzn2-ami-hvm-*-x86_64-gp2']},
                    {'Name': 'state', 'Values': ['available']}
                ],
                Owners=['amazon']
            )
            ami_id = sorted(response['Images'], 
                          key=lambda x: x['CreationDate'],
                          reverse=True)[0]['ImageId']
            
            # Launch instance
            instance = ec2.run_instances(
                ImageId=ami_id,
                InstanceType=instance_type,
                MinCount=1,
                MaxCount=1,
                TagSpecifications=[
                    {
                        'ResourceType': 'instance',
                        'Tags': [
                            {'Key': 'Name', 'Value': name}
                        ]
                    }
                ]
            )
            
            instance_id = instance['Instances'][0]['InstanceId']
            return f"EC2 instance created successfully. Instance ID: {instance_id}"
        except Exception as e:
            return f"Failed to create EC2 instance: {str(e)}"
    
    def create_s3_bucket(self, bucket_name):
        s3 = self.session.client('s3')
        try:
            if self.region == 'us-east-1':
                s3.create_bucket(Bucket=bucket_name)
            else:
                s3.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': self.region}
                )
            return f"S3 bucket '{bucket_name}' created successfully"
        except Exception as e:
            return f"Failed to create S3 bucket: {str(e)}"

    def execute_command(self, command_text):
        """Parse and execute AWS commands from natural language or AWS CLI format"""
        command_text = command_text.lower()
        
        # Parse for EC2 instance creation
        if "create" in command_text and "ec2" in command_text:
            instance_type = 't2.micro'  # default
            name = 'MyInstance'
            
            # Extract instance type if specified
            type_match = re.search(r't[23]\.(micro|small|medium|large)', command_text)
            if type_match:
                instance_type = type_match.group(0)
            
            # Extract name if specified
            name_match = re.search(r'name[d:\s]+(["\']?([\w-]+)["\']?)', command_text, re.IGNORECASE)
            if name_match:
                name = name_match.group(2)
            
            return self.create_ec2_instance(instance_type, name)
        
        # Parse for VPC creation
        elif "create" in command_text and "vpc" in command_text:
            cidr = "10.0.0.0/16"  # default
            name = 'MyVPC'
            
            # Extract CIDR if specified
            cidr_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})', command_text)
            if cidr_match:
                cidr = cidr_match.group(1)
            
            # Extract name if specified
            name_match = re.search(r'name[d:\s]+(["\']?([\w-]+)["\']?)', command_text, re.IGNORECASE)
            if name_match:
                name = name_match.group(2)
            
            return self.create_vpc(cidr, name)
        
        # Parse for S3 bucket creation
        elif "create" in command_text and ("s3" in command_text or "bucket" in command_text):
            # Extract bucket name
            bucket_match = re.search(r'bucket[:\s]+(["\']?([\w.-]+)["\']?)', command_text, re.IGNORECASE)
            if bucket_match:
                bucket_name = bucket_match.group(2)
                return self.create_s3_bucket(bucket_name)
            else:
                return "Error: Bucket name not specified"
        
        return "Command not recognized or not supported"

class AWSExpert:
    def __init__(self, region=None):
        self.aws_session = None
        self.region = region
        self.executor = None

    def connect_aws(self, access_key, secret_key, region):
        try:
            self.region = region
            self.aws_session = Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region
            )
            # Test connection
            sts = self.aws_session.client('sts')
            sts.get_caller_identity()
            
            # Initialize command executor
            self.executor = AWSCommandExecutor(self.aws_session, region)
            return True
        except Exception as e:
            st.error(f"Failed to connect to AWS: {str(e)}")
            return False

    def disconnect_aws(self):
        self.aws_session = None
        self.region = None
        self.executor = None

    def get_gpt_response(self, user_input):
        try:
            region_context = f"Current AWS region: {self.region}. "
            completion = openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": f"""You are an AWS expert. Convert natural language to AWS commands. 
                     {region_context} Currently supported operations:
                     1. Create EC2 instances (specify instance type and name)
                     2. Create VPCs (specify CIDR and name)
                     3. Create S3 buckets (specify bucket name)
                     If any information is missing, ask the user for details."""},
                    {"role": "user", "content": user_input}
                ]
            )
            return completion.choices[0].message.content
        except Exception as e:
            st.error(f"Failed to get GPT response: {str(e)}")
            return None

    def execute_aws_command(self, command):
        try:
            return self.executor.execute_command(command)
        except Exception as e:
            st.error(f"Failed to execute AWS command: {str(e)}")
            return None

def main():
    st.title("AWS Expert Assistant")
    
    # AWS Regions
    aws_regions = [
        'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
        'eu-west-1', 'eu-west-2', 'eu-central-1',
        'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1'
    ]

    # Sidebar configuration
    with st.sidebar:
        st.header("Configuration")
        
        aws_access_key = st.text_input("AWS Access Key", type="password")
        aws_secret_key = st.text_input("AWS Secret Key", type="password")
        selected_region = st.selectbox("AWS Region", aws_regions)
        
        if st.button("Connect"):
            if aws_access_key and aws_secret_key:
                st.session_state.aws_expert = AWSExpert(selected_region)
                if st.session_state.aws_expert.connect_aws(aws_access_key, aws_secret_key, selected_region):
                    st.session_state.aws_connected = True
                    st.session_state.current_region = selected_region
                    st.success(f"Connected to AWS in region {selected_region}!")
            else:
                st.error("Please provide AWS credentials")

        if st.session_state.aws_connected and st.button("Disconnect"):
            if st.session_state.aws_expert:
                st.session_state.aws_expert.disconnect_aws()
            st.session_state.aws_connected = False
            st.session_state.aws_expert = None
            st.session_state.current_region = None
            st.success("Disconnected from AWS")

    # Main chat interface
    if st.session_state.aws_connected and st.session_state.aws_expert:
        st.info(f"Connected to AWS region: {st.session_state.current_region}")
        
        st.markdown("""
        ### Supported Commands:
        1. Create EC2 instances (e.g., "create a t2.micro EC2 instance named webserver")
        2. Create VPCs (e.g., "create a VPC with CIDR 10.0.0.0/16 named myvpc")
        3. Create S3 buckets (e.g., "create an S3 bucket named my-unique-bucket")
        """)
        
        # Display chat history
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.write(message["content"])

        # Chat input
        user_input = st.chat_input("What would you like to do in AWS?")
        
        if user_input:
            with st.chat_message("user"):
                st.write(user_input)
            st.session_state.chat_history.append({"role": "user", "content": user_input})

            gpt_response = st.session_state.aws_expert.get_gpt_response(user_input)
            
            if gpt_response:
                with st.chat_message("assistant"):
                    st.write(gpt_response)
                st.session_state.chat_history.append({"role": "assistant", "content": gpt_response})

                # Extract commands and execute them
                commands = re.findall(r'```(.*?)```', gpt_response, re.DOTALL)
                if not commands:
                    # If no code blocks found, treat the entire response as a command
                    commands = [gpt_response]
                
                for command in commands:
                    result = st.session_state.aws_expert.execute_aws_command(command)
                    if result:
                        st.success(result)
    else:
        st.info("Please connect to AWS using the sidebar")

if __name__ == "__main__":
    main()
