import boto3
import json
from botocore.exceptions import ClientError
import os

# Ensure we use the local credentials from .env for the boto3 client
from dotenv import load_dotenv
load_dotenv(".env")

def create_chatbot_role():
    iam = boto3.client('iam', region_name='us-east-1')
    sts = boto3.client('sts', region_name='us-east-1')
    
    try:
        account_id = sts.get_caller_identity()["Account"]
    except ClientError as e:
        print("Could not retrieve AWS Account ID:", e)
        return
        
    issuer_url = os.environ.get("IDENTITY_CENTER_ISSUER_URL", "cognito-idp.us-east-1.amazonaws.com/us-east-1_aU7rNNHXS")
    issuer_url = issuer_url.replace("https://", "")
    client_id = os.environ.get("IDENTITY_CENTER_CLIENT_ID", "7demdtl344bq4qbv288qeu99r")
    
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Federated": f"arn:aws:iam::{account_id}:oidc-provider/{issuer_url}"
                },
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringEquals": {
                        f"{issuer_url}:aud": client_id
                    }
                }
            }
        ]
    }
    
    try:
        print("Checking permissions to create IAM role...")
        response = iam.create_role(
            RoleName='ChatbotDefaultRole',
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description='Default role for AWS AI Chatbot'
        )
        print("Successfully created role:", response['Role']['Arn'])
        
        iam.attach_role_policy(
            RoleName='ChatbotDefaultRole',
            PolicyArn='arn:aws:iam::aws:policy/ReadOnlyAccess'
        )
        print("Attached ReadOnlyAccess policy.")
        
    except ClientError as e:
        print("Failed:", e)

if __name__ == "__main__":
    create_chatbot_role()
