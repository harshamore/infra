# In the main app file
import streamlit as st
import openai
from openai import OpenAI
import os

class CloudAssistant:
    def __init__(self):
        # Initialize OpenAI client with API key
        self.openai_api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OpenAI API key not found in environment variables or Streamlit secrets")
        
        self.openai_client = OpenAI(api_key=self.openai_api_key)
        self.aws_client = None
        self.deployment_manager = DeploymentManager()
        self.cost_estimator = CostEstimator()

    def process_user_query(self, user_query: str) -> Dict:
        """Process user query with OpenAI to generate AWS configurations"""
        system_prompt = """You are an expert AWS cloud architect. Analyze user requests and provide:
        1. Detailed AWS configuration with specific service requirements
        2. Resource specifications for accurate cost estimation
        3. Deployment steps with rollback procedures
        
        For each AWS service mentioned, provide the exact API calls needed.
        
        Example:
        User: "Create an S3 bucket for my website"
        Response should include:
        {
            "aws_commands": [{
                "service": "s3",
                "action": "create_bucket",
                "parameters": {
                    "Bucket": "example-website-bucket",
                    "ACL": "private"
                },
                "rollback": {
                    "action": "delete_bucket",
                    "parameters": {
                        "Bucket": "example-website-bucket"
                    }
                }
            }]
        }"""

        try:
            # Send request to OpenAI API
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.7,
                response_format={ "type": "json_object" }
            )
            
            # Parse the response
            config = json.loads(response.choices[0].message.content)
            
            # Validate the response structure
            required_keys = ["aws_commands", "explanation", "deployment_order"]
            if not all(key in config for key in required_keys):
                raise ValueError("Invalid response structure from OpenAI")
            
            # Add cost estimation
            self._enhance_with_cost_estimation(config)
            
            return config
            
        except openai.OpenAIError as e:
            st.error(f"OpenAI API error: {str(e)}")
            return None
        except json.JSONDecodeError as e:
            st.error(f"Error parsing OpenAI response: {str(e)}")
            return None
        except Exception as e:
            st.error(f"Unexpected error: {str(e)}")
            return None

def main():
    st.set_page_config(page_title="Cloud Configuration Assistant", layout="wide")
    
    # Check for OpenAI API key
    if "OPENAI_API_KEY" not in st.secrets and "OPENAI_API_KEY" not in os.environ:
        st.error("""
        OpenAI API key not found. Please set it up in one of these ways:
        1. Add it to Streamlit secrets (.streamlit/secrets.toml):
           ```
           OPENAI_API_KEY = "your-key-here"
           ```
        2. Set it as an environment variable:
           ```
           export OPENAI_API_KEY="your-key-here"
           ```
        """)
        return
    
    # Initialize session state
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'aws_credentials' not in st.session_state:
        st.session_state.aws_credentials = None

    # Rest of the main function implementation...

if __name__ == "__main__":
    main()
