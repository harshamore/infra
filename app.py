import streamlit as st
import openai
import boto3
import json
from typing import Dict, List, Optional
from datetime import datetime
import threading
import queue
from decimal import Decimal

class AWSAction:
    def __init__(self, service: str, action: str, parameters: Dict):
        self.service = service
        self.action = action
        self.parameters = parameters
        self.response = None
        self.resource_id = None
        self.rollback_action = None
        self.rollback_parameters = None

class DeploymentManager:
    def __init__(self):
        self.actions_history: List[AWSAction] = []
        self.deployment_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.rollback_queue = queue.Queue()
        
    def add_rollback_action(self, action: AWSAction, rollback_details: Dict):
        """Add rollback information for an action"""
        action.rollback_action = rollback_details.get('action')
        action.rollback_parameters = rollback_details.get('parameters')
        self.actions_history.append(action)

    def execute_rollback(self, aws_client) -> List[Dict]:
        """Execute rollback for failed deployment"""
        rollback_results = []
        
        # Process actions in reverse order
        for action in reversed(self.actions_history):
            if action.rollback_action and action.response:  # Only rollback successful actions
                try:
                    client = aws_client.get_aws_client(action.service)
                    rollback_response = getattr(client, action.rollback_action)(
                        **action.rollback_parameters
                    )
                    rollback_results.append({
                        "action": action.rollback_action,
                        "status": "success",
                        "details": rollback_response
                    })
                except Exception as e:
                    rollback_results.append({
                        "action": action.rollback_action,
                        "status": "failed",
                        "error": str(e)
                    })
        
        return rollback_results

class CostEstimator:
    def __init__(self):
        # Base pricing for common AWS services (simplified)
        self.pricing_data = {
            "ec2": {
                "t3.micro": 0.0104,  # USD per hour
                "t3.small": 0.0208,
                "t3.medium": 0.0416,
            },
            "s3": {
                "storage": 0.023,  # USD per GB per month
                "transfer": 0.09,  # USD per GB (outbound)
            },
            "rds": {
                "t3.micro": 0.017,
                "t3.small": 0.034,
                "t3.medium": 0.068,
            }
        }

    def estimate_resource_cost(self, service: str, configuration: Dict) -> Dict:
        """Estimate cost for a specific resource configuration"""
        monthly_cost = Decimal('0')
        details = []

        if service == "ec2":
            instance_type = configuration.get("InstanceType", "t3.micro")
            count = int(configuration.get("Count", 1))
            
            hourly_cost = Decimal(str(self.pricing_data["ec2"].get(instance_type, 0)))
            monthly_cost = hourly_cost * 24 * 30 * count
            
            details.append({
                "item": f"{count}x {instance_type} EC2 instance(s)",
                "monthly_cost": float(monthly_cost)
            })

        elif service == "s3":
            estimated_storage = Decimal(str(configuration.get("EstimatedStorageGB", 1)))
            estimated_transfer = Decimal(str(configuration.get("EstimatedTransferGB", 0)))
            
            storage_cost = estimated_storage * Decimal(str(self.pricing_data["s3"]["storage"]))
            transfer_cost = estimated_transfer * Decimal(str(self.pricing_data["s3"]["transfer"]))
            monthly_cost = storage_cost + transfer_cost
            
            details.append({
                "item": f"S3 Storage ({estimated_storage}GB)",
                "monthly_cost": float(storage_cost)
            })
            details.append({
                "item": f"S3 Transfer ({estimated_transfer}GB)",
                "monthly_cost": float(transfer_cost)
            })

        return {
            "monthly_estimate": float(monthly_cost),
            "details": details,
            "notes": ["Estimates are approximate and may vary based on usage patterns",
                     "Additional costs may apply for related services",
                     "Prices based on US East (N. Virginia) region"]
        }

class CloudAssistant:
    def __init__(self):
        self.openai_client = None
        self.aws_client = None
        self.deployment_manager = DeploymentManager()
        self.cost_estimator = CostEstimator()
        
    def get_aws_client(self, service: str):
        """Get or create an AWS service client"""
        return boto3.client(
            service,
            aws_access_key_id=st.session_state.aws_credentials['access_key'],
            aws_secret_access_key=st.session_state.aws_credentials['secret_key'],
            region_name=st.session_state.aws_credentials['region']
        )

    def process_user_query(self, user_query: str) -> Dict:
        """Process user query with enhanced cost estimation"""
        system_prompt = """You are an expert AWS cloud architect. Analyze user requests and provide:
        1. Detailed AWS configuration with specific service requirements
        2. Resource specifications for accurate cost estimation
        3. Deployment steps with rollback procedures
        
        Respond with a JSON object containing:
        {
            "aws_commands": [{
                "service": "service_name",
                "action": "action_name",
                "parameters": {},
                "rollback": {
                    "action": "rollback_action",
                    "parameters": {}
                },
                "cost_factors": {
                    "service": "service_name",
                    "EstimatedStorageGB": 0,
                    "EstimatedTransferGB": 0,
                    "InstanceType": "instance_type",
                    "Count": 1
                }
            }],
            "missing_info": [],
            "explanation": "detailed_explanation",
            "deployment_order": ["step1", "step2"],
            "estimated_duration": "duration_in_minutes"
        }"""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.7,
                response_format={ "type": "json_object" }
            )
            
            config = json.loads(response.choices[0].message.content)
            
            # Enhance with detailed cost estimation
            total_cost = Decimal('0')
            cost_breakdown = []
            
            for command in config["aws_commands"]:
                cost_factors = command.get("cost_factors", {})
                service = cost_factors.get("service")
                if service:
                    cost_estimate = self.cost_estimator.estimate_resource_cost(
                        service, cost_factors
                    )
                    total_cost += Decimal(str(cost_estimate["monthly_estimate"]))
                    cost_breakdown.extend(cost_estimate["details"])
            
            config["cost_estimation"] = {
                "monthly_total": float(total_cost),
                "breakdown": cost_breakdown,
                "notes": self.cost_estimator.estimate_resource_cost("", {})["notes"]
            }
            
            return config
            
        except Exception as e:
            st.error(f"Error processing query: {str(e)}")
            return None

    def execute_deployment(self, config: Dict) -> Dict:
        """Execute deployment with rollback support"""
        execution_results = []
        failed = False
        
        try:
            # Execute commands in specified order
            for step in config["deployment_order"]:
                command = next(cmd for cmd in config["aws_commands"] 
                             if cmd.get("step_id") == step)
                
                action = AWSAction(
                    command["service"],
                    command["action"],
                    command["parameters"]
                )
                
                # Execute the AWS action
                client = self.get_aws_client(action.service)
                action.response = getattr(client, action.action)(**action.parameters)
                
                # Store rollback information
                self.deployment_manager.add_rollback_action(action, command.get("rollback", {}))
                
                execution_results.append({
                    "step": step,
                    "status": "success",
                    "response": action.response
                })
                
        except Exception as e:
            failed = True
            execution_results.append({
                "step": step,
                "status": "failed",
                "error": str(e)
            })
            
            # Perform rollback if any step fails
            if failed:
                st.warning("Deployment failed. Initiating rollback...")
                rollback_results = self.deployment_manager.execute_rollback(self)
                execution_results.append({
                    "rollback_results": rollback_results
                })
        
        return {
            "success": not failed,
            "results": execution_results,
            "deployment_id": self.deployment_manager.deployment_id
        }

def render_cost_estimation(cost_data: Dict):
    """Render cost estimation details"""
    st.subheader("💰 Cost Estimation")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.write("Monthly Cost Breakdown:")
        for item in cost_data["breakdown"]:
            st.write(f"- {item['item']}: ${item['monthly_cost']:.2f}")
    
    with col2:
        st.metric(
            label="Total Monthly Estimate",
            value=f"${cost_data['monthly_total']:.2f}"
        )
    
    with st.expander("Cost Estimation Notes"):
        for note in cost_data["notes"]:
            st.write(f"- {note}")

def render_deployment_status(results: Dict):
    """Render deployment status and results"""
    if results["success"]:
        st.success("✅ Deployment completed successfully")
    else:
        st.error("❌ Deployment failed - Rollback completed")
    
    with st.expander("Deployment Details"):
        st.write(f"Deployment ID: {results['deployment_id']}")
        for result in results["results"]:
            if "step" in result:
                status_icon = "✅" if result["status"] == "success" else "❌"
                st.write(f"{status_icon} Step: {result['step']}")
                if result["status"] == "failed":
                    st.error(f"Error: {result['error']}")
            elif "rollback_results" in result:
                st.write("🔄 Rollback Results:")
                for rollback in result["rollback_results"]:
                    status_icon = "✅" if rollback["status"] == "success" else "❌"
                    st.write(f"{status_icon} {rollback['action']}")

def render_chat_interface():
    """Render the chat interface with enhanced features"""
    st.title("Cloud Configuration Assistant")
    
    # Display chat messages with enhanced visualization
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            
            if "config" in message:
                config = message["config"]
                
                # Show cost estimation if available
                if "cost_estimation" in config:
                    render_cost_estimation(config["cost_estimation"])
                
                # Show deployment plan
                if "deployment_order" in config:
                    with st.expander("Deployment Plan"):
                        for step in config["deployment_order"]:
                            st.write(f"- {step}")
                
            if "execution_results" in message:
                render_deployment_status(message["execution_results"])
    
    # Chat input and processing remains the same as before...

# Main function remains the same...
